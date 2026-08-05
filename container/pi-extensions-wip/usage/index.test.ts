import { strict as assert } from "node:assert";
import type { ProviderStatus } from "./core.ts";
import indexModule, { renderFooterLines } from "./index.ts";

// theme.fg is identity here: renderFooterLines must budget width against the
// plain text it decides to include, not against ANSI-wrapped output, so an
// identity theme is a faithful stand-in for measuring the same lines a real
// (colored) theme would produce.
const fakeTheme = { fg: (_color: string, text: string) => text };

function lineLengths(lines: string[]): number[] {
  return lines.map((l) => l.length);
}

// --- finding 2: render(width) must never return a line longer than width ---

// Loading state (no statuses yet)
for (const width of [0, 1, 5, 16, 40, 80]) {
  const lines = renderFooterLines(fakeTheme, [], width);
  for (const len of lineLengths(lines)) {
    assert.ok(len <= width, `loading state at width ${width} produced a line of length ${len}`);
  }
}

const usageCodex: ProviderStatus = {
  name: "codex",
  usage: { sessionPercent: 42, weeklyPercent: 10, resetsInSeconds: 100 },
};
const usageClaude: ProviderStatus = {
  name: "claude",
  usage: { sessionPercent: 91, weeklyPercent: 50, resetsInSeconds: null },
};
const staleAntigravity: ProviderStatus = { name: "antigravity", stale: "http 500" };

const allStatuses = [usageCodex, usageClaude, staleAntigravity];

// A three-provider footer easily overflows a narrow terminal (the reported
// finding), so sweep a range of widths, including the one called out
// explicitly (40) and ones narrower than any single segment.
for (const width of [0, 1, 4, 8, 12, 13, 20, 27, 31, 40, 80]) {
  const lines = renderFooterLines(fakeTheme, allStatuses, width);
  for (const len of lineLengths(lines)) {
    assert.ok(len <= width, `width ${width} produced a line of length ${len} (line: ${JSON.stringify(lines)})`);
  }
}

// At width 40 specifically: 3 whole segments (12 + 13 + 18 chars, 2-space
// separated = 47) don't fit, so the third column (antigravity) must be
// dropped and a "+1" omission marker shown instead of silently truncating.
{
  const lines = renderFooterLines(fakeTheme, allStatuses, 40);
  assert.equal(lines.length, 1);
  assert.ok(lines[0].length <= 40);
  assert.ok(lines[0].includes("codex"), "codex should fit at width 40");
  assert.ok(lines[0].includes("claude"), "claude should fit at width 40");
  assert.ok(!lines[0].includes("antigravity"), "antigravity should be dropped at width 40");
  assert.ok(lines[0].includes("+1"), "a dropped column should surface an omission marker");
}

// Negative width (defensive: pi's contract promises a non-negative width,
// but a caller mistake here must degrade, not throw or return garbage).
{
  const lines = renderFooterLines(fakeTheme, allStatuses, -5);
  for (const len of lineLengths(lines)) {
    assert.ok(len <= 0, `negative width produced a non-empty line: ${JSON.stringify(lines)}`);
  }
}

// Every provider fits comfortably at a wide terminal: no column dropped.
{
  const lines = renderFooterLines(fakeTheme, allStatuses, 200);
  assert.ok(lines[0].includes("codex") && lines[0].includes("claude") && lines[0].includes("antigravity"));
  assert.ok(!lines[0].includes("+"), "nothing should be omitted when everything fits");
}

// The default export is the extension entry point pi loads; it must stay a
// plain function (pi calls it with an ExtensionAPI instance).
assert.equal(typeof indexModule, "function");

console.log("index.test.ts PASS");
