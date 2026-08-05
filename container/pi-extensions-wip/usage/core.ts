import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import {
  readCodexCredential, readAnthropicCredential, readAntigravityCredential,
} from "./auth.ts";
import {
  parseCodexUsage, parseAnthropicUsage, parseGoogleQuota, type Usage,
} from "./parse.ts";

export type ProviderStatus =
  | { name: string; usage: Usage }
  | { name: string; stale: string };

const CACHE_TTL_MS = 60_000;

// tmpdir, never ~/.pi: that mount is shared live with the host and every
// other container, and cache churn does not belong in contended space.
export function cachePathFor(provider: string, accountKey: string): string {
  const uid = String(process.getuid?.() ?? "nouid");
  const safe = accountKey.replace(/[^A-Za-z0-9_-]/g, "_");
  return path.join(os.tmpdir(), "pi-usage", uid, provider, `${safe}.json`);
}

function readCache(file: string, nowMs: number): Usage | null {
  try {
    const entry = JSON.parse(fs.readFileSync(file, "utf-8"));
    return nowMs - entry.at < CACHE_TTL_MS ? entry.usage : null;
  } catch {
    return null;
  }
}

function writeCache(file: string, usage: Usage, nowMs: number): void {
  try {
    fs.mkdirSync(path.dirname(file), { recursive: true });
    fs.writeFileSync(file, JSON.stringify({ at: nowMs, usage }));
  } catch {
    // Cache is an optimisation; losing it must never break the bar.
  }
}

// --- Google (Antigravity) needs a Cloud Code project id before it will hand
// out quota, and the retrieveUserQuota call itself is a POST with a specific
// header set — nothing like the plain bearer-token GETs codex/claude use.
// Shape verified against the reference's googleHeaders/googleMetadata/
// discoverGoogleProjectId/fetchGoogleUsage (see task-9-report.md).

function googleMetadata(projectId?: string) {
  return {
    ideType: "IDE_UNSPECIFIED",
    platform: "PLATFORM_UNSPECIFIED",
    pluginType: "GEMINI",
    ...(projectId ? { duetProject: projectId } : {}),
  };
}

function googleHeaders(token: string, projectId?: string) {
  return {
    Authorization: `Bearer ${token}`,
    "Content-Type": "application/json",
    "User-Agent": "google-cloud-sdk vscode_cloudshelleditor/0.1",
    "X-Goog-Api-Client": "gl-node/22.17.0",
    "Client-Metadata": JSON.stringify(googleMetadata(projectId)),
  };
}

const GOOGLE_QUOTA_ENDPOINT = "https://cloudcode-pa.googleapis.com/v1internal:retrieveUserQuota";
const GOOGLE_LOAD_CODE_ASSIST_ENDPOINTS = [
  "https://cloudcode-pa.googleapis.com/v1internal:loadCodeAssist",
  "https://daily-cloudcode-pa.sandbox.googleapis.com/v1internal:loadCodeAssist",
];

async function discoverGoogleProjectId(
  token: string, fetchImpl: typeof fetch,
): Promise<string | undefined> {
  const envProjectId = process.env.GOOGLE_CLOUD_PROJECT || process.env.GOOGLE_CLOUD_PROJECT_ID;
  if (envProjectId) return envProjectId;

  for (const endpoint of GOOGLE_LOAD_CODE_ASSIST_ENDPOINTS) {
    const response = await fetchImpl(endpoint, {
      method: "POST",
      headers: googleHeaders(token),
      body: JSON.stringify({ metadata: googleMetadata() }),
    });
    if (!response.ok) continue;
    const data = await response.json();
    if (typeof data?.cloudaicompanionProject === "string" && data.cloudaicompanionProject) {
      return data.cloudaicompanionProject;
    }
    if (typeof data?.cloudaicompanionProject?.id === "string") return data.cloudaicompanionProject.id;
  }
  return undefined;
}

async function requestCodex(token: string, fetchImpl: typeof fetch): Promise<Response> {
  return fetchImpl("https://chatgpt.com/backend-api/wham/usage", {
    headers: { Authorization: `Bearer ${token}` },
  });
}

async function requestClaude(token: string, fetchImpl: typeof fetch): Promise<Response> {
  return fetchImpl("https://api.anthropic.com/api/oauth/usage", {
    headers: {
      Authorization: `Bearer ${token}`,
      "anthropic-beta": "oauth-2025-04-20",
    },
  });
}

async function requestAntigravity(token: string, fetchImpl: typeof fetch): Promise<Response> {
  const projectId = await discoverGoogleProjectId(token, fetchImpl);
  if (!projectId) throw new Error("no project id");
  return fetchImpl(GOOGLE_QUOTA_ENDPOINT, {
    method: "POST",
    headers: googleHeaders(token, projectId),
    body: JSON.stringify({ project: projectId }),
  });
}

const PROVIDERS = [
  {
    name: "codex",
    read: (nowMs: number) => readCodexCredential(undefined, nowMs),
    request: requestCodex,
    parse: (payload: unknown) => parseCodexUsage(payload),
  },
  {
    name: "claude",
    read: (nowMs: number) => readAnthropicCredential(undefined, nowMs),
    request: requestClaude,
    parse: (payload: unknown, nowMs: number) => parseAnthropicUsage(payload, nowMs),
  },
  {
    name: "antigravity",
    read: (_nowMs: number) => readAntigravityCredential(),
    request: requestAntigravity,
    parse: (payload: unknown) => parseGoogleQuota(payload),
  },
] as const;

async function fetchOne(
  provider: (typeof PROVIDERS)[number],
  nowMs: number,
  fetchImpl: typeof fetch,
): Promise<ProviderStatus> {
  const credential = provider.read(nowMs);
  if ("stale" in credential) {
    return { name: provider.name, stale: credential.stale };
  }

  const cacheFile = cachePathFor(provider.name, credential.token.slice(-12));
  const cached = readCache(cacheFile, nowMs);
  if (cached) return { name: provider.name, usage: cached };

  let response: Response;
  try {
    response = await provider.request(credential.token, fetchImpl);
  } catch {
    return { name: provider.name, stale: "unreachable" };
  }
  if (!response.ok) {
    return { name: provider.name, stale: `http ${response.status}` };
  }

  let body: unknown;
  try {
    body = await response.json();
  } catch {
    return { name: provider.name, stale: "unparseable body" };
  }

  const usage = provider.parse(body, nowMs);
  if (!usage) return { name: provider.name, stale: "unrecognised payload" };

  writeCache(cacheFile, usage, nowMs);
  return { name: provider.name, usage };
}

export async function fetchAll(
  nowMs = Date.now(), fetchImpl: typeof fetch = fetch,
): Promise<ProviderStatus[]> {
  return Promise.all(PROVIDERS.map((p) => fetchOne(p, nowMs, fetchImpl)));
}
