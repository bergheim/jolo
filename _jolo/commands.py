"""Command handler functions and main dispatcher for jolo."""

import argparse
import json
import os
import random
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import tomllib

from _jolo import constants
from _jolo.cli import (
    _format_container_display,
    check_tmux_guard,
    clipboard_copy,
    detect_flavors,
    detect_hostname,
    find_git_root,
    generate_random_name,
    is_port_available,
    parse_args,
    parse_copy,
    parse_mount,
    read_port_from_devcontainer,
    select_flavors_interactive,
    slugify_prompt,
    verbose_cmd,
    verbose_print,
)
from _jolo.container import (
    devcontainer_exec_command,
    devcontainer_exec_tmux,
    devcontainer_up,
    find_containers_for_project,
    find_stopped_containers_for_project,
    get_container_for_workspace,
    get_container_runtime,
    is_container_running,
    list_all_devcontainers,
    reassign_port,
    remove_container,
    remove_image,
    set_port,
    stop_container,
)
from _jolo.setup import (
    add_user_mounts,
    copy_template_files,
    copy_user_files,
    ensure_test_gate_script,
    get_secrets,
    scaffold_devcontainer,
    setup_credential_cache,
    setup_emacs_config,
    setup_notification_hooks,
    setup_stash,
    sync_devcontainer,
    sync_skill_templates,
    sync_template_files,
    write_prompt_file,
)
from _jolo.templates import (
    generate_precommit_config,
    get_justfile_common_content,
    get_justfile_content,
    get_motd_content,
    get_precommit_install_command,
    get_project_init_commands,
    get_scaffold_files,
    get_test_framework_config,
    get_type_checker_config,
    to_pascal_case,
    to_snake_case,
)
from _jolo.worktree import (
    branch_exists,
    find_project_workspaces,
    find_stale_worktrees,
    get_or_create_worktree,
    get_worktree_path,
    list_worktrees,
    remove_worktree,
    validate_create_mode,
    validate_init_mode,
    validate_tree_mode,
)


def get_agent_command(
    config: dict, agent_name: str | None = None, index: int = 0
) -> str:
    """Get the command to run an agent.

    Args:
        config: Configuration dict
        agent_name: Specific agent name, or None for round-robin based on index
        index: Index for round-robin selection (used when agent_name is None)

    Returns:
        The command string to run the agent
    """
    agents = config.get("agents", ["claude"])
    agent_commands = config.get("agent_commands", {})

    if agent_name:
        # Specific agent requested
        name = agent_name
    else:
        # Round-robin through available agents
        name = agents[index % len(agents)]

    # Get command, fall back to just the agent name
    return agent_commands.get(name, name)


def get_agent_name(
    config: dict, agent_name: str | None = None, index: int = 0
) -> str:
    """Get the agent name for a given index.

    Args:
        config: Configuration dict
        agent_name: Specific agent name, or None for round-robin based on index
        index: Index for round-robin selection

    Returns:
        The agent name
    """
    if agent_name:
        return agent_name

    agents = config.get("agents", ["claude"])
    return agents[index % len(agents)]


def _fzf_pick(header: str, labels: list[str]) -> str | None:
    """Run fzf picker with the given header and labels, return selected line."""
    try:
        result = subprocess.run(
            [
                "fzf",
                "--header",
                header,
                "--height",
                "~10",
                "--layout",
                "reverse",
                "--no-multi",
            ],
            input="\n".join(labels),
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return None
        return result.stdout.rstrip("\n")
    except KeyboardInterrupt:
        return None


def _sync_config(
    name: str, path: Path, config: dict, force: bool = False, **kwargs: int
) -> None:
    """Sync devcontainer config, skill templates, and template files."""
    sync_devcontainer(name, target_dir=path, config=config, **kwargs)
    sync_skill_templates(path)
    sync_template_files(path, force=force)


def _setup_container_env(workspace: Path, config: dict) -> None:
    """Set up secrets, credentials, hooks, and Emacs config for a container."""
    secrets = get_secrets(config)
    os.environ.update(secrets)
    setup_credential_cache(workspace)
    setup_notification_hooks(workspace, config.get("notify_threshold", 60))
    setup_emacs_config(workspace)
    setup_stash()


def load_config(
    global_config_dir: Path | None = None,
    project_dir: Path | None = None,
) -> dict:
    """Load configuration from TOML files.

    Config is loaded in order (later overrides earlier):
    1. Default config
    2. Global config: ~/.config/jolo/config.toml
    3. Project config: .jolo.toml in project_dir (defaults to cwd)
    """
    config = constants.DEFAULT_CONFIG.copy()

    if global_config_dir is None:
        global_config_dir = Path.home() / ".config" / "jolo"

    # Load global config
    global_config_file = global_config_dir / "config.toml"
    if global_config_file.exists():
        with open(global_config_file, "rb") as f:
            global_cfg = tomllib.load(f)
            config.update(global_cfg)

    # Load project config
    base = project_dir if project_dir is not None else Path.cwd()
    project_config_file = base / ".jolo.toml"
    if project_config_file.exists():
        with open(project_config_file, "rb") as f:
            project_cfg = tomllib.load(f)
            config.update(project_cfg)

    return config


def infer_repo_name(url: str) -> str:
    """Infer repo name from a git URL or path."""
    raw = url.strip().rstrip("/")
    if raw.endswith(".git"):
        raw = raw[:-4]

    if "://" in raw:
        # https://host/org/repo
        path = raw.split("://", 1)[1]
        path = path.split("/", 1)[1] if "/" in path else ""
    elif ":" in raw and "@" in raw.split(":", 1)[0]:
        # git@host:org/repo
        path = raw.split(":", 1)[1]
    else:
        # local path or already a repo name
        path = raw

    name = Path(path).name if path else Path(raw).name
    if not name:
        sys.exit(f"Error: Unable to infer repo name from URL: {url}")
    return name


def pick_project() -> Path:
    """Resolve the current project, or fzf-pick from running containers.

    If we're inside a git repo, returns its root. Otherwise, discovers
    projects from running devcontainers and lets the user pick with fzf.
    """
    git_root = find_git_root()
    if git_root is not None:
        return git_root

    containers = list_all_devcontainers()
    # Dedupe to unique workspace folders
    folders = list(
        dict.fromkeys(
            folder
            for _name, folder, state, _img in containers
            if state == "running" and Path(folder).exists()
        )
    )

    if not folders:
        sys.exit("Not in a git repo and no running containers found.")

    if len(folders) == 1:
        return Path(folders[0])

    labels = [f"{Path(f).name:<24} {f}" for f in folders]
    selected = _fzf_pick("Pick a project:", labels)
    if selected is None:
        sys.exit(0)
    idx = labels.index(selected)
    return Path(folders[idx])


def run_exec_mode(args: argparse.Namespace) -> None:
    """Run exec mode: execute a command in the running devcontainer."""
    git_root = pick_project()

    cmd_parts = [c for c in args.exec_command if c != "--"]
    if not cmd_parts:
        sys.exit("Usage: jolo exec <command>")

    devcontainer_exec_command(git_root, " ".join(cmd_parts))


def run_list_global_mode() -> None:
    """Run --list --all mode: show all running devcontainers globally."""
    runtime = get_container_runtime()
    if runtime is None:
        sys.exit(
            "Error: No container runtime found (docker or podman required)"
        )

    containers = list_all_devcontainers()

    print("Running devcontainers:")
    print()

    running_containers = [
        (n, f, s, i) for n, f, s, i in containers if s == "running"
    ]

    if not running_containers:
        print("  (none)")
    else:
        for name, folder, _, _ in running_containers:
            print(f"  {name:<24} {folder}")

    # Also show stopped containers
    stopped_containers = [
        (n, f, s, i) for n, f, s, i in containers if s != "running"
    ]
    if stopped_containers:
        print()
        print("Stopped devcontainers:")
        print()
        for name, folder, state, _ in stopped_containers:
            print(f"  {name:<24} {folder}  ({state})")


def run_stop_mode(args: argparse.Namespace) -> None:
    """Run --stop mode: stop the devcontainer for current project."""
    git_root = pick_project()

    if args.all:
        # Stop all containers for this project (worktrees first, then main)
        workspaces = find_project_workspaces(git_root)
        # Reverse so worktrees come before main
        worktrees = [(p, t) for p, t in workspaces if t != "main"]
        main = [(p, t) for p, t in workspaces if t == "main"]

        any_stopped = False
        for ws_path, _ws_type in worktrees + main:
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


def run_port_mode(args: argparse.Namespace) -> None:
    """Show or change the project port."""
    git_root = pick_project()

    if args.random and args.port is not None:
        sys.exit("Error: Cannot use --random with a specific port number.")

    if args.random:
        new_port = reassign_port(git_root)
        print(f"Port reassigned to {new_port}")
        if is_container_running(git_root):
            print("Note: restart container to apply (jolo up --recreate)")
        return

    if args.port is not None:
        port = args.port
        if not 1 <= port <= 65535:
            sys.exit(f"Error: Port must be between 1 and 65535, got {port}.")
        if not is_port_available(port):
            print(
                f"Warning: Port {port} is currently in use.", file=sys.stderr
            )
        set_port(git_root, port)
        print(f"Port set to {port}")
        if is_container_running(git_root):
            print("Note: restart container to apply (jolo up --recreate)")
        return

    # Show current port + usage
    port = read_port_from_devcontainer(git_root)
    if port is None:
        sys.exit("No port configured. Run 'jolo up' first.")
    print(f"{port}")
    print("\nUsage: jolo port NUMBER   assign a specific port")
    print("       jolo port --random assign a random port")


def run_prune_global_mode() -> None:
    """Run --prune --all mode: clean up all stopped devcontainers globally."""
    runtime = get_container_runtime()
    if runtime is None:
        sys.exit(
            "Error: No container runtime found (docker or podman required)"
        )

    all_containers = list_all_devcontainers()
    stopped_containers = [
        (name, folder, image_id)
        for name, folder, state, image_id in all_containers
        if state != "running"
    ]
    orphan_containers = [
        (name, folder, image_id)
        for name, folder, state, image_id in all_containers
        if state == "running" and not Path(folder).exists()
    ]

    if not stopped_containers and not orphan_containers:
        print("Nothing to prune.")
        return

    if stopped_containers:
        print("Stopped containers:")
        for name, folder, _ in stopped_containers:
            print(f"  {name:<24} {folder}")
        print()

    if orphan_containers:
        print("Orphan containers (workspace dir missing):")
        for name, folder, _ in orphan_containers:
            print(f"  {name:<24} {folder}")
        print()

    # Collect image IDs that might be pruned
    potential_images = {
        c[2] for c in stopped_containers + orphan_containers if c[2]
    }

    if potential_images:
        print("Images that may be pruned (if not used by other containers):")
        for image_id in sorted(potential_images):
            print(f"  {image_id}")
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

    # Stop orphan containers first
    for name, _, _ in orphan_containers:
        cmd = [runtime, "stop", name]
        verbose_cmd(cmd)
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"Stopped: {name}")
        else:
            print(f"Failed to stop: {name}", file=sys.stderr)

    # Remove containers
    for name, _, _ in stopped_containers + orphan_containers:
        if remove_container(name):
            print(f"Removed: {name}")
        else:
            print(f"Failed to remove: {name}", file=sys.stderr)

    # Prune unused images
    if potential_images:
        print("\nPruning images...")
        remaining_containers = list_all_devcontainers()
        in_use_images = {c[3] for c in remaining_containers if c[3]}

        for image_id in potential_images:
            if image_id not in in_use_images:
                if remove_image(image_id):
                    print(f"Removed image: {image_id}")
                else:
                    # Ignore failures (image might be used by non-devcontainer)
                    pass


