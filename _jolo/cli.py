"""Utility functions and CLI argument parsing for jolo."""

import argparse
import json
import os
import random
import shutil
import socket
import subprocess
import sys
from pathlib import Path

try:
    import argcomplete
except ImportError:
    pass

from _jolo import constants


def random_port() -> int:
    """Pick a random port in the PORT_MIN-PORT_MAX range."""
    return random.randint(constants.PORT_MIN, constants.PORT_MAX)


def is_port_available(port: int) -> bool:
    """Check if a TCP port is available on the host."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("", port))
            return True
        except OSError:
            return False


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
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            dns_name = data.get("Self", {}).get("DNSName", "")
            if dns_name:
                return dns_name.rstrip(".")
    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
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


def _select_languages_gum() -> list[str]:
    """Use gum for interactive selection (if available)."""
    result = subprocess.run(
        ["gum", "choose", "--no-limit", "--header", "Select project languages:"]
        + constants.LANGUAGE_OPTIONS,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []
    selected = result.stdout.strip().splitlines()
    return [constants.LANGUAGE_CODE_MAP[opt] for opt in selected if opt in constants.LANGUAGE_CODE_MAP]


def _select_languages_fallback() -> list[str]:
    """Fallback numbered input when gum isn't available."""
    print("Select project languages (comma-separated numbers, e.g. 1,3):")
    for i, opt in enumerate(constants.LANGUAGE_OPTIONS, 1):
        print(f"  {i}. {opt}")
    print()
    try:
        response = input("> ").strip()
    except (KeyboardInterrupt, EOFError):
        return []
    if not response:
        return []
    selected = []
    for part in response.split(","):
        part = part.strip()
        if part.isdigit():
            idx = int(part) - 1
            if 0 <= idx < len(constants.LANGUAGE_OPTIONS):
                selected.append(constants.LANGUAGE_CODE_MAP[constants.LANGUAGE_OPTIONS[idx]])
    return selected


def select_languages_interactive() -> list[str]:
    """Show interactive multi-select picker for project languages.

    Uses gum choose if available, falls back to numbered input.

    Returns:
        List of selected language codes (lowercase), e.g. ['python', 'typescript'].
        First selected = primary language. Returns empty list if user cancels.
    """
    if shutil.which("gum"):
        try:
            return _select_languages_gum()
        except KeyboardInterrupt:
            return []
    else:
        return _select_languages_fallback()


def parse_lang_arg(value: str) -> list[str]:
    """Parse and validate --lang argument.

    Accepts comma-separated language names, strips whitespace, validates
    each language against VALID_LANGUAGES.

    Args:
        value: Comma-separated string of language names

    Returns:
        List of validated language names

    Raises:
        argparse.ArgumentTypeError: If any language is invalid
    """
    languages = [lang.strip() for lang in value.split(",")]
    invalid = [lang for lang in languages if lang not in constants.VALID_LANGUAGES]
    if invalid:
        valid_list = ", ".join(sorted(constants.VALID_LANGUAGES))
        raise argparse.ArgumentTypeError(
            f"Invalid language(s): {', '.join(invalid)}. "
            f"Valid options: {valid_list}"
        )
    return languages


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
        sys.exit(f"Error: Invalid mount syntax: {arg} (expected source:target)")

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
        print(f'[verbose] $ {" ".join(cmd)}', file=sys.stderr)


