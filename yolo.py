#!/usr/bin/env python3
"""yolo - Devcontainer + Git Worktree Launcher.

A CLI tool that bootstraps devcontainer environments with git worktree support.
Target location: ~/.local/bin/yolo
"""

import argparse
import json
import os
import random
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

# Word lists for random name generation
ADJECTIVES = [
    "brave",
    "swift",
    "calm",
    "bold",
    "keen",
    "wild",
    "warm",
    "cool",
    "fair",
    "wise",
]
NOUNS = [
    "panda",
    "falcon",
    "river",
    "mountain",
    "oak",
    "wolf",
    "hawk",
    "cedar",
    "fox",
    "bear",
]

# Default configuration
DEFAULT_CONFIG = {
    "base_image": "localhost/emacs-gui:latest",
    "pass_path_anthropic": "api/llm/anthropic",
    "pass_path_openai": "api/llm/openai",
}

# Global verbose flag
VERBOSE = False


def verbose_print(msg: str) -> None:
    """Print message if verbose mode is enabled."""
    if VERBOSE:
        print(f"[verbose] {msg}", file=sys.stderr)


def verbose_cmd(cmd: list[str]) -> None:
    """Print command if verbose mode is enabled."""
    if VERBOSE:
        print(f'[verbose] $ {" ".join(cmd)}', file=sys.stderr)


def load_config(global_config_dir: Path | None = None) -> dict:
    """Load configuration from TOML files.

    Config is loaded in order (later overrides earlier):
    1. Default config
    2. Global config: ~/.config/yolo/config.toml
    3. Project config: .yolo.toml in current directory
    """
    config = DEFAULT_CONFIG.copy()

    if global_config_dir is None:
        global_config_dir = Path.home() / ".config" / "yolo"

    # Load global config
    global_config_file = global_config_dir / "config.toml"
    if global_config_file.exists():
        with open(global_config_file, "rb") as f:
            global_cfg = tomllib.load(f)
            config.update(global_cfg)

    # Load project config
    project_config_file = Path.cwd() / ".yolo.toml"
    if project_config_file.exists():
        with open(project_config_file, "rb") as f:
            project_cfg = tomllib.load(f)
            config.update(project_cfg)

    return config


# Base mounts that are always included
BASE_MOUNTS = [
    "source=/tmp/.X11-unix,target=/tmp/.X11-unix,type=bind",
    "source=${localEnv:HOME}/.claude,target=/home/${localEnv:USER}/.claude,type=bind",
    "source=${localEnv:HOME}/.claude.json,target=/home/${localEnv:USER}/.claude.json,type=bind",
    "source=${localEnv:HOME}/.zshrc,target=/home/${localEnv:USER}/.zshrc,type=bind,readonly",
    "source=${localEnv:HOME}/.tmux.conf,target=/home/${localEnv:USER}/.tmux.conf,type=bind,readonly",
    "source=${localEnv:HOME}/.gitconfig,target=/home/${localEnv:USER}/.gitconfig,type=bind,readonly",
    "source=${localEnv:HOME}/.config/tmux,target=/home/${localEnv:USER}/.config/tmux,type=bind,readonly",
    "source=${localEnv:HOME}/.config/emacs,target=/home/${localEnv:USER}/.config/emacs,type=bind",
    "source=${localEnv:HOME}/.cache/emacs,target=/home/${localEnv:USER}/.cache/emacs,type=bind",
    "source=${localEnv:HOME}/.gnupg/pubring.kbx,target=/home/${localEnv:USER}/.gnupg/pubring.kbx,type=bind,readonly",
    "source=${localEnv:HOME}/.gnupg/trustdb.gpg,target=/home/${localEnv:USER}/.gnupg/trustdb.gpg,type=bind,readonly",
    "source=${localEnv:XDG_RUNTIME_DIR}/gnupg/S.gpg-agent,target=/home/${localEnv:USER}/.gnupg/S.gpg-agent,type=bind",
    "source=${localEnv:HOME}/.config/gh,target=/home/${localEnv:USER}/.config/gh,type=bind,readonly",
]

# Wayland mount - only included when WAYLAND_DISPLAY is set
WAYLAND_MOUNT = "source=${localEnv:XDG_RUNTIME_DIR}/${localEnv:WAYLAND_DISPLAY},target=/tmp/container-runtime/${localEnv:WAYLAND_DISPLAY},type=bind"


