import { strict as assert } from "node:assert";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";

// core.ts imports auth.ts, whose AUTH_FILE/ANTIGRAVITY_TOKEN_FILE constants
// are computed once at module-load time from os.homedir(). Fake HOME before
// the first (dynamic) import so every credential read in this file resolves
// under a throwaway fixture directory instead of the real ~/.pi.
const fakeHome = fs.mkdtempSync(path.join(os.tmpdir(), "pi-usage-core-test-home-"));
process.env.HOME = fakeHome;

const farFuture = Date.now() + 1000 * 60 * 60 * 24 * 365 * 10; // 10 years out

const authDir = path.join(fakeHome, ".pi", "agent");
fs.mkdirSync(authDir, { recursive: true });
fs.writeFileSync(
  path.join(authDir, "auth.json"),
  JSON.stringify({
    "openai-codex": { access: "codex-secret-tokenAAA111", expires: farFuture },
    anthropic: { access: "claude-secret-tokenBBB222", expires: farFuture },
  }),
);

const antigravityDir = path.join(fakeHome, ".gemini", "antigravity-cli");
fs.mkdirSync(antigravityDir, { recursive: true });
fs.writeFileSync(
  path.join(antigravityDir, "antigravity-oauth-token"),
  JSON.stringify({ token: "antigravity-secret-tokenCCC333" }),
);

const { fetchAll, cachePathFor } = await import("./core.ts");

// --- cache key isolation (different accounts/providers never collide) ---
const a = cachePathFor("codex", "acct-1");
const b = cachePathFor("codex", "acct-2");
const c = cachePathFor("anthropic", "acct-1");

assert.notEqual(a, b);
assert.notEqual(a, c);
assert.ok(a.includes(String(process.getuid?.() ?? "nouid")));
assert.ok(!a.startsWith(process.env.HOME + "/.pi"));

// --- fake fetch payloads ---
const GOOD_CODEX_PAYLOAD = {
  rate_limit: {
    primary_window: { used_percent: 42, reset_after_seconds: 100 },
    secondary_window: { used_percent: 10 },
  },
};
const GOOD_CLAUDE_PAYLOAD = {
  five_hour: { utilization: 55, resets_at: new Date(Date.now() + 3600_000).toISOString() },
  seven_day: { utilization: 20 },
};
const GOOD_LOAD_CODE_ASSIST_PAYLOAD = { cloudaicompanionProject: "proj-123" };
const GOOD_ANTIGRAVITY_PAYLOAD = {
  buckets: [
    { tokenType: "REQUESTS", modelId: "gemini-2.5-pro", remainingFraction: 0.5 },
    { tokenType: "REQUESTS", modelId: "gemini-2.5-flash", remainingFraction: 0.8 },
  ],
};

function jsonResponse(status: number, body: unknown) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
  } as Response;
}

function brokenJsonResponse() {
  return {
    ok: true,
    status: 200,
    json: async () => {
      throw new Error("not json");
    },
  } as Response;
}

// Routes any URL to a good default response unless a scenario overrides it.
function defaultFetch(url: string): Promise<Response> {
  if (url.includes("wham/usage")) return Promise.resolve(jsonResponse(200, GOOD_CODEX_PAYLOAD));
  if (url.includes("oauth/usage")) return Promise.resolve(jsonResponse(200, GOOD_CLAUDE_PAYLOAD));
  if (url.includes("loadCodeAssist")) return Promise.resolve(jsonResponse(200, GOOD_LOAD_CODE_ASSIST_PAYLOAD));
  if (url.includes("retrieveUserQuota")) return Promise.resolve(jsonResponse(200, GOOD_ANTIGRAVITY_PAYLOAD));
  throw new Error(`core.test.ts: unexpected fetch url ${url}`);
}

function statusOf(results: Awaited<ReturnType<typeof fetchAll>>, name: string) {
  const entry = results.find((r) => r.name === name);
  assert.ok(entry, `missing provider status for ${name}`);
  return entry!;
}

const T0 = 1_000_000_000_000;

// --- scenario 1: good payload (codex) ---
const good = await fetchAll(T0, defaultFetch as unknown as typeof fetch);
const codexGood = statusOf(good, "codex");
assert.ok("usage" in codexGood, "codex should have usage, not stale");
if ("usage" in codexGood) {
  assert.equal(codexGood.usage.sessionPercent, 42);
  assert.equal(codexGood.usage.weeklyPercent, 10);
  assert.equal(codexGood.usage.resetsInSeconds, 100);
}

// --- cache hit: same nowMs, fetchImpl for codex must not be called again ---
let codexFetchedAgain = false;
const sentinelFetch = (url: string, init?: RequestInit) => {
  if (url.includes("wham/usage")) codexFetchedAgain = true;
  return defaultFetch(url);
};
const cached = await fetchAll(T0, sentinelFetch as unknown as typeof fetch);
assert.equal(codexFetchedAgain, false, "cached codex entry must not re-fetch within TTL");
assert.deepEqual(statusOf(cached, "codex"), codexGood);

// Every scenario below spaces its nowMs at least 61s past the previous one:
// each successful defaultFetch fallback re-caches whichever providers it
// touches, and 61s clears the 60s TTL so the *next* scenario always sees a
// cold cache rather than accidentally inheriting a neighbour's result.
const T1 = T0 + 61_000;
const T2 = T1 + 61_000;
const T3 = T2 + 61_000;
const T4 = T3 + 61_000;

// --- scenario 2: non-OK status (claude) ---
const claudeNonOk = (url: string, init?: RequestInit) => {
  if (url.includes("oauth/usage")) return Promise.resolve(jsonResponse(500, {}));
  return defaultFetch(url);
};
const nonOkResults = await fetchAll(T1, claudeNonOk as unknown as typeof fetch);
assert.deepEqual(statusOf(nonOkResults, "claude"), { name: "claude", stale: "http 500" });

// --- scenario 3: fetch throws (antigravity) ---
const antigravityThrows = (url: string, init?: RequestInit) => {
  if (url.includes("loadCodeAssist")) throw new Error("network unreachable");
  return defaultFetch(url);
};
const throwResults = await fetchAll(T2, antigravityThrows as unknown as typeof fetch);
assert.deepEqual(statusOf(throwResults, "antigravity"), { name: "antigravity", stale: "unreachable" });

// --- scenario 4: unparseable body (codex) ---
const codexUnparseable = (url: string, init?: RequestInit) => {
  if (url.includes("wham/usage")) return Promise.resolve(brokenJsonResponse());
  return defaultFetch(url);
};
const unparseableResults = await fetchAll(T3, codexUnparseable as unknown as typeof fetch);
assert.deepEqual(statusOf(unparseableResults, "codex"), { name: "codex", stale: "unparseable body" });

// --- fetchAll never throws, even when every provider fails at once ---
const allThrow = () => {
  throw new Error("boom");
};
const allFailed = await fetchAll(T4, allThrow as unknown as typeof fetch);
assert.equal(allFailed.length, 3);
for (const entry of allFailed) {
  assert.ok("stale" in entry, `${entry.name} should degrade to a stale marker, not throw`);
}

console.log("core.test.ts PASS");
