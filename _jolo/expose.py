"""jolo expose — temporarily expose one project's dev server to the public.

A host-side Caddy vhost (pub.glvortex.net) reverse-proxies to a loopback
slot port. `expose` runs a foreground socat that forwards the slot to the
selected project's dev port. The project is public only while the command
runs; Ctrl-C tears it down. The single loopback slot allows exactly one
exposed project at a time — a second `expose` fails to bind and exits.
"""

from __future__ import annotations

import socket
import subprocess
import sys

from _jolo import constants
from _jolo.cli import read_port_from_devcontainer
from _jolo.commands import pick_project


def _port_listening(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", port)) == 0


def run_expose_mode(args) -> None:
    """Forward the public slot to a project's dev port until interrupted."""
    project = pick_project()
    port = read_port_from_devcontainer(project)
    if port is None:
        sys.exit(f"No PORT in {project}/.devcontainer/devcontainer.json")

    if not _port_listening(port):
        print(
            f"warning: nothing listening on localhost:{port} — is the dev "
            f"server running in {project.name}?",
            file=sys.stderr,
        )

    slot = constants.EXPOSE_SLOT_PORT
    print(
        f"Exposing {project.name} (:{port}) at {constants.EXPOSE_PUBLIC_URL}"
    )
    print("Ctrl-C to stop.")
    cmd = [
        "socat",
        f"TCP-LISTEN:{slot},bind=127.0.0.1,fork,reuseaddr",
        f"TCP:127.0.0.1:{port}",
    ]
    try:
        subprocess.run(cmd, check=True)
    except KeyboardInterrupt:
        print("\nStopped — no longer public.")
    except subprocess.CalledProcessError:
        sys.exit(
            f"socat failed — is slot {slot} already in use by another "
            "`jolo expose`?"
        )
