"""Container management functions for jolo."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from _jolo import constants
from _jolo.cli import (
    detect_hostname,
    is_port_available,
    random_port,
    read_port_from_devcontainer,
    verbose_cmd,
)


def build_devcontainer_json(project_name: str, port: int | None = None) -> str:
    """Build devcontainer.json content dynamically.

    Conditionally includes Wayland mount only if WAYLAND_DISPLAY is set.
    Auto-detects Tailscale hostname for DEV_HOST.

    Args:
        project_name: Name of the project/container
        port: Port number for dev servers (random in 4000-5000 if not specified)
    """
    if port is None:
        port = random_port()

    hostname = detect_hostname()

    mounts = constants.BASE_MOUNTS.copy()

    # Only add Wayland mount if WAYLAND_DISPLAY is set
    if os.environ.get("WAYLAND_DISPLAY"):
        mounts.append(constants.WAYLAND_MOUNT)

    workspace_folder = f"/workspaces/{project_name}"
    config = {
        "name": project_name,
        "build": {"dockerfile": "Dockerfile"},
        "workspaceFolder": workspace_folder,
        "runArgs": [
            "--hostname", project_name,
            "--name", project_name,
            "-p", f"{port}:{port}",
        ],
        "mounts": mounts,
        "containerEnv": {
            "TERM": "xterm-256color",
            "WAYLAND_DISPLAY": "${localEnv:WAYLAND_DISPLAY}",
            "XDG_RUNTIME_DIR": "/tmp/container-runtime",
            "ANTHROPIC_API_KEY": "${localEnv:ANTHROPIC_API_KEY}",
            "OPENAI_API_KEY": "${localEnv:OPENAI_API_KEY}",
            "PORT": str(port),
            "DEV_HOST": hostname,
            "WORKSPACE_FOLDER": workspace_folder,
        },
    }

    return json.dumps(config, indent=4)


def is_container_running(workspace_dir: Path) -> bool:
    """Check if devcontainer for workspace is already running."""
    cmd = ["devcontainer", "exec", "--workspace-folder", str(workspace_dir), "true"]
    verbose_cmd(cmd)
    result = subprocess.run(cmd, capture_output=True, cwd=workspace_dir)
    return result.returncode == 0


def devcontainer_up(workspace_dir: Path, remove_existing: bool = False) -> bool:
    """Start devcontainer with devcontainer up.

    Checks port availability before launching. Returns True if successful.
    """
    # Check port availability before starting
    port = read_port_from_devcontainer(workspace_dir)
    if port is not None and not is_port_available(port):
        print(
            f"Error: Port {port} is already in use.\n"
            f"Either stop the process using it, or change PORT in "
            f".devcontainer/devcontainer.json"
        )
        return False

    # Ensure histfile exists as a file (otherwise mount creates a directory)
    histfile = workspace_dir / ".devcontainer" / ".histfile"
    histfile.touch(exist_ok=True)

    cmd = ["devcontainer", "up", "--workspace-folder", str(workspace_dir)]

    if remove_existing:
        cmd.append("--remove-existing-container")

    verbose_cmd(cmd)
    result = subprocess.run(cmd, cwd=workspace_dir)
    return result.returncode == 0


def devcontainer_exec_tmux(workspace_dir: Path) -> None:
    """Execute into container and attach/create tmux session."""
    shell_cmd = (
        "if [ -x \"$HOME/tmux-layout.sh\" ]; then exec \"$HOME/tmux-layout.sh\"; "
        "else tmux attach-session -d -t dev || tmux new-session -s dev; fi"
    )
    cmd = [
        "devcontainer",
        "exec",
        "--workspace-folder",
        str(workspace_dir),
        "sh",
        "-c",
        shell_cmd,
    ]

    verbose_cmd(cmd)
    subprocess.run(cmd, cwd=workspace_dir)


def devcontainer_exec_command(workspace_dir: Path, command: str) -> None:
    """Execute a command directly in container (no tmux)."""
    cmd = [
        "devcontainer",
        "exec",
        "--workspace-folder",
        str(workspace_dir),
        "sh",
        "-c",
        command,
    ]

    verbose_cmd(cmd)
    subprocess.run(cmd, cwd=workspace_dir)


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


def remove_container(container_name: str) -> bool:
    """Remove a container."""
    runtime = get_container_runtime()
    if runtime is None:
        return False

    cmd = [runtime, "rm", container_name]
    verbose_cmd(cmd)
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0
