import { strict as assert } from "node:assert";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import {
  readCodexCredential, readAnthropicCredential, readAntigravityCredential,
} from "./auth.ts";

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "usage-auth-"));

// Codex: live token
const live = path.join(tmp, "live.json");
fs.writeFileSync(live, JSON.stringify({
  "openai-codex": { access: "tok", refresh: "r", expires: 4102444800000 },
}));
assert.deepEqual(readCodexCredential(live, 1000), { token: "tok" });

// Codex: expired -> stale, never a token
const expired = path.join(tmp, "expired.json");
fs.writeFileSync(expired, JSON.stringify({
  "openai-codex": { access: "tok", refresh: "r", expires: 500 },
}));
assert.deepEqual(readCodexCredential(expired, 1000), { stale: "expired" });

// Missing file -> stale, not a throw
assert.deepEqual(
  readCodexCredential(path.join(tmp, "nope.json"), 1000),
  { stale: "no credential" },
);

// Malformed JSON -> stale, not a throw
const bad = path.join(tmp, "bad.json");
fs.writeFileSync(bad, "{not json");
assert.deepEqual(readCodexCredential(bad, 1000), { stale: "unreadable" });

// Anthropic: live token
const anthropicLive = path.join(tmp, "anthropic-live.json");
fs.writeFileSync(anthropicLive, JSON.stringify({
  anthropic: { access: "atok", refresh: "r", expires: 4102444800000 },
}));
assert.deepEqual(
  readAnthropicCredential(anthropicLive, 1000), { token: "atok" },
);

// Anthropic: expired -> stale, never a token
const anthropicExpired = path.join(tmp, "anthropic-expired.json");
fs.writeFileSync(anthropicExpired, JSON.stringify({
  anthropic: { access: "atok", refresh: "r", expires: 500 },
}));
assert.deepEqual(
  readAnthropicCredential(anthropicExpired, 1000), { stale: "expired" },
);

// Codex: expires missing entirely -> stale, not a live token
const noExpires = path.join(tmp, "no-expires.json");
fs.writeFileSync(noExpires, JSON.stringify({
  "openai-codex": { access: "tok", refresh: "r" },
}));
assert.deepEqual(
  readCodexCredential(noExpires, 1000), { stale: "expired" },
);

// Codex: expires present but non-numeric -> stale, not a live token
const badExpires = path.join(tmp, "bad-expires.json");
fs.writeFileSync(badExpires, JSON.stringify({
  "openai-codex": { access: "tok", refresh: "r", expires: "soon" },
}));
assert.deepEqual(
  readCodexCredential(badExpires, 1000), { stale: "expired" },
);

// No auth.json at all in these tests unless a case creates one: keeps
// readAntigravityCredential's auth.json-preferred branch from accidentally
// reading this container's real ~/.pi/agent/auth.json when a test only
// overrides the tokenFile argument.
const noAuthFile = path.join(tmp, "no-auth.json");

// --- Fix 1 regression: every reader must type-guard its token before
// returning it. This is the invariant fetchOne relies on for
// `credential.token.slice(...)`.

// Nested-object token: `entry.access` itself an object, not a string — the
// exact shape of bug that crashed fetchOne with
// "TypeError: credential.token.slice is not a function" when a reader
// returned an unguarded field as the token.
const nestedAccess = path.join(tmp, "nested-access.json");
fs.writeFileSync(nestedAccess, JSON.stringify({
  "openai-codex": { access: { nested: "object" }, refresh: "r", expires: 4102444800000 },
}));
assert.deepEqual(readCodexCredential(nestedAccess, 1000), { stale: "no credential" });

// Empty-string token -> stale, never a live credential.
const emptyAccess = path.join(tmp, "empty-access.json");
fs.writeFileSync(emptyAccess, JSON.stringify({
  "openai-codex": { access: "", refresh: "r", expires: 4102444800000 },
}));
assert.deepEqual(readCodexCredential(emptyAccess, 1000), { stale: "no credential" });

// Numeric token -> stale, never a live credential.
const numericAccess = path.join(tmp, "numeric-access.json");
fs.writeFileSync(numericAccess, JSON.stringify({
  "openai-codex": { access: 12345, refresh: "r", expires: 4102444800000 },
}));
assert.deepEqual(readCodexCredential(numericAccess, 1000), { stale: "no credential" });