def preprocess_argv(argv: list[str]) -> list[str]:
    """Convert subcommand form to flag form: 'create foo' -> '--create foo'."""
    if argv and argv[0] in constants.SUBCOMMANDS:
        return [f"--{argv[0]}"] + argv[1:]
    return argv


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse command-line arguments."""
    argv = preprocess_argv(argv)
    parser = argparse.ArgumentParser(
        prog="jolo",
        usage="jolo [command] [options] [path]",
        description="Devcontainer + Git Worktree Launcher",
        epilog="Examples: jolo start | jolo create foo | jolo list | jolo tree feat-x | "
        "jolo stop --all | jolo spawn 3 -p 'do thing'",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=False,
    )

    cmds = parser.add_argument_group(
        "commands",
        "  start               Start devcontainer in current project\n"
        "  create NAME         Create new project with git + devcontainer\n"
        "  tree [NAME]         Create worktree + devcontainer (random name if omitted)\n"
        "  spawn N             Create N worktrees in parallel, each with its own agent\n"
        "  list                List running containers and worktrees\n"
        "  open                Pick a running container and attach to it\n"
        "  stop                Stop the devcontainer\n"
        "  attach              Attach to running container\n"
        "  init                Initialize git + devcontainer in current directory\n"
        "  sync                Regenerate .devcontainer from template\n"
        "  prune               Clean up stopped/orphan containers and stale worktrees\n"
        "  destroy             Stop and remove all containers for project",
    )

    # Commands use SUPPRESS for internal argparse flags, shown manually via description
    cmds.add_argument("--create", metavar="NAME", help=argparse.SUPPRESS)
    cmds.add_argument(
        "--tree", nargs="?", const="", default=None, metavar="NAME",
        help=argparse.SUPPRESS,
    )
    cmds.add_argument("--spawn", type=int, metavar="N", help=argparse.SUPPRESS)
    cmds.add_argument("--list", action="store_true", help=argparse.SUPPRESS)
    cmds.add_argument("--stop", action="store_true", help=argparse.SUPPRESS)
    cmds.add_argument("--attach", action="store_true", help=argparse.SUPPRESS)
    cmds.add_argument("--init", action="store_true", help=argparse.SUPPRESS)
    cmds.add_argument("--sync", action="store_true", help=argparse.SUPPRESS)
    cmds.add_argument("--prune", action="store_true", help=argparse.SUPPRESS)
    cmds.add_argument("--destroy", action="store_true", help=argparse.SUPPRESS)
    cmds.add_argument("--open", action="store_true", help=argparse.SUPPRESS)
    cmds.add_argument("--start", action="store_true", help=argparse.SUPPRESS)

    opts = parser.add_argument_group("options")

    opts.add_argument(
        "--prompt",
        "-p",
        metavar="PROMPT",
        help="Start AI agent with this prompt (implies --detach)",
    )

    opts.add_argument(
        "--agent",
        default="claude",
        metavar="CMD",
        help="AI agent command (default: claude)",
    )

    opts.add_argument(
        "--from",
        dest="from_branch",
        metavar="BRANCH",
        help="Create worktree from specified branch",
    )

    opts.add_argument(
        "--prefix",
        metavar="NAME",
        help="Prefix for spawn worktree names (feat -> feat-1, feat-2, ...)",
    )

    opts.add_argument(
        "--all",
        "-a",
        action="store_true",
        help="With list: all globally. With stop: all for project",
    )

    opts.add_argument(
        "--new", action="store_true", help="Remove existing container before starting"
    )

    opts.add_argument(
        "--detach", "-d", action="store_true", help="Start container without attaching"
    )

    opts.add_argument(
        "--shell",
        action="store_true",
        help="Exec into container with zsh (no tmux)",
    )

    opts.add_argument(
        "--run",
        metavar="CMD",
        help="Exec command directly in container (no tmux)",
    )

    opts.add_argument(
        "--mount",
        action="append",
        default=[],
        metavar="SRC:DST[:ro]",
        help="Mount host path into container (repeatable)",
    )

    opts.add_argument(
        "--copy",
        action="append",
        default=[],
        metavar="SRC[:DST]",
        help="Copy file to workspace before start (repeatable)",
    )

    opts.add_argument(
        "--lang",
        type=parse_lang_arg,
        default=None,
        metavar="LANG[,...]",
        help="Project language(s): python, go, typescript, rust, shell, prose, other",
    )

    opts.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Skip confirmation prompts",
    )

    opts.add_argument(
        "--verbose", "-v", action="store_true", help="Print commands being executed"
    )

    opts.add_argument(
        "-h", "--help", action="help", help="Show this help message and exit"
    )

    parser.add_argument(
        "path",
        nargs="?",
        default=None,
        help=argparse.SUPPRESS,
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