def build_devcontainer_json(project_name: str) -> str:
    """Build devcontainer.json content dynamically.

    Conditionally includes Wayland mount only if WAYLAND_DISPLAY is set.
    """
    mounts = BASE_MOUNTS.copy()

    # Only add Wayland mount if WAYLAND_DISPLAY is set
    if os.environ.get("WAYLAND_DISPLAY"):
        mounts.append(WAYLAND_MOUNT)

    config = {
        "name": project_name,
        "build": {"dockerfile": "Dockerfile"},
        "mounts": mounts,
        "containerEnv": {
            "TERM": "xterm-256color",
            "DISPLAY": "${localEnv:DISPLAY}",
            "WAYLAND_DISPLAY": "${localEnv:WAYLAND_DISPLAY}",
            "XDG_RUNTIME_DIR": "/tmp/container-runtime",
            "ANTHROPIC_API_KEY": "${localEnv:ANTHROPIC_API_KEY}",
            "OPENAI_API_KEY": "${localEnv:OPENAI_API_KEY}",
        },
    }

    return json.dumps(config, indent=4)

DOCKERFILE_TEMPLATE = """FROM BASE_IMAGE

USER root
RUN apk add --no-cache nodejs npm
LABEL devcontainer.metadata='[{"remoteUser":"CONTAINER_USER","workspaceFolder":"/workspace"}]'

WORKDIR /workspace

USER CONTAINER_USER
"""


def parse_args(argv: list[str]) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        prog="yolo",
        description="Devcontainer + Git Worktree Launcher",
        epilog="Run with no arguments to start devcontainer in current git project.",
    )

    parser.add_argument(
        "--tree",
        nargs="?",
        const="",
        default=None,
        metavar="NAME",
        help="Create git worktree and start devcontainer there. "
        "If NAME not provided, generates random name.",
    )

    parser.add_argument(
        "--create", metavar="NAME", help="Create new project with git + devcontainer"
    )

    parser.add_argument(
        "--init",
        action="store_true",
        help="Initialize git + devcontainer in current directory",
    )

    parser.add_argument(
        "--new", action="store_true", help="Remove existing container before starting"
    )

    parser.add_argument(
        "--sync",
        action="store_true",
        help="Regenerate .devcontainer from template using current config",
    )

    parser.add_argument(
        "--list",
        action="store_true",
        help="List running containers and worktrees for current project",
    )

    parser.add_argument(
        "--all",
        "-a",
        action="store_true",
        help="With --list: show all devcontainers globally. "
        "With --stop: stop all containers for project (worktrees + main)",
    )

    parser.add_argument(
        "--stop", action="store_true", help="Stop the devcontainer for current project"
    )

    parser.add_argument(
        "--prune",
        action="store_true",
        help="Clean up stopped containers and stale worktrees for project",
    )

    parser.add_argument(
        "--destroy",
        nargs="?",
        const="",
        default=None,
        metavar="PATH",
        help="Stop and remove all containers for project (before rm -rf)",
    )

    parser.add_argument(
        "--attach",
        action="store_true",
        help="Attach to running container (error if not running)",
    )

    parser.add_argument(
        "--detach", "-d", action="store_true", help="Start container without attaching"
    )

    parser.add_argument(
        "--from",
        dest="from_branch",
        metavar="BRANCH",
        help="With --tree: create worktree from specified branch",
    )

    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Print commands being executed"
    )

    return parser.parse_args(argv)


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
    adj = random.choice(ADJECTIVES)
    noun = random.choice(NOUNS)
    return f"{adj}-{noun}"


def scaffold_devcontainer(
    project_name: str, target_dir: Path | None = None, config: dict | None = None
) -> bool:
    """Create .devcontainer directory with templates.

    Returns True if created, False if already exists.
    """
    if target_dir is None:
        target_dir = Path.cwd()
    if config is None:
        config = DEFAULT_CONFIG

    devcontainer_dir = target_dir / ".devcontainer"

    if devcontainer_dir.exists():
        print(f"Warning: Using existing .devcontainer/", file=sys.stderr)
        return False

    devcontainer_dir.mkdir(parents=True)

    # Get current username for Dockerfile
    username = os.environ.get("USER", "dev")

    # Write devcontainer.json (dynamically built based on environment)
    json_content = build_devcontainer_json(project_name)
    (devcontainer_dir / "devcontainer.json").write_text(json_content)

    # Write Dockerfile with substituted base image and username
    dockerfile_content = DOCKERFILE_TEMPLATE.replace("BASE_IMAGE", config["base_image"])
    dockerfile_content = dockerfile_content.replace("CONTAINER_USER", username)
    (devcontainer_dir / "Dockerfile").write_text(dockerfile_content)

    return True


