"""Per-project HTTPS sites on the tailnet.

Two generated fragments under ``/srv/tailnet`` are the whole control plane:
a Caddy route (berghome serves the app on ``127.0.0.1:$PORT``) and a
Headscale ``A`` record (the name resolves to burial, which terminates TLS
with the wildcard cert and proxies to berghome). Syncthing carries both
files to those hosts, where systemd path units reload the services — so
jolo only ever writes files, never needs sudo, SSH, or a host round-trip.

Both files are wholly owned by jolo: they are re-rendered from the parsed
route/record set, which is what keeps repeated ``jolo up`` runs idempotent
and stops duplicate blocks accumulating.
"""

from __future__ import annotations

import json
import os
import re
import sys
import tempfile
from pathlib import Path

from _jolo import constants

CADDY_RELPATH = "caddy/jolo-sites.caddy"
RECORDS_RELPATH = "headscale/jolo-extra-records.json"

CADDY_HEADER = (
    "# Generated jolo tailnet project routes for berghome.\n"
    "# Imported from /etc/caddy/Caddyfile via /etc/caddy/conf.d/*.\n"
)

# One DNS label: the intersection of what Caddy, Headscale, and the
# wildcard certificate all accept. Project directories are free-form, so
# plenty of legal project names simply cannot become sites.
_LABEL = re.compile(r"^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?$")

_ROUTE = re.compile(
    r"^http://(?P<host>[^\s{]+)\s*\{\s*"
    r"reverse_proxy\s+127\.0\.0\.1:(?P<port>\d+)\s*\}",
    re.MULTILINE,
)


def control_dir() -> Path:
    return Path(constants.TAILNET_CONTROL_DIR)


def _caddy_path() -> Path:
    return control_dir() / CADDY_RELPATH


def _records_path() -> Path:
    return control_dir() / RECORDS_RELPATH


def is_available() -> bool:
    """True when this host carries the shared control-plane fragments."""
    return _caddy_path().is_file() and _records_path().is_file()


def site_host(name: str) -> str:
    return f"{name}.{constants.TAILNET_SITE_DOMAIN}"


def _write_atomic(path: Path, text: str) -> None:
    """Replace path in one step so Syncthing never ships a half-written file."""
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.")
    try:
        with os.fdopen(fd, "w") as fh:
            fh.write(text)
        os.chmod(tmp, 0o644)
        os.replace(tmp, path)
    except BaseException:
        Path(tmp).unlink(missing_ok=True)
        raise


def read_routes() -> dict[str, int]:
    """Parse the Caddy fragment into ``{hostname: port}``."""
    text = _caddy_path().read_text()
    return {
        m.group("host"): int(m.group("port")) for m in _ROUTE.finditer(text)
    }


def _write_routes(routes: dict[str, int]) -> None:
    blocks = [
        f"http://{host} {{\n    reverse_proxy 127.0.0.1:{port}\n}}\n"
        for host, port in sorted(routes.items())
    ]
    _write_atomic(_caddy_path(), CADDY_HEADER + "\n".join(blocks))


def read_records() -> list[dict]:
    return json.loads(_records_path().read_text())


def _write_records(records: list[dict]) -> None:
    # Headscale watches this file and checksums it to decide whether to
    # reprocess, so the output has to be stable across runs — hence the
    # sort. No restart is needed on its side.
    ordered = sorted(records, key=lambda r: r.get("name", ""))
    _write_atomic(
        _records_path(), json.dumps(ordered, indent=2, sort_keys=True) + "\n"
    )


def register(name: str, port: int) -> str | None:
    """Point ``name`` at ``port``, adding or correcting both fragments.

    Returns the site URL, or None when this host has no control plane or
    the project name cannot be a DNS label.
    """
    if not is_available():
        return None
    if not _LABEL.match(name):
        print(
            f"jolo: skipping tailnet site, {name!r} is not a DNS label",
            file=sys.stderr,
        )
        return None

    host = site_host(name)

    routes = read_routes()
    if routes.get(host) != port:
        routes[host] = port
        _write_routes(routes)

    records = read_records()
    wanted = {
        "name": host,
        "type": "A",
        "value": constants.TAILNET_ROUTER_IP,
    }
    if wanted not in records:
        records = [r for r in records if r.get("name") != host]
        records.append(wanted)
        _write_records(records)

    return f"https://{host}"


def unregister(name: str) -> bool:
    """Drop ``name`` from both fragments. True if anything was removed."""
    if not is_available():
        return False

    host = site_host(name)
    changed = False

    routes = read_routes()
    if host in routes:
        del routes[host]
        _write_routes(routes)
        changed = True

    records = read_records()
    kept = [r for r in records if r.get("name") != host]
    if len(kept) != len(records):
        _write_records(kept)
        changed = True

    return changed
