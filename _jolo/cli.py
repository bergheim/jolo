"""Utility functions and CLI argument parsing for jolo."""

import argparse
import json
import os
import random
import re
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


def _select_languages_gum() -> list[str]:
    """Use gum for interactive selection (if available)."""
    result = subprocess.run(
        [
            "gum",
            "choose",
            "--no-limit",
            "--header",
            "Select project languages:",
        ]
        + constants.LANGUAGE_OPTIONS,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []
    selected = result.stdout.strip().splitlines()
    return [
        constants.LANGUAGE_CODE_MAP[opt]
        for opt in selected
        if opt in constants.LANGUAGE_CODE_MAP
    ]


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
                selected.append(
                    constants.LANGUAGE_CODE_MAP[
                        constants.LANGUAGE_OPTIONS[idx]
                    ]
                )
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
    invalid = [
        lang for lang in languages if lang not in constants.VALID_LANGUAGES
    ]
    if invalid:
        valid_list = ", ".join(sorted(constants.VALID_LANGUAGES))
        raise argparse.ArgumentTypeError(
            f"Invalid language(s): {', '.join(invalid)}. Valid options: {valid_list}"
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

    p_new = argparse.ArgumentParser(add_help=False)
    p_new.add_argument(
        "--new",
        action="store_true",
        help="Remove existing container before starting",
    )

    p_sync = argparse.ArgumentParser(add_help=False)
    p_sync.add_argument(
        "--sync",
        action="store_true",
        help="Regenerate .devcontainer from template",
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
        new=False,
        sync=False,
        detach=False,
        shell=False,
        run=None,
        mount=[],
        copy=[],
        lang=None,
        yes=False,
        verbose=False,
        purge=False,
        target=None,
    )

    subparsers = parser.add_subparsers(dest="command", prog="jolo")

    # up: prompt, agent, detach, exec, mounts, new, sync, verbose
    subparsers.add_parser(
        "up",
        parents=[
            p_verbose,
            p_prompt,
            p_detach,
            p_exec,
            p_mounts,
            p_new,
            p_sync,
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
        "--lang",
        type=parse_lang_arg,
        default=None,
        metavar="LANG[,...]",
        help="Project language(s): python, go, typescript, rust, shell, prose, other",
    )

    # clone: prompt, agent, detach, exec, mounts, new, sync, verbose
    sub_clone = subparsers.add_parser(
        "clone",
        parents=[
            p_verbose,
            p_prompt,
            p_detach,
            p_exec,
            p_mounts,
            p_new,
            p_sync,
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

    # tree: prompt, agent, detach, exec, mounts, new, sync, from, verbose
    sub_tree = subparsers.add_parser(
        "tree",
        parents=[
            p_verbose,
            p_prompt,
            p_detach,
            p_exec,
            p_mounts,
            p_new,
            p_sync,
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

    # spawn: prompt, agent, from, prefix, mounts, new, sync, verbose
    sub_spawn = subparsers.add_parser(
        "spawn",
        parents=[p_verbose, p_prompt, p_mounts, p_new, p_sync],
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

    # open: verbose
    subparsers.add_parser(
        "open",
        parents=[p_verbose],
        help="Pick a running container and attach to it",
    )

    # down: all, verbose
    subparsers.add_parser(
        "down", parents=[p_verbose, p_all], help="Stop the devcontainer"
    )

    # init: prompt, agent, detach, exec, mounts, sync, verbose
    subparsers.add_parser(
        "init",
        parents=[p_verbose, p_prompt, p_detach, p_exec, p_mounts, p_sync],
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
    sub_research.add_argument("prompt", help="Research topic or question")
    sub_research.add_argument(
        "--agent",
        default=None,
        metavar="CMD",
        help="AI agent to use (default: random)",
    )
    sub_research.add_argument(
        "--topic",
        default=None,
        metavar="TOPIC",
        help="ntfy.sh topic for notification (default: from config)",
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
