import { strict as assert } from "node:assert";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { readCodexCredential, readAntigravityCredential } from "./auth.ts";

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

// Antigravity: different file, different shape, no expiry field
const agy = path.join(tmp, "agy-token");
fs.writeFileSync(agy, JSON.stringify({
  token: "gtok", id_token: "id", auth_method: "oauth",
}));
assert.deepEqual(readAntigravityCredential(agy), { token: "gtok" });

console.log("auth.test.ts PASS");
