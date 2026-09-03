"""jolo preview / publish — put a project on the open internet.

Two modes, two wildcards, both terminated on burial:

- ``jolo preview`` gives the running dev server a public hostname at
  ``<name>.dev.glvortex.net`` (basic auth by default). It writes a route
  into the dev Caddy fragment; burial proxies to berghome, hot reload and
  all. Deny-by-default — nothing is exposed unless this command runs.
- ``jolo publish`` releases a static build at ``<name>.pub.glvortex.net``:
  it runs the project's own ``just publish`` recipe in the container
  (contract: output lands in ``dist/``), then rsyncs that to the serving
  host. The release outlives the container.
"""

from __future__ import annotations

import os
import secrets
import subprocess
import sys
from pathlib import Path

from _jolo import constants, sites
from _jolo.cli import (
    clipboard_copy,
    find_git_root,
    get_container_name,
    read_port_from_devcontainer,
)
from _jolo.commands import _fzf_pick, pick_project
from _jolo.container import (
    get_container_for_workspace,
    get_container_runtime,
    is_container_running,
)


def generate_password() -> str:
    """A password you can read over the phone.

    Two 10-word lists: 100 combinations, which a script guesses instantly.
    Chosen for typeability, knowing the hostname is public — Caddy's
    certificates appear in Certificate Transparency logs — so treat a
    previewed site as reachable by anyone who bothers. Widen the word lists
    or append digits if that trade ever stops being acceptable.
    """
    return (
        f"{secrets.choice(constants.ADJECTIVES)}-"
        f"{secrets.choice(constants.NOUNS)}"
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
            "this only works on the host that manages these sites."
        )


def _confirm_no_auth(name: str) -> None:
    print(
        f"{name} will be reachable by anyone on the internet, with no "
        "password, for as long as the container runs.",
        file=sys.stderr,
    )
    try:
        answer = input("Type YES to preview without auth: ")
    except (EOFError, KeyboardInterrupt):
        print()
        sys.exit("Cancelled.")
    if answer != "YES":
        sys.exit("Cancelled.")


def _preview_name(host: str) -> str:
    return host.removesuffix(f".{constants.DEV_SITE_DOMAIN}")


def _site_name(project: Path) -> str:
    """The project's site name, honoring the .jolo.toml name override."""
    try:
        return get_container_name(str(project))
    except ValueError as e:
        sys.exit(f"Error: {e}")


def run_list_previews_mode() -> None:
    """List every preview route, running or not."""
    _require_control_plane()

    routes = sites.read_previews()
    if not routes:
        print("No previews.")
        return

    rows = []
    for host, (port, pw_hash) in sorted(routes.items()):
        owner = sites.owner_of(_preview_name(host))
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


def run_preview_mode(args) -> None:
    """Proxy the current project's dev server at <name>.dev.glvortex.net."""
    if args.list:
        run_list_previews_mode()
        return

    _require_control_plane()

    project = pick_project()
    name = _site_name(project)

    port = read_port_from_devcontainer(project)
    if port is None:
        sys.exit(f"No PORT in {project}/.devcontainer/devcontainer.json")

    owner = sites.owner_of(name)
    if owner is not None and owner != project:
        sys.exit(
            f"{sites.preview_host(name)} would collide with {owner}. "
            "Rename one of the projects."
        )

    if args.no_auth:
        _confirm_no_auth(name)
        pw_hash = None
        password = None
    else:
        existing = sites.read_previews().get(sites.preview_host(name))
        if existing and existing[1] and not args.rotate:
            pw_hash, password = existing[1], None
        else:
            password = generate_password()
            pw_hash = hash_password(password)

    url = sites.register_preview(name, port, pw_hash)
    if url is None:
        sys.exit(f"Could not preview {name}.")

    clipboard_copy(url)
    print(f"Preview:   {url}   (clipboard)")
    if password:
        print(f"Username:  {constants.PUBLIC_AUTH_USER}")
        print(f"Password:  {password}   (shown once)")
    elif args.no_auth:
        print("Auth:      none")
    else:
        print("Auth:      unchanged (use --rotate for a new password)")
    print()
    print(
        f"If the dev server rejects the request, add {sites.preview_host(name)} "
        "to its allowed hosts."
    )


def _pick_previewed(routes: dict[str, tuple[int, str | None]]) -> str:
    """Which project to unpreview.

    The generic project picker offers everything jolo knows about, which
    for unpreviewing is noise — only previewed sites are candidates.
    """
    git_root = find_git_root()
    if git_root is not None:
        return _site_name(git_root)

    names = sorted(_preview_name(host) for host in routes)
    if len(names) == 1:
        return names[0]

    labels = [f"{name:<24} {sites.preview_host(name)}" for name in names]
    selected = _fzf_pick("Unpreview which site:", labels)
    if selected is None:
        sys.exit(0)
    return names[labels.index(selected)]


