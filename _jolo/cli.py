"""Utility functions and CLI argument parsing for jolo."""

import argparse
import contextlib
import fcntl
import json
import os
import random
import re
import socket
import subprocess
import sys
from pathlib import Path

try:
    import argcomplete
except ImportError:
    pass

import base64

from _jolo import constants


def clipboard_copy(text: str) -> None:
    """Copy text to the system clipboard via OSC 52 escape sequence."""
    encoded = base64.b64encode(text.encode()).decode()
    try:
        with open("/dev/tty", "w") as tty:
            tty.write(f"\033]52;c;{encoded}\a")
    except OSError:
        pass


def random_port() -> int:
    """Pick a random port in the PORT_MIN-PORT_MAX range.

    Leaves room for WORKTREE_PORTS extra ports above the base port.
    """
    stride = constants.WORKTREE_PORTS + 1
    slot = random.randint(
        0, (constants.PORT_MAX - constants.PORT_MIN) // stride - 1
    )
    return constants.PORT_MIN + slot * stride


def is_port_available(port: int) -> bool:
    """Check if a TCP port and its worktree range are available on the host."""
    for p in range(port, port + constants.WORKTREE_PORTS + 1):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("", p))
            except OSError:
                return False
    return True


def detect_hostname() -> str:
    """Detect the host's Tailscale hostname, with fallback to localhost.

    Checks (in order):
    1. DEV_HOST environment variable (explicit override)
    2. Tailscale DNS name via `tailscale status --self --json`
    3. Falls back to "localhost"
    """
    env_host = os.environ.get("DEV_HOST")
    if env_host:
        return env_host

    try:
        result = subprocess.run(
            ["tailscale", "status", "--self", "--json"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            dns_name = data.get("Self", {}).get("DNSName", "")
            if dns_name:
                return dns_name.rstrip(".")
    except (
        FileNotFoundError,
        subprocess.TimeoutExpired,
        json.JSONDecodeError,
    ):
        pass

    return "localhost"


def read_port_from_devcontainer(workspace_dir: Path) -> int | None:
    """Read the PORT from an existing devcontainer.json, if present."""
    devcontainer_json = workspace_dir / ".devcontainer" / "devcontainer.json"
    if not devcontainer_json.exists():
        return None
    try:
        config = json.loads(devcontainer_json.read_text())
        port_str = config.get("containerEnv", {}).get("PORT")
        return int(port_str) if port_str else None
    except (json.JSONDecodeError, ValueError, TypeError):
        return None


def verbose_print(msg: str) -> None:
    """Print message if verbose mode is enabled."""
    if constants.VERBOSE:
        print(f"[verbose] {msg}", file=sys.stderr)


def select_flavors_interactive() -> list[str]:
    """Show interactive multi-select picker for project flavors.

    Returns:
        List of selected flavor codes, e.g. ['python-web', 'typescript'].
        First selected = primary flavor. Returns empty list if user cancels.
    """
    try:
        result = subprocess.run(
            [
                "fzf",
                "--multi",
                "--header",
                "Select project flavor(s) (Tab to multi-select):",
                "--height",
                "~15",
                "--layout",
                "reverse",
            ],
            input="\n".join(constants.VALID_FLAVORS),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return []
        return [
            f
            for f in result.stdout.rstrip("\n").splitlines()
            if f in constants.VALID_FLAVORS
        ]
    except KeyboardInterrupt:
        return []


def detect_flavors(project_dir: Path) -> list[str]:
    """Auto-detect project flavors from files in the directory.

    Returns list of detected flavor codes, e.g. ['python-web', 'typescript'].
    """
    # The jolo meta-project itself is a unique flavor: a CLI whose
    # `templates/` dir holds project scaffolding (not Jinja templates),
    # so the python-web heuristic below would otherwise mis-fire and
    # stomp this repo's bespoke justfile on `--recreate --force`.
    if (project_dir / "jolo.py").is_file() and (
        project_dir / "_jolo" / "__init__.py"
    ).is_file():
        return ["meta"]

    flavors = []

    pyproject = project_dir / "pyproject.toml"
    has_py = pyproject.exists() or any(project_dir.glob("*.py"))
    has_ts = (project_dir / "package.json").exists() or (
        project_dir / "tsconfig.json"
    ).exists()
    has_go = (project_dir / "go.mod").exists()
    has_rust = (project_dir / "Cargo.toml").exists()
    has_shell = any(project_dir.glob("*.sh"))

    # Detect web vs bare by looking for common web indicators.
    # Frontend-shaped projects: a templates/static/components dir.
    # Python backends: a web framework dependency in pyproject.toml.
    web_indicators = [
        "templates",
        "static",
        "public",
        "src/pages",
        "src/components",
    ]
    has_web = any((project_dir / d).exists() for d in web_indicators)
    if has_py and not has_web and pyproject.exists():
        try:
            pyproject_text = pyproject.read_text(errors="replace").lower()
        except OSError:
            pyproject_text = ""
        # Match the package name as a quoted token to avoid false hits
        # in unrelated keys/values.
        py_web_frameworks = (
            "fastapi",
            "flask",
            "django",
            "starlette",
            "sanic",
            "aiohttp",
            "litestar",
            "quart",
            "bottle",
        )
        for fw in py_web_frameworks:
            if f'"{fw}' in pyproject_text or f"'{fw}" in pyproject_text:
                has_web = True
                break

    if has_py:
        flavors.append("python-web" if has_web else "python")
    if has_ts:
        flavors.append("typescript-web" if has_web else "typescript")
    if has_go:
        flavors.append("go-web" if has_web else "go")
    if has_rust:
        flavors.append("rust-web" if has_web else "rust")
    if has_shell and not flavors:
        flavors.append("shell")

    return flavors


def parse_flavor_arg(value: str) -> list[str]:
    """Parse and validate --flavor argument.

    Accepts comma-separated flavor names, strips whitespace, validates
    each flavor against VALID_FLAVORS.

    Args:
        value: Comma-separated string of flavor names

    Returns:
        List of validated flavor names

    Raises:
        argparse.ArgumentTypeError: If any flavor is invalid
    """
    flavors = [f.strip() for f in value.split(",")]
    invalid = [f for f in flavors if f not in constants.VALID_FLAVORS]
    if invalid:
        valid_list = ", ".join(sorted(constants.VALID_FLAVORS))
        raise argparse.ArgumentTypeError(
            f"Invalid flavor(s): {', '.join(invalid)}. Valid options: {valid_list}"
        )
    return flavors


def parse_mount(arg: str, project_name: str) -> dict:
    """Parse mount argument into structured data.

    Syntax:
        source:target        - relative target, read-write
        source:target:ro     - relative target, read-only
        source:/abs/target   - absolute target
        source:/abs/target:ro - absolute target, read-only

    Returns dict with keys: source, target, readonly
    """
    parts = arg.split(":")
    readonly = False

    # Check for :ro suffix
    if len(parts) >= 2 and parts[-1] == "ro":
        readonly = True
        parts = parts[:-1]

    if len(parts) < 2:
        sys.exit(
            f"Error: Invalid mount syntax: {arg} (expected source:target)"
        )

    # Handle Windows-style paths or paths with colons
    source = parts[0]
    target = ":".join(parts[1:])

    # Expand ~ in source
    source = os.path.expanduser(source)

    # Resolve target: absolute if starts with /, else relative to workspace
    if not target.startswith("/"):
        target = f"/workspaces/{project_name}/{target}"

    return {"source": source, "target": target, "readonly": readonly}


def parse_copy(arg: str, project_name: str) -> dict:
    """Parse copy argument into structured data.

    Syntax:
        source:target  - copy to target path
        source         - copy to workspace with original basename

    Returns dict with keys: source, target
    """
    if ":" in arg:
        # Split on first colon only (in case target has colons)
        parts = arg.split(":", 1)
        source = parts[0]
        target = parts[1]
    else:
        source = arg
        target = None

    # Expand ~ in source
    source = os.path.expanduser(source)

    # Resolve target
    if target is None:
        # Use basename of source
        target = f"/workspaces/{project_name}/{Path(source).name}"
    elif not target.startswith("/"):
        # Relative target - prepend workspace
        target = f"/workspaces/{project_name}/{target}"

    return {"source": source, "target": target}


def verbose_cmd(cmd: list[str]) -> None:
    """Print command if verbose mode is enabled."""
    if constants.VERBOSE:
        print(f"[verbose] $ {' '.join(cmd)}", file=sys.stderr)


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse command-line arguments."""
    # --- Reusable parent parsers (no help to avoid duplicate -h) ---
    # Each groups related flags so subcommands pick only what they need.

    p_verbose = argparse.ArgumentParser(add_help=False)
    p_verbose.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Print commands being executed",
    )

    p_prompt = argparse.ArgumentParser(add_help=False)
    p_prompt.add_argument(
        "--prompt",
        "-p",
        metavar="PROMPT",
        help="Start AI agent with this prompt (implies --detach)",
    )
    p_prompt.add_argument(
        "--agent",
        default="claude",
        metavar="CMD",
        help="AI agent command (default: claude)",
    )

    p_detach = argparse.ArgumentParser(add_help=False)
    p_detach.add_argument(
        "--detach",
        "-d",
        action="store_true",
        help="Start container without attaching",
    )

    p_exec = argparse.ArgumentParser(add_help=False)
    p_exec.add_argument(
        "--shell",
        action="store_true",
        help="Exec into container with zsh (no tmux)",
    )
    p_exec.add_argument(
        "--run",
        metavar="CMD",
        help="Exec command directly in container (no tmux)",
    )

    p_mounts = argparse.ArgumentParser(add_help=False)
    p_mounts.add_argument(
        "--mount",
        action="append",
        default=[],
        metavar="SRC:DST[:ro]",
        help="Mount host path into container (repeatable)",
    )
    p_mounts.add_argument(
        "--copy",
        action="append",
        default=[],
        metavar="SRC[:DST]",
        help="Copy file to workspace before start (repeatable)",
    )

    p_recreate = argparse.ArgumentParser(add_help=False)
    p_recreate.add_argument(
        "--recreate",
        action="store_true",
        help="Sync config from template and recreate the container",
    )
    p_recreate.add_argument(
        "--force",
        action="store_true",
        help=(
            "Retrofit template files that jolo never tracked (no hash "
            "record). Drops {file}.jolonew alongside existing files so "
            "you can diff and merge. Use when pulling in new recipes "
            "like `just perf` for a project created before the current "
            "template."
        ),
    )

    p_all = argparse.ArgumentParser(add_help=False)
    p_all.add_argument(
        "--all",
        "-a",
        action="store_true",
        help="Show/act on all (globally or for project)",
    )

    p_yes = argparse.ArgumentParser(add_help=False)
    p_yes.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Skip confirmation prompts",
    )

    # --- Main parser ---
    parser = argparse.ArgumentParser(
        prog="jolo",
        usage="jolo <command> [options]",
        description="Devcontainer + Git Worktree Launcher",
        epilog="Run 'jolo <command> --help' for command-specific options.\n\n"
        "Examples: jolo up | jolo create foo | jolo clone <url> | jolo list | "
        "jolo tree feat-x | jolo down --all | jolo spawn 3 -p 'do thing' | "
        "jolo research 'topic'",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    # Defaults so attributes exist even when no subcommand is given
    parser.set_defaults(
        prompt=None,
        agent="claude",
        from_branch=None,
        prefix=None,
        all=False,
        recreate=False,
        force=False,
        detach=False,
        shell=False,
        run=None,
        mount=[],
        copy=[],
        flavor=None,
        yes=False,
        verbose=False,
        purge=False,
        target=None,
        deep=False,
    )

    subparsers = parser.add_subparsers(dest="command", prog="jolo")

    # up: prompt, agent, detach, exec, mounts, recreate, verbose
    subparsers.add_parser(
        "up",
        parents=[
            p_verbose,
            p_prompt,
            p_detach,
            p_exec,
            p_mounts,
            p_recreate,
        ],
        help="Start devcontainer in current project",
    )

    # create: prompt, agent, detach, exec, mounts, lang, verbose
    sub_create = subparsers.add_parser(
        "create",
        parents=[p_verbose, p_prompt, p_detach, p_exec, p_mounts],
        help="Create new project with git + devcontainer",
    )
    sub_create.add_argument("name", help="Project name")
    sub_create.add_argument(
        "--flavor",
        type=parse_flavor_arg,
        default=None,
        metavar="FLAVOR[,...]",
        help="Project flavor(s): typescript-web, typescript, go-web, go, python-web, python, rust-web, rust, shell, prose, other",
    )

    # clone: prompt, agent, detach, exec, mounts, recreate, verbose
    sub_clone = subparsers.add_parser(
        "clone",
        parents=[
            p_verbose,
            p_prompt,
            p_detach,
            p_exec,
            p_mounts,
            p_recreate,
        ],
        help="Clone repo and start devcontainer",
    )
    sub_clone.add_argument("url", help="Git repository URL")
    sub_clone.add_argument(
        "name",
        nargs="?",
        default=None,
        help="Directory name (default: inferred from URL)",
    )

    # tree: prompt, agent, detach, exec, mounts, recreate, from, verbose
    sub_tree = subparsers.add_parser(
        "tree",
        parents=[
            p_verbose,
            p_prompt,
            p_detach,
            p_exec,
            p_mounts,
            p_recreate,
        ],
        help="Create worktree + devcontainer (random name if omitted)",
    )
    sub_tree.add_argument("name", nargs="?", default="", help="Worktree name")
    sub_tree.add_argument(
        "--from",
        dest="from_branch",
        metavar="BRANCH",
        help="Create worktree from specified branch",
    )

    # spawn: prompt, agent, from, prefix, mounts, recreate, verbose
    sub_spawn = subparsers.add_parser(
        "spawn",
        parents=[p_verbose, p_prompt, p_mounts, p_recreate],
        help="Create N worktrees in parallel, each with its own agent",
    )
    sub_spawn.add_argument("count", type=int, help="Number of worktrees")
    sub_spawn.add_argument(
        "--from",
        dest="from_branch",
        metavar="BRANCH",
        help="Create worktrees from specified branch",
    )
    sub_spawn.add_argument(
        "--prefix",
        metavar="NAME",
        help="Prefix for worktree names (feat -> feat-1, feat-2, ...)",
    )

    # list: all, verbose
    subparsers.add_parser(
        "list",
        parents=[p_verbose, p_all],
        help="List running containers and worktrees",
    )

    # status: verbose
    subparsers.add_parser(
        "status",
        parents=[p_verbose],
        help="Project dashboard: containers, worktrees, ports, disk",
    )

    # doctor: verbose
    subparsers.add_parser(
        "doctor",
        parents=[p_verbose],
        help="Pre-flight check: runtime, image, ports, tools, API keys",
    )

    # attach: recreate, verbose
    subparsers.add_parser(
        "attach",
        aliases=["a"],
        parents=[p_verbose, p_recreate],
        help="Pick a running container and attach to it",
    )

    # down: all, verbose
    subparsers.add_parser(
        "down", parents=[p_verbose, p_all], help="Stop the devcontainer"
    )

    # init: prompt, agent, detach, exec, mounts, recreate, verbose
    subparsers.add_parser(
        "init",
        parents=[p_verbose, p_prompt, p_detach, p_exec, p_mounts, p_recreate],
        help="Initialize git + devcontainer in current directory",
    )

    # prune: all, yes, verbose
    subparsers.add_parser(
        "prune",
        parents=[p_verbose, p_all, p_yes],
        help="Clean up stopped/orphan containers and stale worktrees",
    )

    # research: prompt, agent, verbose
    sub_research = subparsers.add_parser(
        "research",
        parents=[p_verbose],
        help="Run research in persistent container",
    )
    sub_research.add_argument(
        "prompt", nargs="?", default=None, help="Research topic or question"
    )
    sub_research.add_argument(
        "--agent",
        default=None,
        metavar="CMD",
        help="AI agent to use (default: random)",
    )
    sub_research.add_argument(
        "--file",
        default=None,
        metavar="PATH",
        help="Read prompt from file",
    )
    sub_research.add_argument(
        "--deep",
        action="store_true",
        default=False,
        help="Run multiple agents in parallel, then synthesize findings",
    )
    # exec: verbose
    sub_exec = subparsers.add_parser(
        "exec",
        parents=[p_verbose],
        help="Run a command in the running devcontainer",
    )
    sub_exec.add_argument(
        "exec_command",
        nargs=argparse.REMAINDER,
        help="Command to run inside the container",
    )
    # port: port number, random
    sub_port = subparsers.add_parser(
        "port",
        parents=[p_verbose],
        help="Show or change the project port",
    )
    sub_port.add_argument(
        "port",
        nargs="?",
        default=None,
        type=int,
        help="Port number to assign",
    )
    sub_port.add_argument(
        "--random",
        action="store_true",
        help="Assign a new random port",
    )
    # autonomous: scan TODO.org for :autonomous: items and dispatch them
    sub_autonomous = subparsers.add_parser(
        "autonomous",
        parents=[p_verbose],
        help="Dispatch :autonomous:-tagged TODO items as fresh worktrees",
    )
    sub_autonomous.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would fire, without dispatching or marking",
    )
    sub_autonomous.add_argument(
        "--agents",
        default=None,
        metavar="LIST",
        help="Comma-separated agent list for round-robin (default: config)",
    )
    sub_autonomous.add_argument(
        "--org-file",
        default="docs/TODO.org",
        metavar="PATH",
        help="Path to TODO.org (default: docs/TODO.org)",
    )

    # delete: target, purge, yes, verbose
    sub_delete = subparsers.add_parser(
        "delete",
        parents=[p_verbose, p_yes],
        help="Delete a worktree or project and its container",
    )
    sub_delete.add_argument(
        "target",
        nargs="?",
        default=None,
        help="Worktree name or project path (interactive if omitted)",
    )
    sub_delete.add_argument(
        "--purge",
        action="store_true",
        help="Also remove project directories from disk",
    )

    # publish: scrub, dry-run, yes, verbose
    sub_publish = subparsers.add_parser(
        "publish",
        parents=[p_verbose, p_yes],
        help="Flip project to public-notes mode (docs/ as nested private repo)",
    )
    sub_publish.add_argument(
        "--scrub",
        action="store_true",
        help="Also run git-filter-repo to remove memory/notes from history (destructive)",
    )
    sub_publish.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the plan without making changes",
    )

    # allow: opt a project into a gated capability
    sub_allow = subparsers.add_parser(
        "allow",
        parents=[p_verbose],
        help="Opt a project into a gated capability (e.g. cross-container podman)",
    )
    sub_allow.add_argument(
        "feature", choices=["podman"], help="Capability to enable"
    )
    sub_allow.add_argument(
        "project", help="Project name (matches the devcontainer name)"
    )

    # deny: opt a project out of a gated capability
    sub_deny = subparsers.add_parser(
        "deny",
        parents=[p_verbose],
        help="Opt a project out of a gated capability",
    )
    sub_deny.add_argument(
        "feature", choices=["podman"], help="Capability to disable"
    )
    sub_deny.add_argument("project", help="Project name")

    # allowed: list projects with active capabilities
    subparsers.add_parser(
        "allowed",
        parents=[p_verbose],
        help="List projects with cross-container podman access enabled",
    )

    if constants.HAVE_ARGCOMPLETE:
        argcomplete.autocomplete(parser)

    args = parser.parse_args(argv)
    args._parser = parser
    return args


def check_tmux_guard() -> None:
    """Check if already inside tmux session."""
    if os.environ.get("TMUX"):
        sys.exit("Error: Already in tmux session. Nested tmux not supported.")


def find_git_root(start_path: Path | None = None) -> Path | None:
    """Find git repository root by traversing up from start_path.

    Returns None if not in a git repository.
    """
    if start_path is None:
        start_path = Path.cwd()

    current = Path(start_path).resolve()

    while current != current.parent:
        if (current / ".git").exists():
            return current
        current = current.parent

    # Check root directory too
    if (current / ".git").exists():
        return current

    return None


def generate_random_name() -> str:
    """Generate random adjective-noun name for worktree."""
    adj = random.choice(constants.ADJECTIVES)
    noun = random.choice(constants.NOUNS)
    return f"{adj}-{noun}"


def slugify_prompt(prompt: str, max_len: int = 50) -> str:
    """Convert a research prompt to a filename slug."""
    slug = re.sub(r"[^a-z0-9]+", "-", prompt.lower()).strip("-")
    if len(slug) > max_len:
        slug = slug[:max_len].rsplit("-", 1)[0]
    return slug or "research"


def get_container_name(project_path: str, worktree_name: str | None) -> str:
    """Generate container name from project path and optional worktree name."""
    project_name = Path(project_path.rstrip("/")).name.lower()

    if worktree_name:
        return f"{project_name}-{worktree_name}"
    return project_name


def _format_container_display(workspace_folder: str) -> str:
    """Derive a human-friendly label from a workspace path.

    /home/tsb/dev/myapp           -> myapp
    /home/tsb/dev/myapp-worktrees/bold-bear -> myapp / bold-bear
    """
    p = Path(workspace_folder)
    if p.parent.name.endswith("-worktrees"):
        project = p.parent.name.removesuffix("-worktrees")
        return f"{project} / {p.name}"
    return p.name


# Cross-container podman access gate. `jolo allow podman <project>`
# creates a per-project gate directory at
# ~/.config/jolo/podman-runtime/<project>/ AND starts a socat proxy
# listening at <gate>/podman.sock that forwards to the host's
# $XDG_RUNTIME_DIR/podman/podman.sock. The devcontainer bind-mounts
# the gate directory at /run/podman, so toggling socat (allow/deny)
# flips the capability instantly without container recreation. The
# gate dir itself is host-only — not bind-mounted into any container
# under a writable host path — so an agent inside cannot reach this
# CLI or its state to flip the gate for itself.

_PODMAN_RUNTIME_DIRNAME = "podman-runtime"


def _podman_runtime_dir(project: str, config_dir: Path | None = None) -> Path:
    base = (
        config_dir
        if config_dir is not None
        else Path.home() / ".config" / "jolo"
    )
    return base / _PODMAN_RUNTIME_DIRNAME / project


def _podman_proxy_socket(project: str, config_dir: Path | None = None) -> Path:
    return _podman_runtime_dir(project, config_dir) / "podman.sock"


def _podman_proxy_pidfile(
    project: str, config_dir: Path | None = None
) -> Path:
    return _podman_runtime_dir(project, config_dir) / "socat.pid"


def _process_is_socat(pid: int, listen_path: Path | None = None) -> bool:
    """True iff PID exists, is socat, and (when listen_path is given)
    has UNIX-LISTEN:<listen_path> on its argv. Without listen_path,
    a bare socat anywhere in cmdline is a false positive against PID
    reuse — callers should pass listen_path whenever they have one."""
    try:
        cmdline = Path(f"/proc/{pid}/cmdline").read_bytes()
    except (FileNotFoundError, ProcessLookupError, PermissionError):
        return False
    if b"socat" not in cmdline:
        return False
    if listen_path is not None:
        return f"UNIX-LISTEN:{listen_path}".encode() in cmdline
    return True


def _spawn_socat(listen_path: Path, target_path: Path) -> subprocess.Popen:
    """Spawn a detached socat that forwards listen_path → target_path.
    Detached so it survives the parent jolo invocation."""
    listen_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        return subprocess.Popen(
            [
                "socat",
                f"UNIX-LISTEN:{listen_path},fork,reuseaddr,unlink-early",
                f"UNIX-CONNECT:{target_path}",
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(
            "socat is required for cross-container podman access "
            "(install with `apk add socat` / `pacman -S socat` / etc.)"
        ) from exc


@contextlib.contextmanager
def _podman_proxy_lock(project: str, config_dir: Path | None = None):
    """Serialize concurrent jolo allow/deny on the same project so two
    callers can't double-spawn or race-cleanup. Lockfile lives next to
    the pidfile; flock is released when the context exits."""
    gate_dir = _podman_runtime_dir(project, config_dir)
    gate_dir.mkdir(parents=True, exist_ok=True)
    lockfile = gate_dir / ".lock"
    with open(lockfile, "w") as f:
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)


def is_podman_proxy_running(
    project: str, config_dir: Path | None = None
) -> bool:
    pidfile = _podman_proxy_pidfile(project, config_dir)
    if not pidfile.is_file():
        return False
    try:
        pid = int(pidfile.read_text().strip())
    except (OSError, ValueError):
        return False
    return _process_is_socat(pid, _podman_proxy_socket(project, config_dir))


def start_podman_proxy(project: str, config_dir: Path | None = None) -> int:
    """Start (or attach to) the socat proxy for PROJECT. Returns its PID.
    Idempotent: a live socat for the same listen path is reused; stale
    pidfiles (dead PID, recycled PID running unrelated process, recycled
    PID running a *different* socat) are replaced. Concurrent callers
    are serialized via a per-project flock."""
    socket_path = _podman_proxy_socket(project, config_dir)
    pidfile = _podman_proxy_pidfile(project, config_dir)
    with _podman_proxy_lock(project, config_dir):
        if pidfile.is_file():
            try:
                existing = int(pidfile.read_text().strip())
                if _process_is_socat(existing, socket_path):
                    return existing
            except (OSError, ValueError):
                pass

        target = (
            Path(os.environ.get("XDG_RUNTIME_DIR", "/run/user/1000"))
            / "podman"
            / "podman.sock"
        )
        proc = _spawn_socat(socket_path, target)
        pidfile.write_text(f"{proc.pid}\n")
        return proc.pid


def stop_podman_proxy(project: str, config_dir: Path | None = None) -> bool:
    """Stop the socat proxy for PROJECT. Returns True if it was running.
    Concurrent callers are serialized via the per-project flock; only
    the process matching this project's listen path is killed (defends
    against PID reuse)."""
    pidfile = _podman_proxy_pidfile(project, config_dir)
    socket_path = _podman_proxy_socket(project, config_dir)
    with _podman_proxy_lock(project, config_dir):
        if not pidfile.is_file():
            return False
        try:
            pid = int(pidfile.read_text().strip())
        except (OSError, ValueError):
            pidfile.unlink(missing_ok=True)
            return False
        was_running = _process_is_socat(pid, socket_path)
        if was_running:
            try:
                os.kill(pid, 15)  # SIGTERM
            except ProcessLookupError:
                was_running = False
        pidfile.unlink(missing_ok=True)
        socket_path.unlink(missing_ok=True)
        return was_running


def is_podman_allowed(project: str, config_dir: Path | None = None) -> bool:
    """True if PROJECT has been retrofitted (gate dir exists). Whether
    the proxy is currently running is a separate question — see
    `is_podman_proxy_running`."""
    return _podman_runtime_dir(project, config_dir).is_dir()


def allow_podman(project: str, config_dir: Path | None = None) -> Path:
    """Opt PROJECT in: ensure gate dir exists and start the socat proxy.
    Idempotent. If start fails on the *first* allow (e.g. socat missing)
    the just-created gate dir is rolled back, so the next attempt sees
    a clean first-time state and the user gets the `jolo up --recreate`
    hint they need."""
    gate_dir = _podman_runtime_dir(project, config_dir)
    new = not gate_dir.is_dir()
    gate_dir.mkdir(parents=True, exist_ok=True)
    try:
        start_podman_proxy(project, config_dir)
    except Exception:
        if new:
            # Best-effort cleanup; ignore if it's already populated.
            for child in gate_dir.iterdir():
                child.unlink(missing_ok=True)
            gate_dir.rmdir()
        raise
    return gate_dir


def deny_podman(project: str, config_dir: Path | None = None) -> bool:
    """Stop the socat proxy. Keeps the gate dir so the bind mount stays
    in devcontainer.json across recreates (re-allowing later doesn't
    require another --recreate). Returns True if proxy was running."""
    return stop_podman_proxy(project, config_dir)