def run_prune_mode(args: argparse.Namespace) -> None:
    """Run --prune mode: clean up stopped containers and stale worktrees."""
    git_root = find_git_root()

    # Prune all stopped containers if --all flag or not in a git repo
    if args.all or git_root is None:
        run_prune_global_mode()
        return

    runtime = get_container_runtime()
    if runtime is None:
        sys.exit(
            "Error: No container runtime found (docker or podman required)"
        )

    # Find stopped containers
    stopped_containers = find_stopped_containers_for_project(git_root)

    # Find orphan containers (running but workspace dir missing)
    all_project = find_containers_for_project(git_root)
    orphan_containers = [
        (name, folder, image_id)
        for name, folder, state, image_id in all_project
        if state == "running" and not Path(folder).exists()
    ]

    # Find stale worktrees
    stale_worktrees = find_stale_worktrees(git_root)

    if (
        not stopped_containers
        and not orphan_containers
        and not stale_worktrees
    ):
        print("Nothing to prune.")
        return

    # Show what will be pruned
    if stopped_containers:
        print("Stopped containers:")
        for name, folder, _ in stopped_containers:
            print(f"  {name:<24} {folder}")
        print()

    if orphan_containers:
        print("Orphan containers (workspace dir missing):")
        for name, folder, _ in orphan_containers:
            print(f"  {name:<24} {folder}")
        print()

    if stale_worktrees:
        print("Stale worktrees:")
        for wt_path, branch in stale_worktrees:
            print(f"  {wt_path.name:<24} ({branch})")
        print()

    # Collect image IDs that might be pruned
    potential_images = {
        c[2] for c in stopped_containers + orphan_containers if c[2]
    }

    if potential_images:
        print("Images that may be pruned (if not used by other containers):")
        for image_id in sorted(potential_images):
            print(f"  {image_id}")
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

    # Stop orphan containers first
    for name, _, _ in orphan_containers:
        cmd = [runtime, "stop", name]
        verbose_cmd(cmd)
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0:
            print(f"Stopped: {name}")
        else:
            print(f"Failed to stop: {name}", file=sys.stderr)

    # Remove containers
    for name, _, _ in stopped_containers + orphan_containers:
        if remove_container(name):
            print(f"Removed container: {name}")
        else:
            print(f"Failed to remove container: {name}", file=sys.stderr)

    # Remove worktrees
    for wt_path, _ in stale_worktrees:
        if remove_worktree(git_root, wt_path):
            print(f"Removed worktree: {wt_path.name}")
        else:
            print(
                f"Failed to remove worktree: {wt_path.name}", file=sys.stderr
            )

    # Prune unused images
    if potential_images:
        print("\nPruning images...")
        remaining_containers = list_all_devcontainers()
        in_use_images = {c[3] for c in remaining_containers if c[3]}

        for image_id in potential_images:
            if image_id not in in_use_images:
                if remove_image(image_id):
                    print(f"Removed image: {image_id}")
                else:
                    # Ignore failures
                    pass


def _last_attach_mtime(workspace: Path) -> float:
    """Return mtime of .last-attach marker, or 0 if missing."""
    try:
        return (workspace / ".devcontainer" / ".last-attach").stat().st_mtime
    except OSError:
        return 0.0


def _pick_container() -> Path | None:
    """Show fzf picker for all containers (running and stopped)."""
    containers = list_all_devcontainers()
    candidates = [
        (name, folder, state)
        for name, folder, state, image_id in containers
        if Path(folder).exists()
    ]

    if not candidates:
        sys.exit("No containers found.")

    if len(candidates) == 1:
        return Path(candidates[0][1])

    candidates.sort(
        key=lambda item: _last_attach_mtime(Path(item[1])), reverse=True
    )

    labels = []
    for _, folder, state in candidates:
        label = _format_container_display(folder)
        marker = "" if state == "running" else f" [{state}]"
        labels.append(f"{label}{marker:<12} {folder}")

    selected = _fzf_pick("Pick a container:", labels)
    if selected is None:
        return None
    return Path(selected.strip().split()[-1])


