import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { fetchAll, type ProviderStatus } from "./core.ts";
import { renderBar, barColor, formatDuration } from "./render.ts";

function line(status: ProviderStatus): string {
  if ("stale" in status) return `${status.name}: — (${status.stale})`;
  const { sessionPercent, weeklyPercent, resetsInSeconds } = status.usage;
  const reset = resetsInSeconds === null
    ? ""
    : `  resets ${formatDuration(resetsInSeconds)}`;
  return (
    `${status.name}: ${renderBar(sessionPercent)} ${Math.round(sessionPercent)}%` +
    `  week ${Math.round(weeklyPercent)}%${reset}`
  );
}

// barColor speaks red/yellow/green; the theme only knows semantic slots.
const TONE = { red: "error", yellow: "warning", green: "success" } as const;

function footerLine(theme: { fg(color: string, text: string): string }, status: ProviderStatus): string {
  if ("stale" in status) return theme.fg("dim", `${status.name} —`);
  const bar = renderBar(status.usage.sessionPercent, 6);
  return theme.fg(TONE[barColor(status.usage.sessionPercent)], `${status.name} ${bar}`);
}

export default function (pi: ExtensionAPI) {
  pi.registerCommand("usage", {
    description: "Show provider quota for Codex, Claude, and Antigravity",
    handler: async (_args, ctx) => {
      const statuses = await fetchAll();
      ctx.ui.notify(statuses.map(line).join("\n"), "info");
    },
  });

  // fetchAll degrades every failure to a stale marker, so the footer never
  // has to distinguish "not fetched yet" from "provider unreachable" beyond
  // this initial empty-array loading state.
  let statuses: ProviderStatus[] = [];
  let requestRender: (() => void) | undefined;

  async function refresh(): Promise<void> {
    statuses = await fetchAll();
    requestRender?.();
  }

  pi.on("session_start", async (_event, ctx) => {
    ctx.ui.setFooter((tui, theme) => {
      requestRender = () => tui.requestRender();
      return {
        invalidate() {},
        render(): string[] {
          if (statuses.length === 0) return [theme.fg("dim", "usage: loading…")];
          return [statuses.map((s) => footerLine(theme, s)).join("  ")];
        },
      };
    });
    await refresh();
  });

  // Quota moves as turns run; re-fetch before each one. fetchAll's own
  // cache (core.ts, 60s TTL) keeps this from hammering provider APIs.
  pi.on("turn_start", async () => {
    await refresh();
  });
}
