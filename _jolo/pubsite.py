"""jolo publish — give a project a stable public hostname.

Writes one explicit Caddy site block per published project, which is what
makes per-name HTTP-01 issuance work: no wildcard certificate, no DNS-01.
Deny-by-default — nothing is published unless this command runs.
"""

from __future__ import annotations

import secrets
import subprocess
import sys

from _jolo import constants, sites
from _jolo.cli import read_port_from_devcontainer
from _jolo.commands import pick_project
from _jolo.container import is_container_running


def generate_password() -> str:
    """A password you can read over the phone.

    Deliberately weak at roughly 20 bits: two 10-word lists plus four
    digits. Chosen for typeability over strength, knowing the hostname is
    public — Caddy's certificates appear in Certificate Transparency logs,
    so basic auth is the only barrier. Widen the word lists if that trade
    ever stops being acceptable.
    """
    return (
        f"{secrets.choice(constants.ADJECTIVES)}-"
        f"{secrets.choice(constants.NOUNS)}-"
        f"{secrets.randbelow(9000) + 1000}"
    )


def hash_password(plaintext: str) -> str:
    """Bcrypt a password with Caddy's own hasher.

    Passed on stdin, never argv: a password in a command line lands in the
    process list and in shell history.
    """
    try:
        result = subprocess.run(
            ["caddy", "hash-password"],
            # Trailing newline required: off a terminal, caddy reads one
            # line from stdin and reports a bare "EOF" without it.
            input=plaintext + "\n",
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        sys.exit("caddy binary not found; cannot hash a password.")
    if result.returncode != 0:
        sys.exit(f"caddy hash-password failed: {result.stderr.strip()}")
    return result.stdout.strip()


def _require_control_plane() -> None:
    if not sites.is_available():
        sys.exit(
            f"No tailnet control plane at {sites.control_dir()} — "
            "publishing only works on the host that serves these sites."
        )


def _confirm_no_auth(name: str) -> None:
    print(
        f"{name} will be reachable by anyone on the internet, with no "
        "password, for as long as the container runs.",
        file=sys.stderr,
    )
    try:
        answer = input("Type YES to publish without auth: ")
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit("Cancelled.")
    if answer != "YES":
        sys.exit("Cancelled.")


def _project_name(host: str) -> str:
    return host.removesuffix(f".{constants.PUBLIC_SITE_DOMAIN}")


def run_list_published_mode() -> None:
    """List every published site, running or not."""
    _require_control_plane()

    routes = sites.read_public()
    if not routes:
        print("Nothing published.")
        return

    rows = []
    for host, (port, pw_hash) in sorted(routes.items()):
        owner = sites.owner_of(_project_name(host))
        if owner is None:
            container = "unknown"
        else:
            container = "running" if is_container_running(owner) else "stopped"
        rows.append(
            (host, str(port), "auth" if pw_hash else "NO AUTH", container)
        )

    width = max(len(r[0]) for r in rows)
    print(f"{'HOST':<{width}}  PORT   AUTH      CONTAINER")
    for host, port, auth, container in rows:
        print(f"{host:<{width}}  {port:<5}  {auth:<8}  {container}")


def run_publish_mode(args) -> None:
    """Publish the current project at <name>.pub.glvortex.net."""
    if args.list:
        run_list_published_mode()
        return

    _require_control_plane()

    project = pick_project()
    name = project.name

    port = read_port_from_devcontainer(project)
    if port is None:
        sys.exit(f"No PORT in {project}/.devcontainer/devcontainer.json")

    owner = sites.owner_of(name)
    if owner is not None and owner != project:
        sys.exit(
            f"{sites.public_host(name)} would collide with {owner}. "
            "Rename one of the projects."
        )

    if args.no_auth:
        _confirm_no_auth(name)
        pw_hash = None
        password = None
    else:
        existing = sites.read_public().get(sites.public_host(name))
        if existing and existing[1] and not args.rotate:
            pw_hash, password = existing[1], None
        else:
            password = generate_password()
            pw_hash = hash_password(password)

    url = sites.register_public(name, port, pw_hash)
    if url is None:
        sys.exit(f"Could not publish {name}.")

    print(f"Published: {url}")
    if password:
        print(f"Username:  {constants.PUBLIC_AUTH_USER}")
        print(f"Password:  {password}   (shown once)")
    elif args.no_auth:
        print("Auth:      none")
    else:
        print("Auth:      unchanged (use --rotate for a new password)")
    print()
    print(
        "The certificate is issued on first request and takes a few seconds."
    )
    print(
        f"If the dev server rejects the request, add {sites.public_host(name)} "
        "to its allowed hosts."
    )


def run_unpublish_mode(args) -> None:
    """Remove the current project's public route."""
    _require_control_plane()

    project = pick_project()
    name = project.name
    if sites.unregister_public(name):
        print(f"Unpublished: {sites.public_host(name)}")
    else:
        print(f"Not published: {sites.public_host(name)}")
