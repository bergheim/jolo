import { strict as assert } from "node:assert";
import { renderBar, formatDuration, barColor } from "./render.ts";

assert.equal(renderBar(0, 10), "░░░░░░░░░░");
assert.equal(renderBar(100, 10), "██████████");
assert.equal(renderBar(50, 10), "█████░░░░░");

// Clamp rather than overflow or throw
assert.equal(renderBar(150, 10), "██████████");
assert.equal(renderBar(-10, 10), "░░░░░░░░░░");

// Untrusted provider payloads: non-finite usedPercent must not collapse the column
assert.equal(renderBar(NaN, 10), "░░░░░░░░░░");
assert.equal(renderBar(Infinity, 10), "░░░░░░░░░░");
assert.equal(renderBar(-Infinity, 10), "░░░░░░░░░░");

// Caller-controlled width must not throw on negative values
assert.equal(renderBar(50, -5), "");

assert.equal(barColor(10), "green");
assert.equal(barColor(69.9), "green");
assert.equal(barColor(70), "yellow");
assert.equal(barColor(89.9), "yellow");
assert.equal(barColor(90), "red");

assert.equal(formatDuration(45), "45s");
assert.equal(formatDuration(90), "1m");
assert.equal(formatDuration(3600), "1h");
assert.equal(formatDuration(291639), "81h");
assert.equal(formatDuration(0), "0s");

// Untrusted provider payloads: non-finite and negative resetsInSeconds must degrade sanely
assert.equal(formatDuration(NaN), "0s");
assert.equal(formatDuration(Infinity), "0s");
assert.equal(formatDuration(-30), "0s");

console.log("render.test.ts PASS");
