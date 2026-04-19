"""`jolo autonomous` — dispatch `:autonomous:`-tagged TODO items as fresh
`jolo tree` worktrees with per-item agents.

Selection and idempotency live in Emacs (authoritative org-mode reader);
dispatch lives here. Host cron decides cadence.
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from _jolo.cli import find_git_root, slugify_prompt
from _jolo.commands import load_config

ELISP_SELECT_FN = "bergheim/agent-org-autonomous-select"
ELISP_MARK_FN = "bergheim/agent-org-autonomous-mark-dispatched"


def parse_emacsclient_json(raw: str) -> list[dict]:
    """Decode emacsclient `-e` output that wraps a JSON string.

    emacsclient prints elisp values; strings come back as `"..."` with
    backslash-escaped inner quotes. `ast.literal_eval` handles that
    unescape, and the resulting Python str is parsed as JSON.
    """
    stripped = raw.strip()
    if not stripped or stripped == "nil":
        return []
    try:
        unescaped = ast.literal_eval(stripped)
    except (ValueError, SyntaxError) as exc:
        raise ValueError(
            f"emacsclient output is not a lisp string: {raw!r}"
        ) from exc
    if not isinstance(unescaped, str):
        raise ValueError(f"emacsclient returned non-string: {unescaped!r}")
    if not unescaped:
        return []
    decoded = json.loads(unescaped)
    if decoded is None:
        return []
    return decoded


def build_slug(heading: str) -> str:
    """Worktree slug for an org heading, with `autonomous-` prefix."""
    stripped = re.sub(r"^(TODO|NEXT|INPROGRESS|WAITING)\s+", "", heading)
    return "autonomous-" + slugify_prompt(stripped)


def assign_agents(
    items: list[dict], agents: list[str]
) -> list[tuple[dict, str]]:
    """Round-robin assignment of agents to items."""
    if not agents:
        raise ValueError("agents list must not be empty")
    return [(item, agents[i % len(agents)]) for i, item in enumerate(items)]


def resolve_agents(flag: str | None, config_default: list[str]) -> list[str]:
    """CLI flag wins over config default; reject empty result."""
    if flag is not None:
        agents = [a.strip() for a in flag.split(",") if a.strip()]
    else:
        agents = list(config_default)
    if not agents:
        raise ValueError("no agents configured for autonomous dispatch")
    return agents


class EmacsClientError(RuntimeError):
    """emacsclient exited non-zero — daemon unreachable or helper missing."""


def _emacsclient_eval(elisp: str) -> str:
    """Evaluate ELISP via emacsclient. Raise on non-zero exit."""
    result = subprocess.run(
        ["emacsclient", "-e", elisp],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise EmacsClientError(
            f"emacsclient failed ({result.returncode}): {result.stderr.strip()}"
        )
    return result.stdout


def get_autonomous_items(org_file: Path) -> list[dict]:
    """Return `[{"heading": ..., "body": ...}]` for items to dispatch.

    Raises `EmacsClientError` if emacsclient cannot reach the daemon or the
    elisp helper isn't loaded — callers should treat that as a setup failure,
    not as an empty work queue.
    """
    output = _emacsclient_eval(f'({ELISP_SELECT_FN} "{org_file.resolve()}")')
    return parse_emacsclient_json(output)


def mark_dispatched(org_file: Path, position: int, timestamp: str) -> None:
    """Set `:DISPATCHED: <timestamp>` on the entry at POSITION via emacsclient.

    POSITION is an opaque buffer-offset identifier returned by the selector.
    Using it rather than the heading text avoids mis-marking duplicate-titled
    entries in the same file.

    Failures are logged but swallowed; the next autonomous sweep retries the
    item because the property didn't land.
    """
    try:
        _emacsclient_eval(
            f'({ELISP_MARK_FN} "{org_file.resolve()}" {int(position)} "{timestamp}")'
        )
    except EmacsClientError as exc:
        sys.stderr.write(f"mark_dispatched(pos={position}): {exc}\n")


def dispatch_item(slug: str, prompt: str, agent: str) -> bool:
    """Shell out to `jolo tree`. Return True iff the child exited 0."""
    result = subprocess.run(
        ["jolo", "tree", slug, "-p", prompt, "--agent", agent],
        check=False,
    )
    return result.returncode == 0


def _unique_slugs(items: list[dict], suffix: str = "") -> list[str]:
    """Per-item worktree slugs, disambiguating repeated headings.

    When SUFFIX is non-empty, it is appended so successive runs produce
    distinct worktree names even when the same item is redispatched (e.g.
    after a prior mark failed). Worktree accumulation is managed by
    `jolo prune`.
    """
    seen: dict[str, int] = {}
    slugs: list[str] = []
    for item in items:
        base = build_slug(item["heading"])
        n = seen.get(base, 0)
        disambig = base if n == 0 else f"{base}-{n + 1}"
        slugs.append(f"{disambig}-{suffix}" if suffix else disambig)
        seen[base] = n + 1
    return slugs


def run_autonomous(args: argparse.Namespace) -> None:
    """Scan org-file, dispatch each tagged item in a fresh worktree."""
    git_root = find_git_root()
    if git_root is None:
        sys.exit("Error: jolo autonomous must run inside a git repository")

    config = load_config(project_dir=git_root)
    agents = resolve_agents(
        getattr(args, "agents", None), config.get("agents", ["claude"])
    )

    org_file = Path(args.org_file)
    if not org_file.is_absolute():
        org_file = git_root / org_file

    try:
        items = get_autonomous_items(org_file)
    except EmacsClientError as exc:
        sys.exit(f"Error: {exc}")

    if not items:
        print("No autonomous items to dispatch.")
        return

    pairs = assign_agents(items, agents)
    now = datetime.now(timezone.utc)
    ts = now.strftime("%Y-%m-%dT%H:%M:%SZ")
    slug_suffix = now.strftime("%Y%m%dT%H%M%S")
    slugs = _unique_slugs(items, suffix=slug_suffix)

    if args.dry_run:
        print(f"Would dispatch {len(pairs)} item(s):")
        for (item, agent), slug in zip(pairs, slugs, strict=True):
            preview = (
                item.get("body", "").splitlines()[0][:80]
                if item.get("body")
                else ""
            )
            print(f"  {agent:8s} {slug:40s} {preview}")
        return

    # Dispatch forward (preserves round-robin ordering), then mark in reverse:
    # writing :DISPATCHED: to an earlier heading shifts bytes forward, which
    # would invalidate later items' positions if we marked in file order.
    dispatched_positions: list[int] = []
    for (item, agent), slug in zip(pairs, slugs, strict=True):
        prompt = item.get("body", "").strip() or item["heading"]
        print(f"Dispatching {agent} -> {slug}")
        if dispatch_item(slug=slug, prompt=prompt, agent=agent):
            dispatched_positions.append(item["position"])
        else:
            sys.stderr.write(
                f"dispatch failed for {slug}; leaving undispatched for retry\n"
            )
    for position in reversed(dispatched_positions):
        mark_dispatched(org_file, position, ts)
