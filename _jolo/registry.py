"""Persistent registry of project paths jolo has touched.

Lets `jolo a` resurface containers that podman no longer knows about
(e.g. after a host-side `podman system reset` or storage wipe). The
registry is advisory — `_pick_container` still trusts podman first
and uses this only as a fallback union.
"""

import json
import os
import time
from pathlib import Path

_REGISTRY_PATH = Path.home() / ".config" / "jolo" / "known-projects.json"


def _load_raw() -> dict[str, dict]:
    try:
        data = json.loads(_REGISTRY_PATH.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {k: v for k, v in data.items() if isinstance(v, dict)}


def _atomic_write(data: dict[str, dict]) -> None:
    _REGISTRY_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = _REGISTRY_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True))
    os.replace(tmp, _REGISTRY_PATH)


def record(path: Path) -> None:
    """Record a project path as known. Idempotent; bumps last_seen."""
    key = str(Path(path).resolve())
    data = _load_raw()
    data[key] = {"last_seen": time.time()}
    _atomic_write(data)


def known_paths() -> list[tuple[Path, float]]:
    """Return [(path, last_seen)] for entries that still exist on disk
    and have a `.devcontainer/devcontainer.json`. Prunes missing entries
    from the registry as a side effect.
    """
    data = _load_raw()
    alive: list[tuple[Path, float]] = []
    pruned = False
    for key, entry in list(data.items()):
        path = Path(key)
        if (path / ".devcontainer" / "devcontainer.json").exists():
            alive.append((path, float(entry.get("last_seen", 0))))
        else:
            del data[key]
            pruned = True
    if pruned:
        _atomic_write(data)
    return alive
