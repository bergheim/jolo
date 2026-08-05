export function renderBar(usedPercent: number, width = 10): string {
  const clamped = Math.max(0, Math.min(100, usedPercent));
  const filled = Math.round((clamped / 100) * width);
  return "█".repeat(filled) + "░".repeat(width - filled);
}

export function barColor(usedPercent: number): "green" | "yellow" | "red" {
  if (usedPercent >= 90) return "red";
  if (usedPercent >= 70) return "yellow";
  return "green";
}

export function formatDuration(seconds: number): string {
  if (seconds < 60) return `${Math.floor(seconds)}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  return `${Math.floor(seconds / 3600)}h`;
}
