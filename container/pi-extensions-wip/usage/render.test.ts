import { strict as assert } from "node:assert";
import { renderBar, formatDuration, barColor } from "./render.ts";

assert.equal(renderBar(0, 10), "░░░░░░░░░░");
assert.equal(renderBar(100, 10), "██████████");
assert.equal(renderBar(50, 10), "█████░░░░░");

// Clamp rather than overflow or throw
assert.equal(renderBar(150, 10), "██████████");
assert.equal(renderBar(-10, 10), "░░░░░░░░░░");

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

console.log("render.test.ts PASS");