def sync_devcontainer(
    project_name: str, target_dir: Path | None = None, config: dict | None = None
) -> None:
    """Regenerate .devcontainer from template, overwriting existing files.

    Unlike scaffold_devcontainer, this always writes the files even if
    .devcontainer already exists.
    """
    if target_dir is None:
        target_dir = Path.cwd()
    if config is None:
        config = DEFAULT_CONFIG

    devcontainer_dir = target_dir / ".devcontainer"
    devcontainer_dir.mkdir(parents=True, exist_ok=True)

    # Get current username for Dockerfile
    username = os.environ.get("USER", "dev")

    # Write devcontainer.json (dynamically built based on environment)
    json_content = build_devcontainer_json(project_name)
    (devcontainer_dir / "devcontainer.json").write_text(json_content)

    # Write Dockerfile with substituted base image and username
    dockerfile_content = DOCKERFILE_TEMPLATE.replace("BASE_IMAGE", config["base_image"])
    dockerfile_content = dockerfile_content.replace("CONTAINER_USER", username)
    (devcontainer_dir / "Dockerfile").write_text(dockerfile_content)

    print(f"Synced .devcontainer/ with current config")


def get_secrets(config: dict | None = None) -> dict[str, str]:
    """Get API secrets from pass or environment variables."""
    if config is None:
        config = DEFAULT_CONFIG

    secrets = {}

    # Check if pass is available
    pass_available = shutil.which("pass") is not None

    if pass_available:
        # Try to get secrets from pass using configured paths
        for key, pass_path in [
            ("ANTHROPIC_API_KEY", config["pass_path_anthropic"]),
            ("OPENAI_API_KEY", config["pass_path_openai"]),
        ]:
            try:
                result = subprocess.run(
                    ["pass", "show", pass_path],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    secrets[key] = result.stdout.strip()
            except (subprocess.TimeoutExpired, subprocess.SubprocessError):
                pass

    # Fallback to environment variables for any missing secrets
    for key in ["ANTHROPIC_API_KEY", "OPENAI_API_KEY"]:
        if key not in secrets:
            secrets[key] = os.environ.get(key, "")

    return secrets


def get_container_name(project_path: str, worktree_name: str | None) -> str:
    """Generate container name from project path and optional worktree name."""
    project_name = Path(project_path.rstrip("/")).name.lower()

    if worktree_name:
        return f"{project_name}-{worktree_name}"
    return project_name


def get_worktree_path(project_path: str, worktree_name: str) -> Path:
    """Compute worktree path: ../PROJECT-worktrees/NAME."""
    project_path = Path(project_path.rstrip("/"))
    project_name = project_path.name
    worktrees_dir = project_path.parent / f"{project_name}-worktrees"
    return worktrees_dir / worktree_name


def validate_tree_mode() -> Path:
    """Validate that --tree mode is being run inside a git repo.

    Returns the git root path.
    """
    git_root = find_git_root()
    if git_root is None:
        sys.exit("Error: Not in a git repository. --tree requires an existing repo.")
    return git_root


def validate_create_mode(name: str) -> None:
    """Validate that --create mode is NOT being run inside a git repo."""
    git_root = find_git_root()
    if git_root is not None:
        sys.exit("Error: Already in a git repository. Use --tree for worktrees.")

    target_dir = Path.cwd() / name
    if target_dir.exists():
        sys.exit(f"Error: Directory already exists: {target_dir}")


def validate_init_mode() -> None:
    """Validate that --init mode is NOT being run inside a git repo."""
    git_root = find_git_root()
    if git_root is not None:
        sys.exit("Error: Already in a git repository. Use yolo without --init.")


def add_worktree_git_mount(devcontainer_json_path: Path, main_git_dir: Path) -> None:
    """Add a mount for the main repo's .git directory to devcontainer.json.

    This is needed for worktrees because git worktrees use a .git file that
    points to the main repo's .git/worktrees/NAME directory with an absolute
    path. We need to mount that path into the container.
    """
    content = json.loads(devcontainer_json_path.read_text())

    if "mounts" not in content:
        content["mounts"] = []

    # Mount the main .git directory at the same absolute path in the container
    git_mount = f"source={main_git_dir},target={main_git_dir},type=bind"
    content["mounts"].append(git_mount)

    devcontainer_json_path.write_text(json.dumps(content, indent=4))


def is_container_running(workspace_dir: Path) -> bool:
    """Check if devcontainer for workspace is already running."""
    cmd = ["devcontainer", "exec", "--workspace-folder", str(workspace_dir), "true"]
    verbose_cmd(cmd)
    result = subprocess.run(cmd, capture_output=True, cwd=workspace_dir)
    return result.returncode == 0


def devcontainer_up(workspace_dir: Path, remove_existing: bool = False) -> bool:
    """Start devcontainer with devcontainer up.

    Returns True if successful.
    """
    cmd = ["devcontainer", "up", "--workspace-folder", str(workspace_dir)]

    if remove_existing:
        cmd.append("--remove-existing-container")

    verbose_cmd(cmd)
    result = subprocess.run(cmd, cwd=workspace_dir)
    return result.returncode == 0


def devcontainer_exec_tmux(workspace_dir: Path) -> None:
    """Execute into container and attach/create tmux session."""
    cmd = [
        "devcontainer",
        "exec",
        "--workspace-folder",
        str(workspace_dir),
        "sh",
        "-c",
        "tmux attach-session -t dev || tmux new-session -s dev",
    ]

    verbose_cmd(cmd)
    subprocess.run(cmd, cwd=workspace_dir)


def list_worktrees(git_root: Path) -> list[tuple[Path, str, str]]:
    """List git worktrees for a repository.

    Returns list of tuples: (path, commit, branch)
    """
    result = subprocess.run(
        ["git", "worktree", "list", "--porcelain"],
        cwd=git_root,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        return []

    worktrees = []
    current_worktree = {}

    for line in result.stdout.strip().split("\n"):
        if not line:
            if current_worktree:
                worktrees.append(
                    (
                        Path(current_worktree.get("worktree", "")),
                        current_worktree.get("HEAD", "")[:7],
                        current_worktree.get("branch", "").replace("refs/heads/", ""),
                    )
                )
                current_worktree = {}
            continue

        if line.startswith("worktree "):
            current_worktree["worktree"] = line[9:]
        elif line.startswith("HEAD "):
            current_worktree["HEAD"] = line[5:]
        elif line.startswith("branch "):
            current_worktree["branch"] = line[7:]

    # Don't forget last worktree
    if current_worktree:
        worktrees.append(
            (
                Path(current_worktree.get("worktree", "")),
                current_worktree.get("HEAD", "")[:7],
                current_worktree.get("branch", "").replace("refs/heads/", ""),
            )
        )

    return worktrees


def find_project_workspaces(git_root: Path) -> list[tuple[Path, str]]:
    """Find all workspace directories for a project.

    Returns list of tuples: (path, type) where type is 'main' or worktree name.
    """
    project_name = git_root.name
    workspaces = [(git_root, "main")]

    # Check for worktrees directory
    worktrees_dir = git_root.parent / f"{project_name}-worktrees"
    if worktrees_dir.exists():
        worktrees = list_worktrees(git_root)
        for wt_path, _, branch in worktrees:
            if wt_path != git_root:
                workspaces.append((wt_path, branch or wt_path.name))

    return workspaces


def get_container_runtime() -> str | None:
    """Detect available container runtime (docker or podman)."""
    if shutil.which("docker"):
        return "docker"
    if shutil.which("podman"):
        return "podman"
    return None


def list_all_devcontainers() -> list[tuple[str, str, str]]:
    """List all running devcontainers globally.

    Returns list of tuples: (container_name, workspace_folder, status)
    """
    runtime = get_container_runtime()
    if runtime is None:
        return []

    # Query containers with devcontainer label
    result = subprocess.run(
        [
            runtime,
            "ps",
            "-a",
            "--filter",
            "label=devcontainer.local_folder",
            "--format",
            '{{.Names}}\t{{.Label "devcontainer.local_folder"}}\t{{.State}}',
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        return []

    containers = []
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) >= 3:
            name, folder, state = parts[0], parts[1], parts[2]
            containers.append((name, folder, state))

    return containers


def run_list_global_mode() -> None:
    """Run --list --all mode: show all running devcontainers globally."""
    runtime = get_container_runtime()
    if runtime is None:
        sys.exit("Error: No container runtime found (docker or podman required)")

    containers = list_all_devcontainers()

    print("Running devcontainers:")
    print()

    running_containers = [(n, f, s) for n, f, s in containers if s == "running"]

    if not running_containers:
        print("  (none)")
    else:
        for name, folder, _ in running_containers:
            print(f"  {name:<24} {folder}")

    # Also show stopped containers
    stopped_containers = [(n, f, s) for n, f, s in containers if s != "running"]
    if stopped_containers:
        print()
        print("Stopped devcontainers:")
        print()
        for name, folder, state in stopped_containers:
            print(f"  {name:<24} {folder}  ({state})")


def get_container_for_workspace(workspace_dir: Path) -> str | None:
    """Get container name for a workspace directory.

    Returns container name if found, None otherwise.
    """
    runtime = get_container_runtime()
    if runtime is None:
        return None

    # Query containers with matching workspace folder
    result = subprocess.run(
        [
            runtime,
            "ps",
            "-a",
            "--filter",
            f"label=devcontainer.local_folder={workspace_dir}",
            "--format",
            "{{.Names}}",
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0 or not result.stdout.strip():
        return None

    return result.stdout.strip().split("\n")[0]


def stop_container(workspace_dir: Path) -> bool:
    """Stop the devcontainer for a workspace.

    Returns True if stopped successfully, False otherwise.
    """
    runtime = get_container_runtime()
    if runtime is None:
        print(
            "Error: No container runtime found (docker or podman required)",
            file=sys.stderr,
        )
        return False

    container_name = get_container_for_workspace(workspace_dir)
    if container_name is None:
        print(f"No container found for {workspace_dir}", file=sys.stderr)
        return False

    cmd = [runtime, "stop", container_name]
    verbose_cmd(cmd)
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode == 0:
        print(f"Stopped: {container_name}")
        return True
    else:
        print(f"Failed to stop {container_name}: {result.stderr}", file=sys.stderr)
        return False


def run_stop_mode(args: argparse.Namespace) -> None:
    """Run --stop mode: stop the devcontainer for current project."""
    git_root = find_git_root()

    if git_root is None:
        sys.exit("Error: Not in a git repository.")

    if args.all:
        # Stop all containers for this project (worktrees first, then main)
        workspaces = find_project_workspaces(git_root)
        # Reverse so worktrees come before main
        worktrees = [(p, t) for p, t in workspaces if t != "main"]
        main = [(p, t) for p, t in workspaces if t == "main"]

        any_stopped = False
        for ws_path, ws_type in worktrees + main:
            # Skip if directory doesn't exist (stale worktree)
            if not ws_path.exists():
                continue
            if is_container_running(ws_path):
                if stop_container(ws_path):
                    any_stopped = True

        if not any_stopped:
            print("No running containers found for this project")
    else:
        if not stop_container(git_root):
            sys.exit(1)


def find_containers_for_project(
    git_root: Path, state_filter: str | None = None
) -> list[tuple[str, str, str]]:
    """Find containers for a project.

    Args:
        git_root: The git repository root path
        state_filter: If set, only return containers in this state (e.g., "running")
                      If None, return all containers

    Returns list of tuples: (container_name, workspace_folder, state)
    """
    runtime = get_container_runtime()
    if runtime is None:
        return []

    project_name = git_root.name

    # Get all containers (including stopped) with devcontainer label
    all_containers = list_all_devcontainers()

    # Filter to containers that match this project
    matched = []
    for name, folder, state in all_containers:
        # Check if folder is under this project or its worktrees
        folder_path = Path(folder)
        if (
            folder_path == git_root
            or folder_path.parent.name == f"{project_name}-worktrees"
        ):
            if state_filter is None or state == state_filter:
                matched.append((name, folder, state))

    return matched


def find_stopped_containers_for_project(git_root: Path) -> list[tuple[str, str]]:
    """Find stopped containers for a project.

    Returns list of tuples: (container_name, workspace_folder)
    """
    containers = find_containers_for_project(git_root)
    return [(name, folder) for name, folder, state in containers if state != "running"]


def find_stale_worktrees(git_root: Path) -> list[tuple[Path, str]]:
    """Find worktrees that no longer exist on disk.

    Returns list of tuples: (worktree_path, branch_name)
    """
    worktrees = list_worktrees(git_root)
    stale = []

    for wt_path, _, branch in worktrees:
        if wt_path == git_root:
            continue  # Skip main repo
        if not wt_path.exists():
            stale.append((wt_path, branch))

    return stale


def remove_container(container_name: str) -> bool:
    """Remove a container."""
    runtime = get_container_runtime()
    if runtime is None:
        return False

    cmd = [runtime, "rm", container_name]
    verbose_cmd(cmd)
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0


def remove_worktree(git_root: Path, worktree_path: Path) -> bool:
    """Remove a git worktree."""
    cmd = ["git", "worktree", "remove", "--force", str(worktree_path)]
    verbose_cmd(cmd)
    result = subprocess.run(cmd, cwd=git_root, capture_output=True, text=True)
    return result.returncode == 0


def run_prune_global_mode() -> None:
    """Run --prune --all mode: clean up all stopped devcontainers globally."""
    all_containers = list_all_devcontainers()
    stopped_containers = [(name, folder) for name, folder, state in all_containers if state != "running"]

    if not stopped_containers:
        print("No stopped containers to prune.")
        return

    print("Stopped containers:")
    for name, folder in stopped_containers:
        print(f"  {name:<24} {folder}")
    print()

    # Prompt for confirmation
    try:
        response = input("Remove these? [y/N] ")
    except (EOFError, KeyboardInterrupt):
        print()
        return

    if response.lower() != "y":
        print("Cancelled.")
        return

    for name, _ in stopped_containers:
        if remove_container(name):
            print(f"Removed: {name}")
        else:
            print(f"Failed to remove: {name}", file=sys.stderr)


def run_prune_mode(args: argparse.Namespace) -> None:
    """Run --prune mode: clean up stopped containers and stale worktrees."""
    git_root = find_git_root()

    # Prune all stopped containers if --all flag or not in a git repo
    if args.all or git_root is None:
        run_prune_global_mode()
        return

    # Find stopped containers
    stopped_containers = find_stopped_containers_for_project(git_root)

    # Find stale worktrees
    stale_worktrees = find_stale_worktrees(git_root)

    if not stopped_containers and not stale_worktrees:
        print("Nothing to prune.")
        return

    # Show what will be pruned
    if stopped_containers:
        print("Stopped containers:")
        for name, folder in stopped_containers:
            print(f"  {name:<24} {folder}")
        print()

    if stale_worktrees:
        print("Stale worktrees:")
        for wt_path, branch in stale_worktrees:
            print(f"  {wt_path.name:<24} ({branch})")
        print()

    # Prompt for confirmation
    try:
        response = input("Remove these? [y/N] ")
    except (EOFError, KeyboardInterrupt):
        print()
        return

    if response.lower() != "y":
        print("Cancelled.")
        return

    # Remove containers
    for name, _ in stopped_containers:
        if remove_container(name):
            print(f"Removed container: {name}")
        else:
            print(f"Failed to remove container: {name}", file=sys.stderr)

    # Remove worktrees
    for wt_path, _ in stale_worktrees:
        if remove_worktree(git_root, wt_path):
            print(f"Removed worktree: {wt_path.name}")
        else:
            print(f"Failed to remove worktree: {wt_path.name}", file=sys.stderr)


def run_destroy_mode(args: argparse.Namespace) -> None:
    """Run --destroy mode: stop and remove all containers for project."""
    # If path argument provided, use it; otherwise detect from cwd
    if args.destroy:
        target_path = Path(args.destroy).resolve()
        if not target_path.exists():
            sys.exit(f"Error: Path does not exist: {target_path}")
        git_root = find_git_root(target_path)
        if git_root is None:
            sys.exit(f"Error: Not a git repository: {target_path}")
    else:
        git_root = find_git_root()
        if git_root is None:
            sys.exit("Error: Not in a git repository.")

    runtime = get_container_runtime()
    if runtime is None:
        sys.exit("Error: No container runtime found (docker or podman required)")

    # Find all containers for this project
    containers = find_containers_for_project(git_root)

    if not containers:
        print("No containers found for this project.")
        return

    # Show what will be destroyed
    print(f"Project: {git_root.name}")
    print()
    print("Containers to destroy:")
    for name, folder, state in containers:
        print(f"  {name:<24} {state:<10} {folder}")
    print()

    # Prompt for confirmation
    try:
        response = input("Stop and remove these containers? [y/N] ")
    except (EOFError, KeyboardInterrupt):
        print()
        return

    if response.lower() != "y":
        print("Cancelled.")
        return

    # Stop running containers first
    for name, folder, state in containers:
        if state == "running":
            cmd = [runtime, "stop", name]
            verbose_cmd(cmd)
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                print(f"Stopped: {name}")
            else:
                print(f"Failed to stop {name}: {result.stderr}", file=sys.stderr)

    # Remove all containers
    for name, folder, state in containers:
        if remove_container(name):
            print(f"Removed: {name}")
        else:
            print(f"Failed to remove: {name}", file=sys.stderr)

    print()
    print(f"Done. You can now: rm -rf {git_root}")
    worktrees_dir = git_root.parent / f"{git_root.name}-worktrees"
    if worktrees_dir.exists():
        print(f"              and: rm -rf {worktrees_dir}")


def run_attach_mode(args: argparse.Namespace) -> None:
    """Run --attach mode: attach to running container."""
    git_root = find_git_root()

    if git_root is None:
        sys.exit("Error: Not in a git repository.")

    if not is_container_running(git_root):
        sys.exit("Error: Container is not running. Use yolo to start it.")

    # Attach to tmux
    devcontainer_exec_tmux(git_root)


def run_list_mode(args: argparse.Namespace) -> None:
    """Run --list mode: show containers and worktrees for current project."""
    git_root = find_git_root()

    # Show all containers if --all flag or not in a git repo
    if args.all or git_root is None:
        run_list_global_mode()
        return

    project_name = git_root.name

    print(f"Project: {project_name}")
    print()

    # Find all workspaces
    workspaces = find_project_workspaces(git_root)

    # Check container status for each
    print("Containers:")
    any_running = False
    for ws_path, ws_type in workspaces:
        devcontainer_dir = ws_path / ".devcontainer"
        if devcontainer_dir.exists():
            running = is_container_running(ws_path)
            status = "running" if running else "stopped"
            status_marker = "*" if running else " "
            print(f"  {status_marker} {ws_path.name:<20} {status:<10} ({ws_type})")
            if running:
                any_running = True

    if not any_running:
        print("  (no containers running)")
    print()

    # List worktrees
    worktrees = list_worktrees(git_root)
    if len(worktrees) > 1:  # More than just main repo
        print("Worktrees:")
        for wt_path, commit, branch in worktrees:
            if wt_path == git_root:
                continue  # Skip main repo
            print(f"    {wt_path.name:<20} {branch:<15} [{commit}]")
    else:
        print("Worktrees: (none)")


def run_default_mode(args: argparse.Namespace) -> None:
    """Run default mode: start devcontainer in current git project."""
    git_root = find_git_root()

    if git_root is None:
        sys.exit("Error: Not in a git repository. Use --init to initialize here.")

    os.chdir(git_root)
    project_name = git_root.name

    # Load config
    config = load_config()

    # Scaffold .devcontainer if missing
    scaffold_devcontainer(project_name, config=config)

    # Set up secrets in environment
    secrets = get_secrets(config)
    os.environ.update(secrets)

    # Start devcontainer only if not already running (or --new forces restart)
    if args.new or not is_container_running(git_root):
        if not devcontainer_up(git_root, remove_existing=args.new):
            sys.exit("Error: Failed to start devcontainer")

    if args.detach:
        print(f"Container started: {project_name}")
        return

    # Attach to tmux
    devcontainer_exec_tmux(git_root)


def branch_exists(git_root: Path, branch: str) -> bool:
    """Check if a branch or ref exists in the repository."""
    result = subprocess.run(
        ["git", "rev-parse", "--verify", branch], cwd=git_root, capture_output=True
    )
    return result.returncode == 0


def get_or_create_worktree(
    git_root: Path,
    worktree_name: str,
    worktree_path: Path,
    config: dict | None = None,
    from_branch: str | None = None,
) -> Path:
    """Get existing worktree or create a new one.

    Returns the worktree path. If the worktree already exists, just returns
    the path. If it doesn't exist, creates the worktree with devcontainer.

    If from_branch is specified, creates the worktree from that branch.
    """
    if worktree_path.exists():
        print(f"Using existing worktree: {worktree_path}")
        return worktree_path

    # Create worktrees directory if needed
    worktree_path.parent.mkdir(parents=True, exist_ok=True)

    # Create git worktree with new branch
    cmd = ["git", "worktree", "add", "-b", worktree_name, str(worktree_path)]
    if from_branch:
        cmd.append(from_branch)

    verbose_cmd(cmd)
    result = subprocess.run(cmd, cwd=git_root)
    if result.returncode != 0:
        sys.exit("Error: Failed to create git worktree")

    # Set up .devcontainer in worktree
    src_devcontainer = git_root / ".devcontainer"
    dst_devcontainer = worktree_path / ".devcontainer"

    if dst_devcontainer.exists():
        # Already checked out by git worktree (was committed to repo)
        pass
    elif src_devcontainer.exists():
        # Copy from main repo (not committed, just local)
        shutil.copytree(src_devcontainer, dst_devcontainer)
    else:
        # Scaffold new .devcontainer
        container_name = get_container_name(str(git_root), worktree_name)
        scaffold_devcontainer(container_name, worktree_path, config=config)

    # Add mount for main repo's .git directory so worktree git operations work
    main_git_dir = git_root / ".git"
    devcontainer_json = dst_devcontainer / "devcontainer.json"
    add_worktree_git_mount(devcontainer_json, main_git_dir)

    print(f"Created worktree: {worktree_path}")
    print(f"Branch: {worktree_name}")

    return worktree_path


def run_tree_mode(args: argparse.Namespace) -> None:
    """Run --tree mode: create worktree and start devcontainer."""
    git_root = validate_tree_mode()

    # Validate --from branch if specified
    if args.from_branch and not branch_exists(git_root, args.from_branch):
        sys.exit(f"Error: Branch does not exist: {args.from_branch}")

    # Generate name if not provided
    worktree_name = args.tree if args.tree else generate_random_name()

    # Compute paths
    worktree_path = get_worktree_path(str(git_root), worktree_name)

    # Load config
    config = load_config()

    # Get or create the worktree
    worktree_path = get_or_create_worktree(
        git_root,
        worktree_name,
        worktree_path,
        config=config,
        from_branch=args.from_branch,
    )

    # Set up secrets in environment
    secrets = get_secrets(config)
    os.environ.update(secrets)

    # Start devcontainer only if not already running (or --new forces restart)
    if args.new or not is_container_running(worktree_path):
        if not devcontainer_up(worktree_path, remove_existing=args.new):
            sys.exit("Error: Failed to start devcontainer")

    if args.detach:
        print(f"Container started: {worktree_path.name}")
        return

    # Attach to tmux
    devcontainer_exec_tmux(worktree_path)


def run_create_mode(args: argparse.Namespace) -> None:
    """Run --create mode: create new project with devcontainer."""
    validate_create_mode(args.create)

    project_name = args.create
    project_path = Path.cwd() / project_name

    # Load config
    config = load_config()

    # Create project directory
    project_path.mkdir()

    # Initialize git repo
    cmd = ["git", "init"]
    verbose_cmd(cmd)
    result = subprocess.run(cmd, cwd=project_path)
    if result.returncode != 0:
        sys.exit("Error: Failed to initialize git repository")

    # Scaffold .devcontainer
    scaffold_devcontainer(project_name, project_path, config=config)

    # Initial commit with .devcontainer
    cmd = ["git", "add", ".devcontainer"]
    verbose_cmd(cmd)
    subprocess.run(cmd, cwd=project_path)

    cmd = ["git", "commit", "-m", "Initial commit with devcontainer setup"]
    verbose_cmd(cmd)
    subprocess.run(cmd, cwd=project_path)

    print(f"Created project: {project_path}")

    # Change to project directory for devcontainer commands
    os.chdir(project_path)

    # Set up secrets in environment
    secrets = get_secrets(config)
    os.environ.update(secrets)

    # Start devcontainer (always remove existing for fresh project)
    if not devcontainer_up(project_path, remove_existing=True):
        sys.exit("Error: Failed to start devcontainer")

    if args.detach:
        print(f"Container started: {project_name}")
        return

    # Attach to tmux
    devcontainer_exec_tmux(project_path)


def run_init_mode(args: argparse.Namespace) -> None:
    """Run --init mode: initialize git + devcontainer in current directory."""
    validate_init_mode()

    project_path = Path.cwd()
    project_name = project_path.name

    # Load config
    config = load_config()

    # Initialize git repo
    cmd = ["git", "init"]
    verbose_cmd(cmd)
    result = subprocess.run(cmd, cwd=project_path)
    if result.returncode != 0:
        sys.exit("Error: Failed to initialize git repository")

    # Scaffold .devcontainer
    scaffold_devcontainer(project_name, project_path, config=config)

    # Initial commit with .devcontainer
    cmd = ["git", "add", ".devcontainer"]
    verbose_cmd(cmd)
    subprocess.run(cmd, cwd=project_path)

    cmd = ["git", "commit", "-m", "Initial commit with devcontainer setup"]
    verbose_cmd(cmd)
    subprocess.run(cmd, cwd=project_path)

    print(f"Initialized: {project_path}")

    # Set up secrets in environment
    secrets = get_secrets(config)
    os.environ.update(secrets)

    # Start devcontainer (always remove existing for fresh project)
    if not devcontainer_up(project_path, remove_existing=True):
        sys.exit("Error: Failed to start devcontainer")

    if args.detach:
        print(f"Container started: {project_name}")
        return

    # Attach to tmux
    devcontainer_exec_tmux(project_path)


def run_sync_mode(args: argparse.Namespace) -> None:
    """Run --sync mode: regenerate .devcontainer from template."""
    git_root = find_git_root()

    if git_root is None:
        sys.exit("Error: Not in a git repository.")

    os.chdir(git_root)
    project_name = git_root.name

    # Load config
    config = load_config()

    # Sync .devcontainer
    sync_devcontainer(project_name, config=config)


def main(argv: list[str] | None = None) -> None:
    """Main entry point."""
    global VERBOSE

    if argv is None:
        argv = sys.argv[1:]

    args = parse_args(argv)

    # Set verbose mode
    if args.verbose:
        VERBOSE = True

    # These modes don't need tmux guard (no container attachment)
    if args.sync:
        run_sync_mode(args)
        return

    if args.list:
        run_list_mode(args)
        return

    if args.stop:
        run_stop_mode(args)
        return

    if args.prune:
        run_prune_mode(args)
        return

    if args.destroy is not None:
        run_destroy_mode(args)
        return

    # Check guards (skip tmux guard if detaching)
    if not args.detach:
        check_tmux_guard()

    # Dispatch to appropriate mode
    if args.attach:
        run_attach_mode(args)
    elif args.init:
        run_init_mode(args)
    elif args.create:
        run_create_mode(args)
    elif args.tree is not None:
        run_tree_mode(args)
    else:
        run_default_mode(args)


if __name__ == "__main__":
    main()
