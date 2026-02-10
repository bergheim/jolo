"""Container management functions for jolo."""

import json
import os
import shutil
import socket
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


def build_devcontainer_json(
    project_name: str,
    port: int | None = None,
    base_image: str | None = None,
    remote_user: str | None = None,
) -> str:
    """Build devcontainer.json content dynamically.

    Conditionally includes Wayland mount only if WAYLAND_DISPLAY is set.
    Auto-detects Tailscale hostname for DEV_HOST.

    Args:
        project_name: Name of the project/container
        port: Port number for dev servers (random in 4000-5000 if not specified)
    """
    if port is None:
        port = random_port()

    if base_image is None:
        base_image = constants.DEFAULT_CONFIG["base_image"]

    if remote_user is None:
        remote_user = os.environ.get("USER", "dev")

    hostname = detect_hostname()

    mounts = constants.BASE_MOUNTS.copy()

    # Only add Wayland mount if WAYLAND_DISPLAY is set
    if os.environ.get("WAYLAND_DISPLAY"):
        mounts.append(constants.WAYLAND_MOUNT)

    workspace_folder = f"/workspaces/{project_name}"
    config = {
        "name": project_name,
        "image": base_image,
        "workspaceFolder": workspace_folder,
        "remoteUser": remote_user,
        "updateRemoteUserUID": False,
        "userEnvProbe": "none",
        "runArgs": [
            "--hostname",
            project_name,
            "--name",
            project_name,
            "--add-host",
            f"{socket.gethostname()}:host-gateway",
            "-p",
            f"{port}:{port}",
        ],
        "mounts": mounts,
        "containerEnv": {
            "TERM": "xterm-256color",
            "WAYLAND_DISPLAY": "${localEnv:WAYLAND_DISPLAY}",
            "XDG_RUNTIME_DIR": "/tmp/container-runtime",
            "ANTHROPIC_API_KEY": "${localEnv:ANTHROPIC_API_KEY}",
            "OPENAI_API_KEY": "${localEnv:OPENAI_API_KEY}",
            "GH_TOKEN": "${localEnv:GH_TOKEN}",
            "PORT": str(port),
            "DEV_HOST": hostname,
            "WORKSPACE_FOLDER": workspace_folder,
            "HISTFILE": f"/home/{remote_user}/.zsh-state/.histfile",
            "NTFY_TOPIC": "jolo",
            "NTFY_SERVER": "${localEnv:NTFY_SERVER}",
            "PROJECT": project_name,
        },
    }

    return json.dumps(config, indent=4)


def is_container_running(workspace_dir: Path) -> bool:
    """Check if devcontainer for workspace is already running."""
    runtime = get_container_runtime()
    if runtime is None:
        return False

    # Query running containers with matching workspace folder label
    result = subprocess.run(
        [
            runtime,
            "ps",
            "--filter",
            f"label=devcontainer.local_folder={workspace_dir}",
            "--filter",
            "status=running",
            "--format",
            "{{.Names}}",
        ],
        capture_output=True,
        text=True,
    )

    return bool(result.stdout.strip())


def reassign_port(workspace_dir: Path) -> int:
    """Pick a new available port and rewrite devcontainer.json."""
    devcontainer_json = workspace_dir / ".devcontainer" / "devcontainer.json"
    config = json.loads(devcontainer_json.read_text())

    new_port = random_port()
    while not is_port_available(new_port):
        new_port = random_port()

    old_port = config.get("containerEnv", {}).get("PORT")
    config["containerEnv"]["PORT"] = str(new_port)

    # Update the -p runArg
    run_args = config.get("runArgs", [])
    for i, arg in enumerate(run_args):
        if i > 0 and run_args[i - 1] == "-p" and old_port and old_port in arg:
            run_args[i] = f"{new_port}:{new_port}"
            break

    devcontainer_json.write_text(json.dumps(config, indent=4) + "\n")
    return new_port


def devcontainer_up(workspace_dir: Path, remove_existing: bool = False) -> bool:
    """Start devcontainer with devcontainer up.

    Checks port availability before launching. Returns True if successful.
    """
    port = read_port_from_devcontainer(workspace_dir)
    if port is not None and not is_port_available(port):
        # Our own container will free the port when removed
        if remove_existing and is_container_running(workspace_dir):
            pass
        elif sys.stdin.isatty():
            try:
                answer = input(f"Port {port} is in use. Assign a new random port? [Y/n] ")
            except (KeyboardInterrupt, EOFError):
                return False
            if answer.strip().lower() not in ("", "y", "yes"):
                print(f"Error: Port {port} is already in use.")
                return False
            port = reassign_port(workspace_dir)
            print(f"Reassigned to port {port}")
        else:
            print(f"Error: Port {port} is already in use.")
            return False

    # zsh-state dir: zsh needs rename() for histfile, which fails across filesystems
    (workspace_dir / ".devcontainer" / ".zsh-state").mkdir(exist_ok=True)

    cmd = ["devcontainer", "up", "--workspace-folder", str(workspace_dir)]

    if remove_existing:
        cmd.append("--remove-existing-container")

    verbose_cmd(cmd)
    result = subprocess.run(cmd, cwd=workspace_dir)
    return result.returncode == 0


