"""Peer registry for jolo devcontainers.

Stores a list of running containers at ``<stash>/.jolo/peers.json`` so that
agents inside one devcontainer can introspect other running jolo containers
without needing a connection back to the host podman socket.

Path resolution:
  * Inside a container, the stash is bind-mounted at ``/workspaces/stash``.
  * On the host, the stash lives at ``~/stash``.

Both writers and readers use the same JSON file; the container side reads
it via the shared mount.
"""

from __future__ import annotations

import copy
import json
import os
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

_CONTAINER_STASH = Path("/workspaces/stash")


def registry_path() -> Path:
    """Return the on-disk path to ``peers.json``.

    Prefers the container-side bind mount when present (agents running
    inside devcontainers), otherwise falls back to the host path.
    """
    if _CONTAINER_STASH.is_dir():
        return _CONTAINER_STASH / ".jolo" / "peers.json"
    return Path(os.environ["HOME"]) / "stash" / ".jolo" / "peers.json"


def _load_raw(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    return [e for e in data if isinstance(e, dict) and "container" in e]


def _atomic_write(path: Path, entries: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=path.name + ".", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(entries, f, indent=2, sort_keys=True)
            f.write("\n")
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def read_all() -> list[dict[str, Any]]:
    """Return all registered peer entries (copies, safe to mutate)."""
    entries = _load_raw(registry_path())
    return [copy.deepcopy(e) for e in entries]


def write_entry(entry: dict[str, Any]) -> None:
    """Upsert an entry keyed on ``container`` name."""
    if "container" not in entry:
        raise ValueError("peer entry must include a 'container' key")
    path = registry_path()
    entries = _load_raw(path)
    entries = [e for e in entries if e.get("container") != entry["container"]]
    entries.append(copy.deepcopy(entry))
    _atomic_write(path, entries)


def remove_entry(container: str) -> None:
    """Remove the entry for the given container name. No-op if missing."""
    path = registry_path()
    entries = _load_raw(path)
    new_entries = [e for e in entries if e.get("container") != container]
    if len(new_entries) == len(entries):
        return
    _atomic_write(path, new_entries)


def prune_stale(is_running: Callable[[str], bool]) -> list[str]:
    """Remove entries whose container is no longer running.

    ``is_running`` takes a container name and returns True if it is live.
    Returns the list of removed container names.
    """
    path = registry_path()
    entries = _load_raw(path)
    alive: list[dict[str, Any]] = []
    removed: list[str] = []
    for e in entries:
        name = e.get("container", "")
        if is_running(name):
            alive.append(e)
        else:
            removed.append(name)
    if removed:
        _atomic_write(path, alive)
    return removed
