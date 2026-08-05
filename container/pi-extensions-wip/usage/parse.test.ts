import { strict as assert } from "node:assert";
import {
  parseCodexUsage, parseAnthropicUsage, parseGoogleQuota,
} from "./parse.ts";

// --- Codex: chatgpt.com/backend-api/wham/usage ---
// Real shape is rate_limit.{primary,secondary}_window.{used_percent,
// reset_after_seconds} — not rate_limits.{primary,secondary}.
// {used_percent, resets_in_seconds} as originally guessed.

assert.deepEqual(
  parseCodexUsage({
    rate_limit: {
      primary_window: { used_percent: 42, reset_after_seconds: 7200 },
      secondary_window: { used_percent: 13 },
    },
  }),
  { sessionPercent: 42, weeklyPercent: 13, resetsInSeconds: 7200 },
);

// secondary_window missing -> weekly falls back to session, not a throw
assert.deepEqual(
  parseCodexUsage({ rate_limit: { primary_window: { used_percent: 60 } } }),
  { sessionPercent: 60, weeklyPercent: 60, resetsInSeconds: null },
);

// Garbage in -> null, never a throw and never NaN
assert.equal(parseCodexUsage(null), null);
assert.equal(parseCodexUsage({}), null);
assert.equal(parseCodexUsage("nonsense"), null);
assert.equal(parseCodexUsage([1, 2, 3]), null);
assert.equal(parseCodexUsage({ rate_limit: {} }), null);
// Nested percent as a string rather than a number
assert.equal(
  parseCodexUsage({ rate_limit: { primary_window: { used_percent: "42" } } }),
  null,
);

// --- Anthropic: api.anthropic.com/api/oauth/usage ---
// Real shape is five_hour/seven_day.{utilization, resets_at (ISO string)} —
// unrelated to Codex's rate_limit.*_window shape, so this is NOT a delegate
// to parseCodexUsage as the brief guessed. resets_at is an absolute
// timestamp, not a duration, so parseAnthropicUsage takes an optional nowMs
// (matching the nowMs pattern already used in auth.ts) to convert it to
// seconds-until-reset deterministically in tests.

const fixedNow = 1_700_000_000_000;
const resetsAt = new Date(fixedNow + 3600_000).toISOString();

assert.deepEqual(
  parseAnthropicUsage(
    { five_hour: { utilization: 55, resets_at: resetsAt }, seven_day: { utilization: 20 } },
    fixedNow,
  ),
  { sessionPercent: 55, weeklyPercent: 20, resetsInSeconds: 3600 },
);

// seven_day missing -> weekly falls back to session
assert.deepEqual(
  parseAnthropicUsage({ five_hour: { utilization: 30 } }, fixedNow),
  { sessionPercent: 30, weeklyPercent: 30, resetsInSeconds: null },
);

// resets_at missing -> resetsInSeconds is null, not a throw
assert.deepEqual(
  parseAnthropicUsage(
    { five_hour: { utilization: 10 }, seven_day: { utilization: 5 } },
    fixedNow,
  ),
  { sessionPercent: 10, weeklyPercent: 5, resetsInSeconds: null },
);

// Garbage in -> null, never a throw and never NaN
assert.equal(parseAnthropicUsage(null), null);
assert.equal(parseAnthropicUsage({}), null);
assert.equal(parseAnthropicUsage("nonsense"), null);
assert.equal(parseAnthropicUsage([1, 2, 3]), null);
// Nested percent as a string rather than a number
assert.equal(
  parseAnthropicUsage({ five_hour: { utilization: "55" } }, fixedNow),
  null,
);

// --- Google: cloudcode-pa.googleapis.com/.../retrieveUserQuota ---
// Real shape is a top-level `buckets` array (not `quotaBuckets`), each with
// tokenType, modelId, and remainingFraction. Buckets are filtered to
// tokenType "REQUESTS" (falling back to all buckets if none match), then
// split into a gemini-pro group (session) and gemini-flash group (weekly) —
// mirroring the non-antigravity branch of parseGoogleQuotaBuckets, since
// antigravity's claude-vs-gemini bucket selection needs a provider hint
// this generic single-arg parser doesn't take.

assert.deepEqual(
  parseGoogleQuota({
    buckets: [
      { tokenType: "REQUESTS", modelId: "gemini-2.5-pro", remainingFraction: 0.9 },
      { tokenType: "REQUESTS", modelId: "gemini-2.5-flash", remainingFraction: 0.2 },
    ],
  }),
  { sessionPercent: 10, weeklyPercent: 80, resetsInSeconds: null },
);

// No REQUESTS-typed bucket and no pro/flash match -> falls back to the one
// bucket present for both session and weekly
assert.deepEqual(
  parseGoogleQuota({
    buckets: [{ tokenType: "TOKENS", modelId: "claude-3-opus", remainingFraction: 0.5 }],
  }),
  { sessionPercent: 50, weeklyPercent: 50, resetsInSeconds: null },
);

// Garbage in -> null, never a throw and never NaN
assert.equal(parseGoogleQuota(null), null);
assert.equal(parseGoogleQuota({}), null);
assert.equal(parseGoogleQuota("nonsense"), null);
assert.equal(parseGoogleQuota([1, 2, 3]), null);
assert.equal(parseGoogleQuota({ buckets: [] }), null);
// Nested fraction as a string rather than a number
assert.equal(
  parseGoogleQuota({ buckets: [{ remainingFraction: "0.5" }] }),
  null,
);

console.log("parse.test.ts PASS");