// --- Fix 2 regression: Antigravity real credential shapes ---
//
// ~/.gemini/antigravity-cli/antigravity-oauth-token ("agy" CLI store):
//   { token: { access_token, token_type, refresh_token, expiry }, id_token, auth_method }
// ~/.pi/agent/auth.json ("google-antigravity" key, pi's own store):
//   { access, refresh, expires, ... } — same shape as codex/anthropic.

// auth.json's google-antigravity entry (pi's own store) takes priority over
// the standalone agy file.
const authJsonAntigravity = path.join(tmp, "auth-antigravity.json");
fs.writeFileSync(authJsonAntigravity, JSON.stringify({
  "google-antigravity": { access: "auth-json-tok", refresh: "r", expires: 4102444800000 },
}));
assert.deepEqual(
  readAntigravityCredential(path.join(tmp, "nope-agy"), authJsonAntigravity),
  { token: "auth-json-tok" },
);

// Falls back to the agy CLI store when auth.json has no google-antigravity
// key at all — verified real shape: a nested `token` dict, not a bare string.
const agyReal = path.join(tmp, "agy-real-token");
fs.writeFileSync(agyReal, JSON.stringify({
  token: {
    access_token: "agy-access-tok", token_type: "Bearer",
    refresh_token: "r", expiry: "2099-01-01T00:00:00Z",
  },
  id_token: "idtok",
  auth_method: "oauth",
}));
assert.deepEqual(
  readAntigravityCredential(agyReal, noAuthFile),
  { token: "agy-access-tok" },
);

// auth.json present but without a google-antigravity key -> still falls
// back to the agy file rather than treating the file's presence as enough.
assert.deepEqual(
  readAntigravityCredential(agyReal, live), // `live` above only has openai-codex
  { token: "agy-access-tok" },
);

// agy file's `token` is itself the nested object, returned raw with no
// `.access_token` unwrap: this is exactly what crashed fetchOne before the
// fix (`{ token: <object> }`). Malformed shape must fail safe, not surface
// the object as a token.
const agyMalformed = path.join(tmp, "agy-malformed-token");
fs.writeFileSync(agyMalformed, JSON.stringify({
  token: { wrong_field: "no access_token here" }, id_token: "id", auth_method: "oauth",
}));
assert.deepEqual(
  readAntigravityCredential(agyMalformed, noAuthFile),
  { stale: "no credential" },
);

// agy file's `token` as a bare string (not the real nested shape) -> stale,
// never mistaken for the access token itself.
const agyStringToken = path.join(tmp, "agy-string-token");
fs.writeFileSync(agyStringToken, JSON.stringify({
  token: "gtok", id_token: "id", auth_method: "oauth",
}));
assert.deepEqual(
  readAntigravityCredential(agyStringToken, noAuthFile),
  { stale: "no credential" },
);

// Top-level JSON null -> stale, not a throw (both consumers of readJson)
const topNull = path.join(tmp, "top-null.json");
fs.writeFileSync(topNull, "null");
assert.deepEqual(
  readCodexCredential(topNull, 1000), { stale: "unreadable" },
);
assert.deepEqual(
  readAntigravityCredential(topNull, noAuthFile), { stale: "unreadable" },
);

// Top-level JSON array -> stale, not a throw
const topArray = path.join(tmp, "top-array.json");
fs.writeFileSync(topArray, "[1,2,3]");
assert.deepEqual(
  readCodexCredential(topArray, 1000), { stale: "unreadable" },
);
assert.deepEqual(
  readAntigravityCredential(topArray, noAuthFile), { stale: "unreadable" },
);

// Top-level JSON string -> stale, not a throw
const topString = path.join(tmp, "top-string.json");
fs.writeFileSync(topString, '"just a string"');
assert.deepEqual(
  readCodexCredential(topString, 1000), { stale: "unreadable" },
);
assert.deepEqual(
  readAntigravityCredential(topString, noAuthFile), { stale: "unreadable" },
);

console.log("auth.test.ts PASS");