def run_unpreview_mode(args) -> None:
    """Remove a project's public dev-preview route."""
    _require_control_plane()

    routes = sites.read_previews()
    if not routes:
        print("No previews.")
        return

    name = _pick_previewed(routes)
    if sites.unregister_preview(name):
        print(f"Unpreviewed: {sites.preview_host(name)}")
    else:
        print(f"Not previewed: {sites.preview_host(name)}")


def _remote_dir(name: str) -> str:
    return f"{constants.PUBLISH_ROOT}/{sites.publish_host(name)}"


def _build_in_container(project: Path) -> None:
    """Run the project's own build where the toolchain lives."""
    runtime = get_container_runtime()
    container = get_container_for_workspace(project)
    if (
        runtime is None
        or container is None
        or not is_container_running(project)
    ):
        sys.exit(f"No running container for {project.name}; jolo up first.")

    result = subprocess.run(
        [
            runtime,
            "exec",
            "-u",
            os.environ.get("USER", "dev"),
            "-w",
            f"/workspaces/{project.name}",
            container,
            "just",
            "publish",
        ]
    )
    if result.returncode != 0:
        sys.exit("just publish failed.")


def _released_names() -> list[str]:
    result = subprocess.run(
        ["ssh", constants.PUBLISH_HOST, "ls", "-1", constants.PUBLISH_ROOT],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        sys.exit(
            f"Could not list {constants.PUBLISH_HOST}:{constants.PUBLISH_ROOT}: "
            f"{result.stderr.strip()}"
        )
    suffix = f".{constants.PUBLIC_SITE_DOMAIN}"
    return sorted(
        line.removesuffix(suffix)
        for line in result.stdout.split()
        if line.endswith(suffix)
    )


def run_list_released_mode() -> None:
    """List every released static site on the serving host."""
    names = _released_names()
    if not names:
        print("Nothing published.")
        return
    for name in names:
        print(f"https://{sites.publish_host(name)}")


def run_publish_mode(args) -> None:
    """Release the current project's static build at <name>.pub.glvortex.net."""
    if args.list:
        run_list_released_mode()
        return

    _require_control_plane()

    project = pick_project()
    name = _site_name(project)

    if not sites.is_dns_label(name):
        sys.exit(f"{name!r} is not a DNS label; it cannot become a site.")

    owner = sites.owner_of(name)
    if owner is not None and owner != project:
        sys.exit(
            f"{sites.publish_host(name)} would collide with {owner}. "
            "Rename one of the projects."
        )

    _build_in_container(project)

    dist = project / "dist"
    if not dist.is_dir() or not any(dist.iterdir()):
        sys.exit(f"just publish left nothing in {dist}.")

    dest = f"{constants.PUBLISH_HOST}:{_remote_dir(name)}/"
    result = subprocess.run(["rsync", "-a", "--delete", f"{dist}/", dest])
    if result.returncode != 0:
        sys.exit(f"rsync to {dest} failed.")

    url = f"https://{sites.publish_host(name)}"
    clipboard_copy(url)
    print(f"Published: {url}   (clipboard)")


def _pick_released() -> str:
    git_root = find_git_root()
    if git_root is not None:
        return _site_name(git_root)

    names = _released_names()
    if not names:
        sys.exit("Nothing published.")
    if len(names) == 1:
        return names[0]

    labels = [f"{name:<24} {sites.publish_host(name)}" for name in names]
    selected = _fzf_pick("Unpublish which site:", labels)
    if selected is None:
        sys.exit(0)
    return names[labels.index(selected)]


def run_unpublish_mode(args) -> None:
    """Remove a released static site from the serving host."""
    _require_control_plane()

    name = _pick_released()
    if not sites.is_dns_label(name):
        sys.exit(f"{name!r} is not a DNS label; nothing to unpublish.")

    host = sites.publish_host(name)
    remote = _remote_dir(name)
    result = subprocess.run(
        ["ssh", constants.PUBLISH_HOST, f"test -d {remote} && rm -rf {remote}"]
    )
    if result.returncode == 0:
        print(f"Unpublished: {host}")
    elif result.returncode == 255:
        sys.exit(f"ssh {constants.PUBLISH_HOST} failed.")
    else:
        print(f"Not published: {host}")