def run_attach_mode(args: argparse.Namespace) -> None:
    """Run attach mode: pick a container, start if stopped, and attach."""
    folder = _pick_container()
    if not folder:
        return

    if args.recreate:
        _update_container(folder, force=getattr(args, "force", False))
    elif not is_container_running(folder):
        if not devcontainer_up(folder):
            sys.exit("Error: Failed to start container")

    devcontainer_exec_tmux(folder)


def _update_container(git_root: Path, force: bool = False) -> None:
    """Sync config, rebuild, and restart a container."""
    project_name = git_root.name
    config = load_config(project_dir=git_root)

    _sync_config(project_name, git_root, config, force=force)
    _setup_container_env(git_root, config)

    if not devcontainer_up(git_root, remove_existing=True):
        sys.exit("Error: Failed to rebuild devcontainer")


def run_list_mode(args: argparse.Namespace) -> None:
    """Run --list mode: show containers and worktrees for current project."""
    if args.all:
        run_list_global_mode()
        return

    git_root = pick_project()
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
            print(
                f"  {status_marker} {ws_path.name:<20} {status:<10} ({ws_type})"
            )
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


def _is_image_stale(
    runtime: str, container_name: str, image: str
) -> bool | None:
    """Check if a container is running a stale image. Returns None if unknown."""
    containers = list_all_devcontainers()
    container_img = next(
        (img for name, _f, _s, img in containers if name == container_name),
        None,
    )
    current_img = subprocess.run(
        [runtime, "image", "inspect", "--format", "{{.Id}}", image],
        capture_output=True,
        text=True,
    )
    if not container_img or current_img.returncode != 0:
        return None
    current_id = current_img.stdout.strip()
    return not (
        container_img.startswith(current_id)
        or current_id.startswith(container_img)
    )


def run_status_mode(args: argparse.Namespace) -> None:
    """Project dashboard: containers, worktrees, ports, disk usage."""
    git_root = pick_project()
    project_name = git_root.name
    runtime = get_container_runtime()

    print(f"Project: {project_name}")
    print(f"Root:    {git_root}")
    print()

    # Containers with uptime
    config = load_config()
    image = config.get("base_image", constants.DEFAULT_CONFIG["base_image"])
    workspaces = find_project_workspaces(git_root)
    print("Containers:")
    for ws_path, ws_type in workspaces:
        if not (ws_path / ".devcontainer").exists():
            continue
        container_name = get_container_for_workspace(ws_path)
        if container_name and runtime:
            uptime = subprocess.run(
                [
                    runtime,
                    "inspect",
                    "--format",
                    "{{.State.StartedAt}}",
                    container_name,
                ],
                capture_output=True,
                text=True,
            )
            started = (
                uptime.stdout.strip()[:19].replace("T", " ")
                if uptime.returncode == 0
                else "?"
            )
            port = read_port_from_devcontainer(ws_path)
            port_str = str(port) if port else "-"
            stale = _is_image_stale(runtime, container_name, image)
            tag = f"{ws_type}, stale image" if stale else ws_type
            print(
                f"  * {ws_path.name:<20} port {port_str:<5}  started {started}  ({tag})"
            )
        else:
            port = read_port_from_devcontainer(ws_path)
            port_str = str(port) if port else "-"
            print(
                f"    {ws_path.name:<20} port {port_str:<5}  stopped  ({ws_type})"
            )

    print()

    # Worktrees with branch age
    worktrees = list_worktrees(git_root)
    if len(worktrees) > 1:
        print("Worktrees:")
        for wt_path, _commit, branch in worktrees:
            if wt_path == git_root:
                continue
            if not wt_path.exists():
                print(f"    {wt_path.name:<20} {branch:<20} (prunable)")
                continue
            age = subprocess.run(
                ["git", "-C", str(wt_path), "log", "-1", "--format=%cr"],
                capture_output=True,
                text=True,
            )
            age_str = age.stdout.strip() if age.returncode == 0 else "?"
            print(f"    {wt_path.name:<20} {branch:<20} {age_str}")
    print()

    # Disk usage
    print("Disk:")
    devcontainer_size = _dir_size(git_root / ".devcontainer")
    git_size = _dir_size(git_root / ".git")
    print(f"    .devcontainer  {_fmt_size(devcontainer_size)}")
    print(f"    .git           {_fmt_size(git_size)}")


