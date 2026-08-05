import fs from "node:fs";
import os from "node:os";
import path from "node:path";

export type Credential = { token: string } | { stale: string };

export const AUTH_FILE = path.join(os.homedir(), ".pi", "agent", "auth.json");
export const ANTIGRAVITY_TOKEN_FILE = path.join(
  os.homedir(), ".gemini", "antigravity-cli", "antigravity-oauth-token",
);

type ReadResult =
  | { ok: Record<string, any> }
  | { missing: true }
  | { corrupt: true };

// Read-only by design. Refreshing here would race pi's own refresh on a mount
// shared by the host and every container; a rotated token written back stale
// logs every pi on that mount out.
function readJson(file: string): ReadResult {
  let raw: string;
  try {
    raw = fs.readFileSync(file, "utf-8");
  } catch (err: any) {
    return err?.code === "ENOENT" ? { missing: true } : { corrupt: true };
  }
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return { corrupt: true };
  }
  // A credential store must be a plain object: null, arrays, and scalars all
  // parse fine as JSON but crash the `entry.foo` lookups below if allowed
  // through.
  if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
    return { corrupt: true };
  }
  return { ok: parsed as Record<string, any> };
}

function fromAuthFile(
  provider: string, authFile: string, nowMs: number,
): Credential {
  const result = readJson(authFile);
  if ("missing" in result) return { stale: "no credential" };
  if ("corrupt" in result) return { stale: "unreadable" };
  const entry = result.ok[provider];
  if (!entry?.access) return { stale: "no credential" };
  // Real codex/anthropic entries always carry a numeric `expires` (unlike
  // Antigravity's file, which has none by design). An absent field is as
  // untrustworthy as a malformed one here, so both fail safe as expired
  // rather than being read as a live, never-expiring token.
  if (typeof entry.expires !== "number" || entry.expires <= nowMs) {
    return { stale: "expired" };
  }
  return { token: entry.access };
}

export function readCodexCredential(
  authFile = AUTH_FILE, nowMs = Date.now(),
): Credential {
  return fromAuthFile("openai-codex", authFile, nowMs);
}

export function readAnthropicCredential(
  authFile = AUTH_FILE, nowMs = Date.now(),
): Credential {
  return fromAuthFile("anthropic", authFile, nowMs);
}

// Antigravity is not in auth.json: separate file, different shape, and it
// carries no expiry field — so there is nothing to check but presence.
export function readAntigravityCredential(
  tokenFile = ANTIGRAVITY_TOKEN_FILE,
): Credential {
  const result = readJson(tokenFile);
  if ("missing" in result) return { stale: "no credential" };
  if ("corrupt" in result) return { stale: "unreadable" };
  return result.ok.token
    ? { token: result.ok.token }
    : { stale: "no credential" };
}
