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
    # Defensive: older elisp may emit "null" when no items match.
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


def get_autonomous_items(org_file: Path) -> list[dict]:
    """Return `[{"heading": ..., "body": ...}]` for items to dispatch.

    If the org file is missing, return `[]` without invoking emacsclient.
    """
    org_path = (
        org_file.resolve() if org_file.is_absolute() else Path.cwd() / org_file
    )
    if not org_path.exists():
        return []
    elisp = f'({ELISP_SELECT_FN} "{org_path}")'
    result = subprocess.run(
        ["emacsclient", "-e", elisp],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        sys.stderr.write(
            f"emacsclient failed ({result.returncode}): {result.stderr.strip()}\n"
        )
        return []
    return parse_emacsclient_json(result.stdout)


def mark_dispatched(org_file: Path, heading: str, timestamp: str) -> None:
    """Set `:DISPATCHED: <timestamp>` on the given heading via emacsclient."""
    org_path = (
        org_file.resolve() if org_file.is_absolute() else Path.cwd() / org_file
    )
    elisp = (
        f'({ELISP_MARK_FN} "{org_path}" '
        f'"{_elisp_escape(heading)}" "{timestamp}")'
    )
    result = subprocess.run(
        ["emacsclient", "-e", elisp],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        sys.stderr.write(
            f"failed to mark dispatched ({result.returncode}): {result.stderr.strip()}\n"
        )


def _elisp_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')


def dispatch_item(slug: str, prompt: str, agent: str) -> bool:
    """Shell out to `jolo tree`. Return True iff the child exited 0."""
    result = subprocess.run(
        ["jolo", "tree", slug, "-p", prompt, "--agent", agent],
        check=False,
    )
    return result.returncode == 0


def run_autonomous(args: argparse.Namespace) -> None:
    """Scan org-file, dispatch each tagged item in a fresh worktree."""
    config = load_config()
    agents = resolve_agents(
        getattr(args, "agents", None), config.get("agents", ["claude"])
    )

    git_root = find_git_root()
    if git_root is None:
        sys.exit("Error: jolo autonomous must run inside a git repository")
    org_file = Path(args.org_file)
    if not org_file.is_absolute():
        org_file = git_root / org_file

    items = get_autonomous_items(org_file)

    if not items:
        print("No autonomous items to dispatch.")
        return

    pairs = assign_agents(items, agents)

    if args.dry_run:
        print(f"Would dispatch {len(pairs)} item(s):")
        for item, agent in pairs:
            slug = build_slug(item["heading"])
            preview = (
                item.get("body", "").splitlines()[0][:80]
                if item.get("body")
                else ""
            )
            print(f"  {agent:8s} {slug:40s} {preview}")
        return

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for item, agent in pairs:
        slug = build_slug(item["heading"])
        prompt = item.get("body", "").strip() or item["heading"]
        print(f"Dispatching {agent} -> {slug}")
        if dispatch_item(slug=slug, prompt=prompt, agent=agent):
            mark_dispatched(org_file, item["heading"], ts)
        else:
            sys.stderr.write(
                f"dispatch failed for {slug}; leaving undispatched for retry\n"
            )
