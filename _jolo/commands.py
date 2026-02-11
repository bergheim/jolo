"""Command handler functions and main dispatcher for jolo."""

import argparse
import json
import os
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
    find_git_root,
    generate_random_name,
    parse_args,
    parse_copy,
    parse_mount,
    select_languages_interactive,
    verbose_cmd,
    verbose_print,
)
from _jolo.container import (
    devcontainer_exec_command,
    devcontainer_exec_tmux,
    devcontainer_up,
    find_containers_for_project,
    find_stopped_containers_for_project,
    get_container_runtime,
    is_container_running,
    list_all_devcontainers,
    remove_container,
    remove_image,
    stop_container,
)
from _jolo.setup import (
    add_user_mounts,
    copy_template_files,
    copy_user_files,
    get_secrets,
    scaffold_devcontainer,
    setup_credential_cache,
    setup_emacs_config,
    setup_notification_hooks,
    sync_devcontainer,
    sync_skill_templates,
    write_prompt_file,
)
from _jolo.templates import (
    generate_precommit_config,
    get_justfile_content,
    get_motd_content,
    get_project_init_commands,
    get_test_framework_config,
    get_type_checker_config,
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


def load_config(global_config_dir: Path | None = None) -> dict:
    """Load configuration from TOML files.

    Config is loaded in order (later overrides earlier):
    1. Default config
    2. Global config: ~/.config/jolo/config.toml
    3. Project config: .jolo.toml in current directory
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
    project_config_file = Path.cwd() / ".jolo.toml"
    if project_config_file.exists():
        with open(project_config_file, "rb") as f:
            project_cfg = tomllib.load(f)
            config.update(project_cfg)

    return config


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


def run_open_mode(args: argparse.Namespace) -> None:
    """Run --open mode: pick a running container and attach to it."""
    containers = list_all_devcontainers()
    running = [
        (name, folder)
        for name, folder, state, image_id in containers
        if state == "running" and Path(folder).exists()
    ]

    if not running:
        sys.exit("No running containers found.")

    if len(running) == 1:
        _, folder = running[0]
        devcontainer_exec_tmux(Path(folder))
        return

    # Build display lines
    labels = []
    for _, folder in running:
        label = _format_container_display(folder)
        labels.append(f"{label:<30} {folder}")

    # Try fzf > gum > numbered fallback
    selected_folder = None
    if shutil.which("fzf"):
        try:
            result = subprocess.run(
                [
                    "fzf",
                    "--header",
                    "Pick a container:",
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
                return
            selected_folder = result.stdout.strip().split()[-1]
        except KeyboardInterrupt:
            return
    elif shutil.which("gum"):
        try:
            result = subprocess.run(
                ["gum", "choose", "--header", "Pick a container:"] + labels,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                return
            selected_folder = result.stdout.strip().split()[-1]
        except KeyboardInterrupt:
            return
    else:
        print("Pick a container:")
        for i, line in enumerate(labels, 1):
            print(f"  {i}. {line}")
        print()
        try:
            response = input("> ").strip()
        except (KeyboardInterrupt, EOFError):
            return
        if not response.isdigit():
            sys.exit("Invalid selection.")
        idx = int(response) - 1
        if not (0 <= idx < len(running)):
            sys.exit("Invalid selection.")
        _, selected_folder = running[idx]

    if selected_folder:
        devcontainer_exec_tmux(Path(selected_folder))


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
    if args.sync:
        sync_devcontainer(project_name, config=config)
        sync_skill_templates(git_root)
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

    # Set up secrets in environment
    secrets = get_secrets(config)
    os.environ.update(secrets)

    # Copy AI credentials for container isolation
    setup_credential_cache(git_root)
    setup_notification_hooks(git_root)

    # Set up Emacs config (copy config files, symlink packages)
    setup_emacs_config(git_root)

    # Write prompt file before starting container so entrypoint picks it up
    if args.prompt:
        write_prompt_file(git_root, args.agent, args.prompt)

    # Start devcontainer only if not already running (or --new forces restart)
    already_running = is_container_running(git_root)
    if args.new or not already_running:
        if not devcontainer_up(git_root, remove_existing=args.new):
            sys.exit("Error: Failed to start devcontainer")
    elif already_running:
        print("Container already running, reattaching. Use --new to rebuild.")

    if args.prompt:
        print(f"Started {args.agent} in: {project_name}")
        return

    if args.detach:
        print(f"Container started: {project_name}")
        return

    # Direct exec modes (no tmux)
    if args.shell:
        devcontainer_exec_command(git_root, "zsh")
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

    # Sync .devcontainer if requested
    if args.sync:
        sync_devcontainer(
            worktree_name, target_dir=worktree_path, config=config
        )
        sync_skill_templates(worktree_path)

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

    # Set up secrets in environment
    secrets = get_secrets(config)
    os.environ.update(secrets)

    # Copy AI credentials for container isolation
    setup_credential_cache(worktree_path)
    setup_notification_hooks(worktree_path)

    # Set up Emacs config (copy config files, symlink packages)
    setup_emacs_config(worktree_path)

    # Write prompt file before starting container so entrypoint picks it up
    if args.prompt:
        write_prompt_file(worktree_path, args.agent, args.prompt)

    # Start devcontainer only if not already running (or --new forces restart)
    if args.new or not is_container_running(worktree_path):
        if not devcontainer_up(worktree_path, remove_existing=args.new):
            sys.exit("Error: Failed to start devcontainer")

    if args.prompt:
        print(f"Started {args.agent} in: {worktree_path.name}")
        return

    if args.detach:
        print(f"Container started: {worktree_path.name}")
        return

    # Direct exec modes (no tmux)
    if args.shell:
        devcontainer_exec_command(worktree_path, "zsh")
        return

    if args.run:
        devcontainer_exec_command(worktree_path, args.run)
        return

    # Attach to tmux
    devcontainer_exec_tmux(worktree_path)


def run_create_mode(args: argparse.Namespace) -> None:
    """Run --create mode: create new project with devcontainer."""
    validate_create_mode(args.name)

    project_name = args.name
    project_path = Path.cwd() / project_name

    # Load config
    config = load_config()

    # Get languages from --lang or interactive selector
    if args.lang:
        languages = args.lang
    else:
        languages = select_languages_interactive()
        # Abort if user cancels (Ctrl+C or no selection)
        if not languages:
            print("No languages selected, aborting.", file=sys.stderr)
            sys.exit(1)

    # Primary language is the first in the list
    primary_language = languages[0] if languages else "other"

    # Create project directory
    project_path.mkdir()

    # Copy template files (AGENTS.md, CLAUDE.md, .gitignore, .editorconfig, etc.)
    copy_template_files(project_path)

    # Generate MOTD for the project
    motd_content = get_motd_content(primary_language, project_name)
    (project_path / "MOTD").write_text(motd_content)
    verbose_print("Generated MOTD")

    # Generate justfile for the project
    justfile_content = get_justfile_content(primary_language, project_name)
    (project_path / "justfile").write_text(justfile_content)
    verbose_print("Generated justfile")

    # Generate and write .pre-commit-config.yaml based on selected languages
    precommit_content = generate_precommit_config(languages)
    (project_path / ".pre-commit-config.yaml").write_text(precommit_content)
    verbose_print(
        f"Generated .pre-commit-config.yaml for languages: {', '.join(languages)}"
    )

    # Write test framework config for primary language
    test_config = get_test_framework_config(primary_language)
    # Python module names use underscores, not hyphens
    module_name = project_name.replace("-", "_")

    def replace_placeholders(text: str) -> str:
        return text.replace("{{PROJECT_NAME}}", project_name).replace(
            "{{PROJECT_NAME_UNDERSCORE}}", module_name
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
        main_path.write_text(test_config["main_content"])
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

    # Write type checker config for primary language
    type_config = get_type_checker_config(primary_language)
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
    scaffold_devcontainer(project_name, project_path, config=config)

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

    # Set up secrets in environment
    secrets = get_secrets(config)
    os.environ.update(secrets)

    # Copy AI credentials for container isolation
    setup_credential_cache(project_path)
    setup_notification_hooks(project_path)

    # Set up Emacs config (copy config files, symlink packages)
    setup_emacs_config(project_path)

    # Write prompt file before starting container so entrypoint picks it up
    if args.prompt:
        write_prompt_file(project_path, args.agent, args.prompt)

    # Start devcontainer (always remove existing for fresh project)
    if not devcontainer_up(project_path, remove_existing=True):
        sys.exit("Error: Failed to start devcontainer")

    # Run project init commands for primary language inside the container
    init_commands = get_project_init_commands(primary_language, project_name)
    if init_commands:
        combined_cmd = " && ".join([" ".join(c) for c in init_commands])
        verbose_print(f"Running in container: {combined_cmd}")
        devcontainer_exec_command(project_path, combined_cmd)

    if args.prompt:
        print(f"Started {args.agent} in: {project_name}")
        return

    if args.detach:
        print(f"Container started: {project_name}")
        return

    # Direct exec modes (no tmux)
    if args.shell:
        devcontainer_exec_command(project_path, "zsh")
        return

    if args.run:
        devcontainer_exec_command(project_path, args.run)
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

    # Sync or scaffold .devcontainer
    if args.sync:
        sync_devcontainer(project_name, project_path, config=config)
        sync_skill_templates(project_path)
    else:
        scaffold_devcontainer(project_name, project_path, config=config)

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

    # Set up secrets in environment
    secrets = get_secrets(config)
    os.environ.update(secrets)

    # Copy AI credentials for container isolation
    setup_credential_cache(project_path)
    setup_notification_hooks(project_path)

    # Set up Emacs config (copy config files, symlink packages)
    setup_emacs_config(project_path)

    # Write prompt file before starting container so entrypoint picks it up
    if args.prompt:
        write_prompt_file(project_path, args.agent, args.prompt)

    # Start devcontainer (always remove existing for fresh project)
    if not devcontainer_up(project_path, remove_existing=True):
        sys.exit("Error: Failed to start devcontainer")

    if args.prompt:
        print(f"Started {args.agent} in: {project_name}")
        return

    if args.detach:
        print(f"Container started: {project_name}")
        return

    # Direct exec modes (no tmux)
    if args.shell:
        devcontainer_exec_command(project_path, "zsh")
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

        # Sync .devcontainer if requested
        if args.sync:
            sync_devcontainer(
                name, target_dir=worktree_path, config=config, port=port
            )
            sync_skill_templates(worktree_path)

        # Update devcontainer.json with correct port if not syncing (sync handles it)
        devcontainer_json = (
            worktree_path / ".devcontainer" / "devcontainer.json"
        )
        if devcontainer_json.exists() and not args.sync:
            content = json.loads(devcontainer_json.read_text())
            if "containerEnv" not in content:
                content["containerEnv"] = {}
            content["containerEnv"]["PORT"] = str(port)
            devcontainer_json.write_text(json.dumps(content, indent=4))

        # Add user-specified mounts
        if args.mount:
            parsed_mounts = [parse_mount(m, name) for m in args.mount]
            add_user_mounts(devcontainer_json, parsed_mounts)

        # Copy user-specified files
        if args.copy:
            parsed_copies = [parse_copy(c, name) for c in args.copy]
            copy_user_files(parsed_copies, worktree_path)

        # Set up credentials and emacs config
        setup_credential_cache(worktree_path)
        setup_notification_hooks(worktree_path)
        setup_emacs_config(worktree_path)

        (worktree_path / ".devcontainer" / ".zsh-state").mkdir(exist_ok=True)

        worktree_paths.append(worktree_path)

    # Set up secrets in environment
    secrets = get_secrets(config)
    os.environ.update(secrets)

    # Start containers in parallel
    print(f"Starting {n} containers...")
    processes = []
    for i, path in enumerate(worktree_paths):
        cmd = ["devcontainer", "up", "--workspace-folder", str(path)]
        if args.new:
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
        inner_cmd = f"{agent_cmd} {quoted_prompt}"
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
    items: list[dict] = []

    for _, folder, _, _ in containers:
        folder_path = Path(folder)
        if not folder_path.exists():
            continue
        root = find_git_root(folder_path)
        if root is None or root in seen_roots:
            continue
        seen_roots.add(root)

        # Add the main project
        items.append(
            {
                "path": root,
                "label": f"{root.name:<24} (project)",
                "type": "project",
                "git_root": root,
                "branch": None,
            }
        )

        # Add worktrees
        for wt_path, commit, branch in _find_deletable_worktrees(root):
            items.append(
                {
                    "path": wt_path,
                    "label": f"  {wt_path.name:<22} ({branch}) [{commit[:7]}]",
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


def _delete_project(
    git_root: Path, purge: bool = False, yes: bool = False
) -> None:
    """Delete a project: stop containers, optionally remove dirs.

    1. Find all worktrees under the project
    2. If worktrees exist, prompt to delete them too (unless --yes)
    3. Stop and remove all containers
    4. If --purge, remove directories from disk
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


def run_delete_mode(args: argparse.Namespace) -> None:
    """Run delete mode: delete a worktree or project and its containers."""
    git_root = find_git_root()
    target_arg = args.target
    purge = getattr(args, "purge", False)

    if target_arg:
        # Target specified: either a path or a worktree name
        if target_arg.startswith("/") or target_arg.startswith("."):
            # Path → treat as project
            target_path = Path(target_arg).resolve()
            if not target_path.exists():
                sys.exit(f"Error: Path does not exist: {target_path}")
            project_root = find_git_root(target_path)
            if project_root is None:
                sys.exit(f"Error: Not a git repository: {target_path}")

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
            # Name → find worktree in current project
            if git_root is None:
                sys.exit(
                    "Error: Not in a git repository (needed to find worktree by name)."
                )

            wt_list = _find_deletable_worktrees(git_root)
            if not wt_list:
                sys.exit("No worktrees found to delete.")

            target = None
            for wt_path, _commit, branch in wt_list:
                if wt_path.name == target_arg:
                    target = (wt_path, branch)
                    break

            if target is None:
                available = ", ".join(p.name for p, _, _ in wt_list)
                sys.exit(
                    f"Error: Worktree '{target_arg}' not found. Available: {available}"
                )

            wt_path, branch = target

            # Confirm
            if not args.yes:
                try:
                    response = input(
                        f"Delete worktree '{wt_path.name}' (branch: {branch})? [y/N] "
                    )
                except (EOFError, KeyboardInterrupt):
                    print()
                    return
                if response.lower() != "y":
                    print("Cancelled.")
                    return

            _delete_worktree(wt_path, git_root, yes=args.yes)
    else:
        # Interactive picker
        items = _build_delete_picker_items()

        if not items:
            sys.exit("No worktrees or projects found to delete.")

        labels = [item["label"] for item in items]

        selected_idx = None
        if shutil.which("fzf"):
            try:
                result = subprocess.run(
                    [
                        "fzf",
                        "--header",
                        "Pick item to delete:",
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
                    return
                selected_line = result.stdout.strip()
                selected_idx = labels.index(selected_line)
            except (KeyboardInterrupt, ValueError):
                return
        else:
            print("Select item to delete:")
            for i, label in enumerate(labels, 1):
                print(f"  {i}. {label}")
            print()
            try:
                response = input("> ").strip()
            except (KeyboardInterrupt, EOFError):
                return
            if not response.isdigit():
                sys.exit("Invalid selection.")
            selected_idx = int(response) - 1
            if not (0 <= selected_idx < len(items)):
                sys.exit("Invalid selection.")

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

    if cmd == "down":
        run_stop_mode(args)
        return

    if cmd == "prune":
        run_prune_mode(args)
        return

    if cmd == "delete":
        run_delete_mode(args)
        return

    # No subcommand — show help
    if cmd is None:
        args._parser.print_help()
        return

    # Check guards (skip tmux guard if detaching, using prompt, shell, or run)
    if not args.detach and not args.prompt and not args.shell and not args.run:
        check_tmux_guard()

    # Dispatch to appropriate mode
    if cmd == "open":
        run_open_mode(args)
    elif cmd == "spawn":
        run_spawn_mode(args)
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
