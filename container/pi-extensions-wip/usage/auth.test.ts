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

// Antigravity: different file, different shape, no expiry field
const agy = path.join(tmp, "agy-token");
fs.writeFileSync(agy, JSON.stringify({
  token: "gtok", id_token: "id", auth_method: "oauth",
}));
assert.deepEqual(readAntigravityCredential(agy), { token: "gtok" });

// Top-level JSON null -> stale, not a throw (both consumers of readJson)
const topNull = path.join(tmp, "top-null.json");
fs.writeFileSync(topNull, "null");
assert.deepEqual(
  readCodexCredential(topNull, 1000), { stale: "unreadable" },
);
assert.deepEqual(readAntigravityCredential(topNull), { stale: "unreadable" });

// Top-level JSON array -> stale, not a throw
const topArray = path.join(tmp, "top-array.json");
fs.writeFileSync(topArray, "[1,2,3]");
assert.deepEqual(
  readCodexCredential(topArray, 1000), { stale: "unreadable" },
);
assert.deepEqual(
  readAntigravityCredential(topArray), { stale: "unreadable" },
);

// Top-level JSON string -> stale, not a throw
const topString = path.join(tmp, "top-string.json");
fs.writeFileSync(topString, '"just a string"');
assert.deepEqual(
  readCodexCredential(topString, 1000), { stale: "unreadable" },
);
assert.deepEqual(
  readAntigravityCredential(topString), { stale: "unreadable" },
);

console.log("auth.test.ts PASS");
