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

// core.ts's cache lives under os.tmpdir(), which is the real shared /tmp
// unless TMPDIR says otherwise. os.tmpdir() reads TMPDIR at call time (not
// at process start) on Linux, so setting it here — before core.ts is
// imported or fetchAll/cachePathFor is ever called — is enough to keep
// this run's cache files from leaking into or reading a prior run's.
const fakeTmp = fs.mkdtempSync(path.join(os.tmpdir(), "pi-usage-core-test-tmp-"));
process.env.TMPDIR = fakeTmp;

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
// Both loadCodeAssist endpoints throw here (the mock matches on the
// "loadCodeAssist" substring, which both endpoint URLs contain), so
// discovery exhausts its fallback and requestAntigravity reports the
// specific missing-projectId reason, not a generic "unreachable".
const throwResults = await fetchAll(T2, antigravityThrows as unknown as typeof fetch);
assert.deepEqual(statusOf(throwResults, "antigravity"), {
  name: "antigravity",
  stale: "missing projectId (try /login again)",
});

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

const T5 = T4 + 61_000;
const T6 = T5 + 61_000;
const T7 = T6 + 61_000;
const T8 = T7 + 61_000;
const codexAccountKey = "codex-secret-tokenAAA111".slice(-12);

// --- finding 1: a cache entry with a future `at` must not be immortal ---
{
  const primed = await fetchAll(T5, defaultFetch as unknown as typeof fetch);
  assert.ok("usage" in statusOf(primed, "codex"), "priming fetch should succeed");

  const cacheFile = cachePathFor("codex", codexAccountKey);
  const entry = JSON.parse(fs.readFileSync(cacheFile, "utf-8"));
  entry.at = T5 + 1000 * 60 * 60 * 24; // a day in the future: clock stepped back, or a copied file
  fs.writeFileSync(cacheFile, JSON.stringify(entry));

  let refetched = false;
  const sentinelFetch2 = (url: string) => {
    if (url.includes("wham/usage")) refetched = true;
    return defaultFetch(url);
  };
  // Same T5: naive `nowMs - at < TTL` is negative here, which the buggy
  // check treats as "fresh forever". A correct cache must reject it.
  const afterFutureAt = await fetchAll(T5, sentinelFetch2 as unknown as typeof fetch);
  assert.ok(refetched, "a future `at` must not pin the cache entry forever");
  assert.ok("usage" in statusOf(afterFutureAt, "codex"));
}

// --- finding 2: cached usage must be validated before it reaches callers ---
{
  const cacheFile = cachePathFor("codex", codexAccountKey);
  fs.mkdirSync(path.dirname(cacheFile), { recursive: true });
  fs.writeFileSync(
    cacheFile,
    JSON.stringify({ at: T6, usage: { sessionPercent: "9999", weeklyPercent: 10, resetsInSeconds: 100 } }),
  );

  // age is 0 (well within TTL), so only the shape/type of `usage` is under
  // test here — a corrupt cache entry must be treated as a miss.
  const results = await fetchAll(T6, defaultFetch as unknown as typeof fetch);
  const codex = statusOf(results, "codex");
  assert.ok("usage" in codex, "a malformed cache entry must fall back to a live fetch");
  if ("usage" in codex) {
    assert.equal(typeof codex.usage.sessionPercent, "number");
  }

  const cacheFile2 = cachePathFor("codex", codexAccountKey);
  fs.writeFileSync(cacheFile2, JSON.stringify({ at: T6, usage: 7 }));
  const results2 = await fetchAll(T6, defaultFetch as unknown as typeof fetch);
  assert.ok("usage" in statusOf(results2, "codex"), "a non-object cached usage must fall back to a live fetch");
}

// --- finding 3: fetchAll must not throw when a stage outside try/catch throws ---
{
  // A fetchImpl resolving to a non-Response makes `!response.ok` throw a
  // TypeError instead of returning false.
  const brokenResponseFetch = (url: string) => {
    if (url.includes("oauth/usage")) return Promise.resolve(undefined as unknown as Response);
    return defaultFetch(url);
  };
  let threw = false;
  let resultsC: Awaited<ReturnType<typeof fetchAll>> = [];
  try {
    resultsC = await fetchAll(T7, brokenResponseFetch as unknown as typeof fetch);
  } catch {
    threw = true;
  }
  assert.equal(threw, false, "fetchAll must not throw when a fetchImpl resolves to a non-Response");
  assert.ok("stale" in statusOf(resultsC, "claude"), "claude should degrade to stale, not crash fetchAll");
}

// --- finding 4: a failing primary loadCodeAssist endpoint must fall back to the mirror ---
{
  const mirrorFallbackFetch = (url: string) => {
    if (url === "https://cloudcode-pa.googleapis.com/v1internal:loadCodeAssist") {
      throw new Error("primary endpoint down");
    }
    return defaultFetch(url);
  };
  const resultsD = await fetchAll(T8, mirrorFallbackFetch as unknown as typeof fetch);
  assert.ok(
    "usage" in statusOf(resultsD, "antigravity"),
    "a primary loadCodeAssist failure must fall back to the sandbox mirror, not abort discovery",
  );
}

console.log("core.test.ts PASS");