def _runtime_exec(workspace_dir: Path, command: str, interactive: bool = False) -> bool:
    """Try executing a command via the container runtime directly.

    Returns True if successful, False if we should fall back to devcontainer CLI.
    """
    runtime = get_container_runtime()
    container_name = get_container_for_workspace(workspace_dir)

    if not runtime or not container_name:
        return False

    user = os.environ.get("USER", "dev")
    project_name = workspace_dir.name
    workspace_folder = f"/workspaces/{project_name}"

    cmd = [runtime, "exec"]
    if interactive:
        cmd.append("-it")
    cmd.extend(["-u", user, "-w", workspace_folder, container_name, "sh", "-c", command])

    verbose_cmd(cmd)
    result = subprocess.run(cmd)
    return result.returncode == 0


def devcontainer_exec_tmux(workspace_dir: Path) -> None:
    """Execute into container and attach/create tmux session."""
    shell_cmd = (
        'if [ -x "$HOME/tmux-layout.sh" ]; then exec "$HOME/tmux-layout.sh"; '
        "else tmux attach-session -d -t dev || tmux new-session -s dev; fi"
    )

    if _runtime_exec(workspace_dir, shell_cmd, interactive=True):
        return

    # Fallback: slow path via devcontainer CLI
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
    if _runtime_exec(workspace_dir, command):
        return

    # Fallback: slow path via devcontainer CLI
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


def list_all_devcontainers() -> list[tuple[str, str, str, str]]:
    """List all running devcontainers globally.

    Returns list of tuples: (container_name, workspace_folder, status, image_id)
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
            '{{.Names}}\t{{.Label "devcontainer.local_folder"}}\t{{.State}}\t{{.ImageID}}',
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
        if len(parts) >= 4:
            name, folder, state, image_id = parts[0], parts[1], parts[2], parts[3]
            containers.append((name, folder, state, image_id))

    return containers


def get_container_for_workspace(workspace_dir: Path) -> str | None:
    """Get container name for a workspace directory.

    Returns container name if found, None otherwise. Prefers running containers.
    """
    runtime = get_container_runtime()
    if runtime is None:
        return None

    # Query containers with matching workspace folder, sorted by status (running first)
    result = subprocess.run(
        [
            runtime,
            "ps",
            "-a",
            "--filter",
            f"label=devcontainer.local_folder={workspace_dir}",
            "--format",
            "{{.Names}}\t{{.State}}",
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0 or not result.stdout.strip():
        return None

    lines = result.stdout.strip().split("\n")

    # Check for running ones first
    for line in lines:
        parts = line.split("\t")
        if len(parts) >= 2 and parts[1] == "running":
            return parts[0]

    # Fall back to first available (stopped)
    return lines[0].split("\t")[0]


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


def find_containers_for_project(git_root: Path, state_filter: str | None = None) -> list[tuple[str, str, str, str]]:
    """Find containers for a project.

    Args:
        git_root: The git repository root path
        state_filter: If set, only return containers in this state (e.g., "running")
                      If None, return all containers

    Returns list of tuples: (container_name, workspace_folder, state, image_id)
    """
    runtime = get_container_runtime()
    if runtime is None:
        return []

    project_name = git_root.name

    # Get all containers (including stopped) with devcontainer label
    all_containers = list_all_devcontainers()

    # Filter to containers that match this project
    matched = []
    for name, folder, state, image_id in all_containers:
        # Check if folder is under this project or its worktrees
        folder_path = Path(folder)
        if folder_path == git_root or folder_path.parent.name == f"{project_name}-worktrees":
            if state_filter is None or state == state_filter:
                matched.append((name, folder, state, image_id))

    return matched


def find_stopped_containers_for_project(git_root: Path) -> list[tuple[str, str, str]]:
    """Find stopped containers for a project.

    Returns list of tuples: (container_name, workspace_folder, image_id)
    """
    containers = find_containers_for_project(git_root)
    return [(name, folder, image_id) for name, folder, state, image_id in containers if state != "running"]


def remove_container(container_name: str) -> bool:
    """Remove a container."""
    runtime = get_container_runtime()
    if runtime is None:
        return False

    cmd = [runtime, "rm", container_name]
    verbose_cmd(cmd)
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0


def remove_image(image_id: str) -> bool:
    """Remove an image."""
    runtime = get_container_runtime()
    if runtime is None:
        return False

    cmd = [runtime, "rmi", image_id]
    verbose_cmd(cmd)
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0