def _dir_size(path: Path) -> int:
    """Total size of a directory in bytes."""
    if not path.exists():
        return 0
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def _fmt_size(nbytes: int) -> str:
    """Format bytes as human-readable."""
    size = float(nbytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return (
                f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
            )
        size /= 1024
    return f"{size:.1f} TB"


def run_doctor_mode(args: argparse.Namespace) -> None:
    """Pre-flight check: runtime, image, ports, tools, API keys."""
    ok_count = 0
    fail_count = 0

    def check(label: str, passed: bool, detail: str = "") -> None:
        nonlocal ok_count, fail_count
        icon = "ok" if passed else "FAIL"
        suffix = f"  ({detail})" if detail else ""
        print(f"  [{icon:>4}] {label}{suffix}")
        if passed:
            ok_count += 1
        else:
            fail_count += 1

    config = load_config()

    # Container runtime
    runtime = get_container_runtime()
    check("Container runtime", runtime is not None, runtime or "not found")

    # Image exists
    image = config.get("base_image", constants.DEFAULT_CONFIG["base_image"])
    if runtime:
        result = subprocess.run(
            [runtime, "image", "exists", image],
            capture_output=True,
        )
        check("Container image", result.returncode == 0, image)
    else:
        check("Container image", False, "no runtime")

    # Project-specific checks (pick project, or skip if none available)
    try:
        git_root = pick_project()
    except SystemExit:
        git_root = None
    if git_root:
        # Container running?
        container_name = get_container_for_workspace(git_root)
        running = container_name is not None
        check("Container running", running, container_name or "stopped")

        # Image up to date?
        if running and runtime:
            stale = _is_image_stale(runtime, container_name, image)
            if stale is not None:
                check(
                    "Image up to date",
                    not stale,
                    "rebuild needed" if stale else "current",
                )

        # Port
        port = read_port_from_devcontainer(git_root)
        if port:
            avail = is_port_available(port)
            if avail:
                check("Port", True, f"{port}, free")
            elif running:
                check("Port", True, f"{port}, in use by this project")
            else:
                check("Port", False, f"{port}, in use by something else")

    # API keys (check pass + env, same as runtime)
    secrets = get_secrets(config)
    for key in ["ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY"]:
        val = secrets.get(key, "")
        source = (
            "pass"
            if not os.environ.get(key) and val
            else "env"
            if val
            else "missing"
        )
        check(key, bool(val), source)

    # gh auth
    gh_result = subprocess.run(
        ["gh", "auth", "status"],
        capture_output=True,
        text=True,
    )
    check("GitHub CLI auth", gh_result.returncode == 0)

    print()
    print(f"{ok_count} passed, {fail_count} failed")
    if fail_count:
        sys.exit(1)


def _copy_url_to_clipboard(workspace_dir: Path) -> None:
    """Copy the project's dev server URL to the clipboard via OSC 52."""
    port = read_port_from_devcontainer(workspace_dir)
    if port is None:
        return
    hostname = detect_hostname()
    url = f"http://{hostname}:{port}"
    clipboard_copy(url)


def run_up_mode(args: argparse.Namespace) -> None:
    """Run up mode: start devcontainer in current git project."""
    git_root = find_git_root()

    if git_root is None:
        sys.exit(
            "Error: Not in a git repository. Use --init to initialize here."
        )

    os.chdir(git_root)
    project_name = git_root.name

    # Load config
    config = load_config()

    # Sync or scaffold .devcontainer
    if args.recreate:
        _sync_config(
            project_name,
            git_root,
            config,
            force=getattr(args, "force", False),
        )
    else:
        scaffold_devcontainer(project_name, config=config)

    # Add user-specified mounts to devcontainer.json
    if args.mount:
        parsed_mounts = [parse_mount(m, project_name) for m in args.mount]
        devcontainer_json = git_root / ".devcontainer" / "devcontainer.json"
        add_user_mounts(devcontainer_json, parsed_mounts)

    # Copy user-specified files
    if args.copy:
        parsed_copies = [parse_copy(c, project_name) for c in args.copy]
        copy_user_files(parsed_copies, git_root)

    _setup_container_env(git_root, config)

    # Write prompt file before starting container so entrypoint picks it up
    if args.prompt:
        write_prompt_file(git_root, args.agent, args.prompt)

    already_running = is_container_running(git_root)
    if args.recreate or not already_running:
        if not devcontainer_up(git_root, remove_existing=args.recreate):
            sys.exit("Error: Failed to start devcontainer")
    elif already_running:
        print(
            "Container already running, reattaching. Use --recreate to rebuild."
        )

    _copy_url_to_clipboard(git_root)

    if args.prompt:
        print(f"Started {args.agent} in: {project_name}")
        return

    if args.detach:
        print(f"Container started: {project_name}")
        return

    # Direct exec modes (no tmux)
    if args.shell:
        devcontainer_exec_command(git_root, "zsh", interactive=True)
        return

    if args.run:
        devcontainer_exec_command(git_root, args.run)
        return

    # Attach to tmux
    devcontainer_exec_tmux(git_root)


def run_tree_mode(args: argparse.Namespace) -> None:
    """Run --tree mode: create worktree and start devcontainer."""
    git_root = validate_tree_mode()

    # Validate --from branch if specified
    if args.from_branch and not branch_exists(git_root, args.from_branch):
        sys.exit(f"Error: Branch does not exist: {args.from_branch}")

    # Generate name if not provided
    worktree_name = args.name if args.name else generate_random_name()

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

    if args.recreate:
        _sync_config(
            worktree_name,
            worktree_path,
            config,
            force=getattr(args, "force", False),
        )

    # Add user-specified mounts to devcontainer.json
    if args.mount:
        parsed_mounts = [parse_mount(m, worktree_name) for m in args.mount]
        devcontainer_json = (
            worktree_path / ".devcontainer" / "devcontainer.json"
        )
        add_user_mounts(devcontainer_json, parsed_mounts)

    # Copy user-specified files
    if args.copy:
        parsed_copies = [parse_copy(c, worktree_name) for c in args.copy]
        copy_user_files(parsed_copies, worktree_path)

    _setup_container_env(worktree_path, config)

    # Write prompt file before starting container so entrypoint picks it up
    if args.prompt:
        write_prompt_file(worktree_path, args.agent, args.prompt)

    if args.recreate or not is_container_running(worktree_path):
        if not devcontainer_up(worktree_path, remove_existing=args.recreate):
            sys.exit("Error: Failed to start devcontainer")

    if args.prompt:
        print(f"Started {args.agent} in: {worktree_path.name}")
        return

    if args.detach:
        print(f"Container started: {worktree_path.name}")
        return

    # Direct exec modes (no tmux)
    if args.shell:
        devcontainer_exec_command(worktree_path, "zsh", interactive=True)
        return

    if args.run:
        devcontainer_exec_command(worktree_path, args.run)
        return

    # Attach to tmux
    devcontainer_exec_tmux(worktree_path)


def _setup_test_hooks(project_path: Path) -> None:
    install_cmd = get_precommit_install_command()
    devcontainer_exec_command(project_path, " ".join(install_cmd))
    devcontainer_exec_command(
        project_path, "git config --local hooks.test-on-commit true"
    )
    devcontainer_exec_command(
        project_path, "git config --local hooks.test-on-push false"
    )


def run_create_mode(args: argparse.Namespace) -> None:
    """Run --create mode: create new project with devcontainer."""
    validate_create_mode(args.name)

    project_name = args.name
    project_path = Path.cwd() / project_name

    # Load config
    config = load_config()

    # Get flavors from --flavor or interactive selector
    if args.flavor:
        flavors = args.flavor
    else:
        flavors = select_flavors_interactive()
        if not flavors:
            print("No flavors selected, aborting.", file=sys.stderr)
            sys.exit(1)

    primary_flavor = flavors[0] if flavors else "other"

    # Create project directory
    project_path.mkdir()

    # Copy template files (AGENTS.md, CLAUDE.md, .gitignore, .editorconfig, etc.)
    copy_template_files(project_path)

    # Generate MOTD for the project
    motd_content = get_motd_content(primary_flavor, project_name)
    (project_path / "MOTD").write_text(motd_content)
    verbose_print("Generated MOTD")

    # Generate justfile + justfile.common for the project. The user
    # edits `justfile`; tool-owned recipes live in `justfile.common`
    # and are retrofitted on `jolo up --recreate --force`.
    justfile_content = get_justfile_content(primary_flavor, project_name)
    (project_path / "justfile").write_text(justfile_content)
    common_content = get_justfile_common_content(project_name)
    (project_path / "justfile.common").write_text(common_content)
    verbose_print("Generated justfile + justfile.common")

    # Fill perf-rig.toml placeholders with the project's identity so the
    # user isn't staring at REPLACE-ME on first open. target.url stays
    # as ${DEV_HOST}:${PORT} — resolved by envsubst at `just perf`
    # time, never written to disk.
    #
    # json.dumps()[1:-1] escapes quotes/backslashes/control chars for TOML
    # basic strings (TOML's escape rules are a subset of JSON's). Keeps
    # weird project names from producing invalid TOML.
    perf_rig_path = project_path / "perf-rig.toml"
    if perf_rig_path.exists():
        language = constants.FLAVOR_LANGUAGE.get(
            primary_flavor, primary_flavor
        )
        content = perf_rig_path.read_text()
        content = content.replace(
            "{{PROJECT_NAME}}", json.dumps(project_name)[1:-1]
        )
        content = content.replace(
            "{{PROJECT_LANGUAGE}}", json.dumps(language)[1:-1]
        )
        perf_rig_path.write_text(content)
        verbose_print("Filled perf-rig.toml")

    # Generate and write .pre-commit-config.yaml based on selected flavors
    precommit_content = generate_precommit_config(flavors)
    (project_path / ".pre-commit-config.yaml").write_text(precommit_content)
    verbose_print(
        f"Generated .pre-commit-config.yaml for flavors: {', '.join(flavors)}"
    )

    # Write test framework config for primary flavor
    test_config = get_test_framework_config(primary_flavor)
    module_name = to_snake_case(project_name)
    pascal_name = to_pascal_case(project_name)

    def replace_placeholders(text: str) -> str:
        return (
            text.replace("{{PROJECT_NAME}}", project_name)
            .replace("{{PROJECT_NAME_UNDERSCORE}}", module_name)
            .replace("{{MODULE_NAME}}", pascal_name)
        )

    if test_config.get("config_file"):
        config_file = project_path / test_config["config_file"]
        content = replace_placeholders(test_config["config_content"])
        if config_file.exists():
            # Append to existing file
            existing = config_file.read_text()
            config_file.write_text(existing + "\n" + content)
        else:
            config_file.write_text(content)
        verbose_print(
            f"Wrote test framework config: {test_config['config_file']}"
        )

    # Write main module file (Python src layout)
    if test_config.get("main_file") and test_config.get("main_content"):
        main_path = project_path / replace_placeholders(
            test_config["main_file"]
        )
        main_path.parent.mkdir(parents=True, exist_ok=True)
        main_path.write_text(replace_placeholders(test_config["main_content"]))
        verbose_print(
            f"Wrote main module: {main_path.relative_to(project_path)}"
        )

    # Write __init__.py for Python packages
    if test_config.get("init_file"):
        init_path = project_path / replace_placeholders(
            test_config["init_file"]
        )
        init_path.parent.mkdir(parents=True, exist_ok=True)
        init_path.write_text("")
        verbose_print(
            f"Wrote package init: {init_path.relative_to(project_path)}"
        )

    # Write tests/__init__.py for Python test packages
    if test_config.get("tests_init_file"):
        tests_init_path = project_path / test_config["tests_init_file"]
        tests_init_path.parent.mkdir(parents=True, exist_ok=True)
        tests_init_path.write_text("")
        verbose_print(
            f"Wrote tests init: {tests_init_path.relative_to(project_path)}"
        )

    # Write example test file for primary language
    if test_config.get("example_test_file") and test_config.get(
        "example_test_content"
    ):
        example_test_path = project_path / test_config["example_test_file"]
        example_test_path.parent.mkdir(parents=True, exist_ok=True)
        example_test_path.write_text(
            replace_placeholders(test_config["example_test_content"])
        )
        verbose_print(
            f"Wrote example test: {test_config['example_test_file']}"
        )

    # Write additional scaffold source files
    for rel_path, content in get_scaffold_files(primary_flavor):
        file_path = project_path / replace_placeholders(rel_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(replace_placeholders(content))
        verbose_print(f"Wrote scaffold file: {rel_path}")

    # Write type checker config for primary flavor
    type_config = get_type_checker_config(primary_flavor)
    if type_config:
        config_file = project_path / type_config["config_file"]
        if config_file.exists():
            # Append to existing file (e.g., pyproject.toml)
            existing = config_file.read_text()
            config_file.write_text(
                existing + "\n" + type_config["config_content"]
            )
        else:
            config_file.write_text(type_config["config_content"])
        verbose_print(
            f"Wrote type checker config: {type_config['config_file']}"
        )

    # Initialize git repo
    cmd = ["git", "init"]
    verbose_cmd(cmd)
    result = subprocess.run(cmd, cwd=project_path)
    if result.returncode != 0:
        sys.exit("Error: Failed to initialize git repository")

    # Scaffold .devcontainer
    scaffold_devcontainer(
        project_name,
        project_path,
        config=config,
        has_web="web" in primary_flavor,
    )

    # Format code before initial commit to avoid "format on save" noise
    lang = constants.FLAVOR_LANGUAGE.get(primary_flavor, primary_flavor)
    try:
        if lang == "typescript":
            verbose_print("Formatting TypeScript files with biome...")
            subprocess.run(
                [
                    "biome",
                    "check",
                    "--write",
                    "--no-errors-on-unmatched",
                    "--files-ignore-unknown=true",
                    ".",
                ],
                cwd=project_path,
                capture_output=not constants.VERBOSE,
            )
        elif lang == "go":
            verbose_print("Formatting Go files with gofmt...")
            subprocess.run(
                ["gofmt", "-w", "."],
                cwd=project_path,
                capture_output=not constants.VERBOSE,
            )
        elif lang == "python":
            verbose_print("Formatting Python files with ruff...")
            subprocess.run(
                ["ruff", "format", "--isolated", "."],
                cwd=project_path,
                capture_output=not constants.VERBOSE,
            )
            subprocess.run(
                ["ruff", "check", "--fix", "--isolated", "."],
                cwd=project_path,
                capture_output=not constants.VERBOSE,
            )
        elif lang == "rust":
            verbose_print("Formatting Rust files with rustfmt...")
            for rs_file in project_path.rglob("*.rs"):
                subprocess.run(
                    ["rustfmt", str(rs_file)],
                    capture_output=not constants.VERBOSE,
                )
    except FileNotFoundError:
        pass

    # Initial commit with all generated files
    cmd = ["git", "add", "."]
    verbose_cmd(cmd)
    subprocess.run(cmd, cwd=project_path)

    cmd = ["git", "commit", "-m", "Initial commit with devcontainer setup"]
    verbose_cmd(cmd)
    subprocess.run(cmd, cwd=project_path)

    print(f"Created project: {project_path}")

    # Change to project directory for devcontainer commands
    os.chdir(project_path)

    # Add user-specified mounts to devcontainer.json
    if args.mount:
        parsed_mounts = [parse_mount(m, project_name) for m in args.mount]
        devcontainer_json = (
            project_path / ".devcontainer" / "devcontainer.json"
        )
        add_user_mounts(devcontainer_json, parsed_mounts)

    # Copy user-specified files
    if args.copy:
        parsed_copies = [parse_copy(c, project_name) for c in args.copy]
        copy_user_files(parsed_copies, project_path)

    _setup_container_env(project_path, config)

    # Write prompt file before starting container so entrypoint picks it up
    if args.prompt:
        write_prompt_file(project_path, args.agent, args.prompt)

    # Start devcontainer (always remove existing for fresh project)
    if not devcontainer_up(project_path, remove_existing=True):
        sys.exit("Error: Failed to start devcontainer")

    _setup_test_hooks(project_path)

    # Run project init commands for primary flavor inside the container
    init_commands = get_project_init_commands(primary_flavor, project_name)
    if init_commands:
        combined_cmd = " && ".join([" ".join(c) for c in init_commands])
        verbose_print(f"Running in container: {combined_cmd}")
        devcontainer_exec_command(project_path, combined_cmd)
        devcontainer_exec_command(
            project_path,
            'git add . && git diff --cached --quiet || git commit -m "Add dependencies"',
        )

    _copy_url_to_clipboard(project_path)

    if args.prompt:
        print(f"Started {args.agent} in: {project_name}")
        return

    if args.detach:
        print(f"Container started: {project_name}")
        return

    # Direct exec modes (no tmux)
    if args.shell:
        devcontainer_exec_command(project_path, "zsh", interactive=True)
        return

    if args.run:
        devcontainer_exec_command(project_path, args.run)
        return

    # Attach to tmux
    devcontainer_exec_tmux(project_path)


def run_clone_mode(args: argparse.Namespace) -> None:
    """Run clone mode: clone repo and start devcontainer."""
    name = args.name or infer_repo_name(args.url)
    target = Path.cwd() / name

    if target.exists():
        sys.exit(f"Error: Target directory exists: {target}")

    target.parent.mkdir(parents=True, exist_ok=True)

    cmd = ["git", "clone", args.url, str(target)]
    verbose_cmd(cmd)
    result = subprocess.run(cmd)
    if result.returncode != 0:
        sys.exit("Error: git clone failed")

    os.chdir(target)

    # Auto-detect flavors if no devcontainer config exists
    if not (target / ".devcontainer").exists():
        detected = detect_flavors(target)
        if detected:
            print(f"Detected flavors: {', '.join(detected)}")
            args.flavor = detected

    run_up_mode(args)


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

    if args.recreate:
        _sync_config(
            project_name,
            project_path,
            config,
            force=getattr(args, "force", False),
        )
    else:
        scaffold_devcontainer(project_name, project_path, config=config)

    ensure_test_gate_script(project_path)
    precommit_path = project_path / ".pre-commit-config.yaml"
    if not precommit_path.exists():
        precommit_content = generate_precommit_config([])
        precommit_path.write_text(precommit_content)
        verbose_print("Generated .pre-commit-config.yaml for init")

    # Initial commit with all generated files
    cmd = ["git", "add", "."]
    verbose_cmd(cmd)
    subprocess.run(cmd, cwd=project_path)

    cmd = ["git", "commit", "-m", "Initial commit with devcontainer setup"]
    verbose_cmd(cmd)
    subprocess.run(cmd, cwd=project_path)

    print(f"Initialized: {project_path}")

    # Add user-specified mounts to devcontainer.json
    if args.mount:
        parsed_mounts = [parse_mount(m, project_name) for m in args.mount]
        devcontainer_json = (
            project_path / ".devcontainer" / "devcontainer.json"
        )
        add_user_mounts(devcontainer_json, parsed_mounts)

    # Copy user-specified files
    if args.copy:
        parsed_copies = [parse_copy(c, project_name) for c in args.copy]
        copy_user_files(parsed_copies, project_path)

    _setup_container_env(project_path, config)

    # Write prompt file before starting container so entrypoint picks it up
    if args.prompt:
        write_prompt_file(project_path, args.agent, args.prompt)

    # Start devcontainer (always remove existing for fresh project)
    if not devcontainer_up(project_path, remove_existing=True):
        sys.exit("Error: Failed to start devcontainer")

    _setup_test_hooks(project_path)

    if args.prompt:
        print(f"Started {args.agent} in: {project_name}")
        return

    if args.detach:
        print(f"Container started: {project_name}")
        return

    # Direct exec modes (no tmux)
    if args.shell:
        devcontainer_exec_command(project_path, "zsh", interactive=True)
        return

    if args.run:
        devcontainer_exec_command(project_path, args.run)
        return

    # Attach to tmux
    devcontainer_exec_tmux(project_path)


def run_spawn_mode(args: argparse.Namespace) -> None:
    """Run --spawn mode: create N worktrees with containers and agents."""
    git_root = validate_tree_mode()

    n = args.count
    if n < 1:
        sys.exit("Error: spawn requires a positive integer")

    # Load config
    config = load_config()
    base_port = config.get("base_port", 4000)

    # Generate worktree names (number prefix for sorting + uniqueness)
    worktree_names = []
    used_names = set()
    for i in range(n):
        idx = i + 1
        if args.prefix:
            name = f"{idx}-{args.prefix}"
        else:
            # Generate unique random name with number prefix
            for _ in range(100):  # Max attempts
                random_part = generate_random_name()
                if random_part not in used_names:
                    break
            else:
                random_part = f"spawn-{idx}"
            used_names.add(random_part)
            name = f"{idx}-{random_part}"
        worktree_names.append(name)

    print(f"Spawning {n} worktrees: {', '.join(worktree_names)}")

    # Set up secrets once (get_secrets shells out to pass/gh)
    secrets = get_secrets(config)
    os.environ.update(secrets)

    # Create worktrees and scaffold devcontainers
    worktree_paths = []
    for i, name in enumerate(worktree_names):
        worktree_path = get_worktree_path(str(git_root), name)
        port = base_port + i

        # Create or get existing worktree
        worktree_path = get_or_create_worktree(
            git_root,
            name,
            worktree_path,
            config=config,
            from_branch=args.from_branch,
        )

        if args.recreate:
            _sync_config(
                name,
                worktree_path,
                config,
                port=port,
                force=getattr(args, "force", False),
            )

        devcontainer_json = (
            worktree_path / ".devcontainer" / "devcontainer.json"
        )
        if devcontainer_json.exists() and not args.recreate:
            content = json.loads(devcontainer_json.read_text())
            if "containerEnv" not in content:
                content["containerEnv"] = {}
            content["containerEnv"]["PORT"] = str(port)
            devcontainer_json.write_text(json.dumps(content, indent=4) + "\n")

        # Add user-specified mounts
        if args.mount:
            parsed_mounts = [parse_mount(m, name) for m in args.mount]
            add_user_mounts(devcontainer_json, parsed_mounts)

        # Copy user-specified files
        if args.copy:
            parsed_copies = [parse_copy(c, name) for c in args.copy]
            copy_user_files(parsed_copies, worktree_path)

        _setup_container_env(worktree_path, config)

        (worktree_path / ".devcontainer" / ".zsh-state").mkdir(exist_ok=True)

        worktree_paths.append(worktree_path)

    # Start containers in parallel
    print(f"Starting {n} containers...")
    processes = []
    for i, path in enumerate(worktree_paths):
        cmd = ["devcontainer", "up", "--workspace-folder", str(path)]
        if args.recreate:
            cmd.append("--remove-existing-container")
        verbose_cmd(cmd)
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        processes.append((path, proc))
        print(f"  [{i + 1}/{n}] Launched: {path.name}")

    # Wait for all containers to start
    print(f"Waiting for {n} containers to be ready...")
    failed = []
    for path, proc in processes:
        stdout, stderr = proc.communicate()
        if proc.returncode != 0:
            failed.append(path.name)
            print(f"  Failed: {path.name}", file=sys.stderr)
            if stderr:
                # Show last few lines of error
                err_lines = stderr.decode().strip().split("\n")
                for line in err_lines[-5:]:
                    print(f"    {line}", file=sys.stderr)
        else:
            print(f"  Ready: {path.name}")

    if failed:
        print(
            f"Warning: {len(failed)} container(s) failed to start: {', '.join(failed)}"
        )

    # If no prompt, just report status
    if not args.prompt:
        print(f"\n{len(worktree_paths) - len(failed)} containers running.")
        print("Use --prompt to start agents, or attach manually.")
        return

    # Launch agents in tmux multi-pane
    spawn_tmux_multipane(
        worktree_paths=[p for p in worktree_paths if p.name not in failed],
        worktree_names=[n for n in worktree_names if n not in failed],
        prompt=args.prompt,
        config=config,
        agent_override=args.agent if args.agent != "claude" else None,
    )


def spawn_tmux_multipane(
    worktree_paths: list[Path],
    worktree_names: list[str],
    prompt: str,
    config: dict,
    agent_override: str | None = None,
) -> None:
    """Create tmux session with one pane per agent.

    Args:
        worktree_paths: List of worktree paths
        worktree_names: List of worktree names
        prompt: The prompt to give each agent
        config: Configuration dict
        agent_override: If set, use this agent for all; otherwise round-robin
    """
    session_name = "spawn"
    n = len(worktree_paths)

    if n == 0:
        print("No containers to attach to.")
        return

    # Kill existing session if present
    subprocess.run(
        ["tmux", "kill-session", "-t", session_name],
        capture_output=True,
    )

    # Create new session with first pane
    first_path = worktree_paths[0]
    first_agent_cmd = get_agent_command(config, agent_override, index=0)
    quoted_prompt = shlex.quote(prompt)

    # Build exec command using sh -c to properly handle agent flags
    def build_exec_cmd(path: Path, agent_cmd: str) -> str:
        inner_cmd = f"notify stamp && {agent_cmd} {quoted_prompt}"
        return f"devcontainer exec --workspace-folder {path} sh -c {shlex.quote(inner_cmd)}"

    # Create new session with first window
    first_exec_cmd = build_exec_cmd(first_path, first_agent_cmd)
    subprocess.run(
        [
            "tmux",
            "new-session",
            "-d",
            "-s",
            session_name,
            "-n",
            worktree_names[0],
        ]
    )
    subprocess.run(
        [
            "tmux",
            "send-keys",
            "-t",
            f"{session_name}:{worktree_names[0]}",
            first_exec_cmd,
            "Enter",
        ]
    )

    # Create additional windows (not panes - full screen each)
    for i in range(1, n):
        path = worktree_paths[i]
        name = worktree_names[i]
        agent_cmd = get_agent_command(config, agent_override, index=i)

        exec_cmd = build_exec_cmd(path, agent_cmd)

        # Create new window (full screen) and send command
        subprocess.run(["tmux", "new-window", "-t", session_name, "-n", name])
        subprocess.run(
            [
                "tmux",
                "send-keys",
                "-t",
                f"{session_name}:{name}",
                exec_cmd,
                "Enter",
            ]
        )

    print(f"\nStarted {n} agents in tmux session '{session_name}'")
    print(
        f"Agents: {', '.join(get_agent_name(config, agent_override, i) for i in range(n))}"
    )
    print("Attaching to tmux session...")

    # Attach to session
    subprocess.run(["tmux", "attach", "-t", session_name])


def ensure_research_repo(config: dict) -> Path:
    """Ensure the research repo exists, creating it on first use."""
    research_home = Path(
        config.get("research_home", "~/jolo/research")
    ).expanduser()

    if (research_home / ".git").exists():
        # Verify scaffold is complete (handles partial init failures)
        if (research_home / ".devcontainer" / "devcontainer.json").exists():
            return research_home
        # Incomplete — wipe and re-create
        shutil.rmtree(research_home)

    research_home.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init"], cwd=research_home, check=True)
    scaffold_devcontainer("research", research_home, config=config)

    # Copy just the research skill
    templates_dir = Path(__file__).resolve().parent.parent / "templates"
    skill_src = templates_dir / "skills" / "j-research"
    if skill_src.exists():
        skill_dst = research_home / ".jolo" / "skills" / "j-research"
        skill_dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(skill_src, skill_dst)

    subprocess.run(["git", "add", "."], cwd=research_home, check=True)
    subprocess.run(
        ["git", "commit", "-m", "Initial research repo"],
        cwd=research_home,
        check=True,
    )

    return research_home


def _resolve_research_prompt(args: argparse.Namespace) -> str:
    """Resolve the research prompt from args, file, or $EDITOR."""
    import tempfile

    if args.file:
        path = Path(args.file).expanduser()
        if not path.exists():
            sys.exit(f"Error: File not found: {args.file}")
        return path.read_text().strip()

    if args.prompt:
        return args.prompt

    # No prompt and no file — open $VISUAL / $EDITOR
    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR") or "vi"
    with tempfile.NamedTemporaryFile(
        suffix=".txt", mode="w", delete=False
    ) as f:
        f.write(
            "# Enter your research question below.\n"
            "# Lines starting with # are ignored.\n"
        )
        tmppath = f.name

    try:
        # Shell=True so EDITOR="emacsclient -w" works
        result = subprocess.run(f"{editor} {shlex.quote(tmppath)}", shell=True)
        if result.returncode != 0:
            sys.exit("Editor exited with error")
        text = Path(tmppath).read_text()
    finally:
        Path(tmppath).unlink(missing_ok=True)

    lines = [line for line in text.splitlines() if not line.startswith("#")]
    prompt = "\n".join(lines).strip()
    if not prompt:
        sys.exit("Error: Empty prompt")
    return prompt


def _build_research_agent_cmd(
    config: dict, agent_name: str, agent_prompt: str, logfile: str
) -> str:
    """Build a nohup command string to run an agent in the background."""
    agent_cmd = get_agent_command(config, agent_name)
    quoted_prompt = shlex.quote(agent_prompt)
    if agent_name == "codex":
        return f"nohup {agent_cmd} exec {quoted_prompt} > {logfile} 2>&1 &"
    return f"nohup {agent_cmd} -p {quoted_prompt} > {logfile} 2>&1 &"


def run_research_mode(args: argparse.Namespace) -> None:
    """Run research in a persistent container at ~/jolo/research/."""
    from datetime import datetime, timezone

    prompt = _resolve_research_prompt(args)

    config = load_config()
    research_home = ensure_research_repo(config)

    slug = slugify_prompt(prompt)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d-%H%M")

    _setup_container_env(research_home, config)
    if not is_container_running(research_home):
        if not devcontainer_up(research_home):
            sys.exit("Error: Failed to start research container")

    if getattr(args, "deep", False):
        _run_research_deep(config, research_home, prompt, slug, ts)
        return

    # Pick agent
    agents = config.get("agents", ["claude"])
    if args.agent:
        agent_name = args.agent
    elif agents:
        agent_name = agents[random.randint(0, len(agents) - 1)]
    else:
        agent_name = "claude"

    filename = f"{ts}-{slug}.org"
    agent_prompt = (
        f"/j-research Write findings to {filename}. Question: {prompt}"
    )
    logfile = f"/tmp/research-{slug}.log"
    exec_cmd = _build_research_agent_cmd(
        config, agent_name, agent_prompt, logfile
    )
    devcontainer_exec_command(research_home, exec_cmd)

    print(f"Research started: {agent_name} → {filename}")
    print(f"Log: podman exec research cat {logfile}")


def _run_research_deep(
    config: dict, research_home: Path, prompt: str, slug: str, ts: str
) -> None:
    """Run two agents in parallel, then synthesize with a third.

    Launches claude and codex to research the same question independently,
    waits for both, then runs gemini to compile findings into a synthesis.
    """
    file_a = f"{ts}-{slug}-claude.org"
    file_b = f"{ts}-{slug}-codex.org"
    file_synth = f"{ts}-{slug}-synthesis.org"
    log_a = f"/tmp/research-{slug}-claude.log"
    log_b = f"/tmp/research-{slug}-codex.log"
    log_synth = f"/tmp/research-{slug}-synthesis.log"

    prompt_a = f"/j-research Write findings to {file_a}. Question: {prompt}"
    prompt_b = f"/j-research Write findings to {file_b}. Question: {prompt}"

    cmd_a = get_agent_command(config, "claude")
    cmd_b = get_agent_command(config, "codex")
    cmd_synth = get_agent_command(config, "gemini")

    quoted_a = shlex.quote(prompt_a)
    quoted_b = shlex.quote(prompt_b)
    synth_prompt = (
        f"Read {file_a} and {file_b}, then write a synthesis combining "
        f"the best findings from both into {file_synth}. "
        f"Original question: {prompt}"
    )
    quoted_synth = shlex.quote(synth_prompt)

    # Single shell script: background both researchers, wait, then synthesize
    script = (
        f"{cmd_a} -p {quoted_a} > {log_a} 2>&1 &\n"
        f"PID_A=$!\n"
        f"{cmd_b} exec {quoted_b} > {log_b} 2>&1 &\n"
        f"PID_B=$!\n"
        f"wait $PID_A $PID_B\n"
        f"{cmd_synth} -p {quoted_synth} > {log_synth} 2>&1"
    )

    exec_cmd = f"nohup sh -c {shlex.quote(script)} > /dev/null 2>&1 &"
    devcontainer_exec_command(research_home, exec_cmd)

    print("Deep research started: claude + codex → gemini synthesis")
    print(f"  Claude → {file_a}")
    print(f"  Codex  → {file_b}")
    print(f"  Synthesis → {file_synth}")


def _find_deletable_worktrees(git_root: Path) -> list[tuple[Path, str, str]]:
    """Find worktrees that can be deleted for a given git root.

    Returns list of (wt_path, commit, branch) excluding the main repo.
    """
    worktrees = list_worktrees(git_root)
    return [(p, c, b) for p, c, b in worktrees if p != git_root]


def _build_delete_picker_items() -> list[dict]:
    """Build a list of deletable items (worktrees and projects) globally.

    Returns list of dicts with keys:
        - path: Path to the workspace
        - label: Display label for picker
        - type: "worktree" or "project"
        - git_root: Path to the main git repo
        - branch: branch name (worktrees only)
    """
    containers = list_all_devcontainers()
    seen_roots: set[Path] = set()
    roots: list[Path] = []

    for _, folder, _, _ in containers:
        folder_path = Path(folder)
        if not folder_path.exists():
            continue
        root = find_git_root(folder_path)
        if root is None or root in seen_roots:
            continue
        seen_roots.add(root)
        roots.append(root)

    roots.sort(key=_last_attach_mtime, reverse=True)

    items: list[dict] = []
    for root in roots:
        label = _format_container_display(str(root))
        items.append(
            {
                "path": root,
                "label": f"{label:<24} (project)",
                "type": "project",
                "git_root": root,
                "branch": None,
            }
        )

        for wt_path, commit, branch in _find_deletable_worktrees(root):
            wt_label = _format_container_display(str(wt_path))
            items.append(
                {
                    "path": wt_path,
                    "label": f"  {wt_label:<22} [{commit[:7]}]",
                    "type": "worktree",
                    "git_root": root,
                    "branch": branch,
                }
            )

    return items


def _delete_worktree(wt_path: Path, git_root: Path, yes: bool = False) -> None:
    """Delete a single worktree: stop container, remove worktree."""
    stop_container(wt_path)
    if remove_worktree(git_root, wt_path):
        print(f"Deleted worktree: {wt_path.name}")
    else:
        print(f"Failed to delete worktree: {wt_path.name}", file=sys.stderr)


def _prompt_purge(git_root: Path) -> None:
    """Ask whether to remove project files from disk, then do it."""
    try:
        response = input("Also remove files from disk? [y/N] ")
    except (EOFError, KeyboardInterrupt):
        print()
        return
    if response.lower() != "y":
        return
    _purge_dirs(git_root)


def _purge_dirs(git_root: Path) -> None:
    """Remove project and worktree directories from disk."""
    dirs_to_remove = [git_root]
    worktrees_dir = git_root.parent / f"{git_root.name}-worktrees"
    if worktrees_dir.exists():
        dirs_to_remove.append(worktrees_dir)

    for d in dirs_to_remove:
        try:
            shutil.rmtree(d)
            print(f"Removed directory: {d}")
        except Exception as e:
            print(f"Failed to remove {d}: {e}", file=sys.stderr)


def _delete_project(
    git_root: Path, purge: bool = False, yes: bool = False
) -> None:
    """Delete a project: stop containers, optionally remove dirs.

    1. Find all worktrees under the project
    2. If worktrees exist, prompt to delete them too (unless --yes)
    3. Stop and remove all containers
    4. If --purge or interactive, handle directory removal
    """
    runtime = get_container_runtime()
    if runtime is None:
        sys.exit(
            "Error: No container runtime found (docker or podman required)"
        )

    # Find worktrees
    wt_list = _find_deletable_worktrees(git_root)

    if wt_list:
        if not yes:
            try:
                wt_names = ", ".join(p.name for p, _, _ in wt_list)
                response = input(
                    f"Project has worktrees: {wt_names}\nAlso delete them? [y/N] "
                )
            except (EOFError, KeyboardInterrupt):
                print()
                return
            if response.lower() != "y":
                print("Cancelled.")
                return

        # Delete each worktree
        for wt_path, _, _branch in wt_list:
            _delete_worktree(wt_path, git_root, yes=yes)

    # Find and remove containers for the main project
    containers = find_containers_for_project(git_root)
    for name, _folder, state, _image_id in containers:
        if state == "running":
            cmd = [runtime, "stop", name]
            verbose_cmd(cmd)
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                print(f"Stopped: {name}")
            else:
                print(
                    f"Failed to stop {name}: {result.stderr}", file=sys.stderr
                )

    for name, _folder, _state, _image_id in containers:
        if remove_container(name):
            print(f"Removed container: {name}")
        else:
            print(f"Failed to remove container: {name}", file=sys.stderr)

    if purge:
        _purge_dirs(git_root)
    elif not yes:
        _prompt_purge(git_root)


def run_delete_mode(args: argparse.Namespace) -> None:
    """Run delete mode: delete a worktree or project and its containers."""
    target_arg = args.target
    purge = getattr(args, "purge", False)

    if target_arg:
        if target_arg.startswith("/") or target_arg.startswith("."):
            # Explicit path → treat as project
            target_path = Path(target_arg).resolve()
        else:
            # Bare name → resolve relative to cwd
            target_path = Path.cwd() / target_arg

        if not target_path.exists():
            sys.exit(f"Error: Project not found: {target_path}")

        # target_path must itself be a git root, not a subdirectory
        git_entry = target_path / ".git"
        if not git_entry.exists():
            sys.exit(f"Error: Not a git repository: {target_path}")

        if git_entry.is_file():
            sys.exit(
                f"Error: '{target_path.name}' is a worktree, not a project. "
                "Use 'jolo delete' (no argument) to pick worktrees interactively."
            )

        project_root = target_path

        # Confirm
        if not args.yes:
            try:
                response = input(
                    f"Delete project '{project_root.name}'? [y/N] "
                )
            except (EOFError, KeyboardInterrupt):
                print()
                return
            if response.lower() != "y":
                print("Cancelled.")
                return

        _delete_project(project_root, purge=purge, yes=args.yes)
    else:
        # Interactive picker
        items = _build_delete_picker_items()

        if not items:
            sys.exit("No worktrees or projects found to delete.")

        labels = [item["label"] for item in items]
        selected_line = _fzf_pick("Pick item to delete:", labels)
        if selected_line is None:
            return

        try:
            selected_idx = labels.index(selected_line)
        except ValueError:
            return

        selected = items[selected_idx]

        # Confirm
        if not args.yes:
            kind = selected["type"]
            name = selected["path"].name
            try:
                response = input(f"Delete {kind} '{name}'? [y/N] ")
            except (EOFError, KeyboardInterrupt):
                print()
                return
            if response.lower() != "y":
                print("Cancelled.")
                return

        if selected["type"] == "worktree":
            _delete_worktree(
                selected["path"], selected["git_root"], yes=args.yes
            )
        else:
            _delete_project(selected["git_root"], purge=purge, yes=args.yes)


def main(argv: list[str] | None = None) -> None:
    """Main entry point."""
    if argv is None:
        argv = sys.argv[1:]

    args = parse_args(argv)

    # Set verbose mode
    if args.verbose:
        constants.VERBOSE = True

    cmd = args.command

    if cmd == "list":
        run_list_mode(args)
        return

    if cmd == "status":
        run_status_mode(args)
        return

    if cmd == "doctor":
        run_doctor_mode(args)
        return

    if cmd == "down":
        run_stop_mode(args)
        return

    if cmd == "prune":
        run_prune_mode(args)
        return

    if cmd == "delete":
        run_delete_mode(args)
        return

    if cmd == "exec":
        run_exec_mode(args)
        return

    if cmd == "port":
        run_port_mode(args)
        return

    if cmd == "autonomous":
        from _jolo.autonomous import run_autonomous

        run_autonomous(args)
        return

    if cmd == "publish":
        from _jolo.publish import run_publish_mode

        run_publish_mode(args)
        return

    # No subcommand — show help
    if cmd is None:
        args._parser.print_help()
        return

    # Check guards (skip for research — always detached)
    if (
        cmd != "research"
        and not getattr(args, "detach", False)
        and not getattr(args, "prompt", None)
        and not getattr(args, "shell", False)
        and not getattr(args, "run", None)
    ):
        check_tmux_guard()

    # Dispatch to appropriate mode
    if cmd in ("attach", "a"):
        run_attach_mode(args)
    elif cmd == "clone":
        run_clone_mode(args)
    elif cmd == "spawn":
        run_spawn_mode(args)
    elif cmd == "research":
        run_research_mode(args)
    elif cmd == "init":
        run_init_mode(args)
    elif cmd == "create":
        run_create_mode(args)
    elif cmd == "tree":
        run_tree_mode(args)
    elif cmd == "up":
        run_up_mode(args)


if __name__ == "__main__":
    main()
