"""Filesystem and credential setup functions for jolo."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from _jolo import constants
from _jolo.cli import read_port_from_devcontainer, verbose_print
from _jolo.container import build_devcontainer_json


def clear_directory_contents(path: Path) -> None:
    """Remove all contents of a directory without removing the directory itself.

    This preserves the directory inode, which is important for bind mounts.
    """
    if not path.exists():
        return
    for item in path.iterdir():
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()


def _patch_json_with_jq(
    path: Path, jq_args: list[str], jq_filter: str
) -> None:
    if not shutil.which("jq"):
        raise RuntimeError("jq is required but was not found on PATH")
    if path.exists():
        cmd = ["jq", *jq_args, jq_filter, str(path)]
    else:
        cmd = ["jq", "-n", *jq_args, jq_filter]
    result = subprocess.run(cmd, check=True, capture_output=True, text=True)
    path.write_text(result.stdout)


def setup_emacs_config(workspace_dir: Path) -> None:
    """Set up Emacs config by copying to .devcontainer/.emacs-config/.

    Copies ~/.config/emacs to .devcontainer/.emacs-config/ so the container
    has an isolated, writable copy of the config. Package directories
    (elpaca, tree-sitter) are in ~/.cache/emacs-container/ on the host,
    separate from the host's ~/.cache/emacs/ to avoid version/libc mismatches.
    """
    home = Path.home()
    emacs_src = home / ".config" / "emacs"
    emacs_dst = workspace_dir / ".devcontainer" / ".emacs-config"
    cache_dst = workspace_dir / ".devcontainer" / ".emacs-cache"

    # Skip if source doesn't exist
    if not emacs_src.exists():
        return

    # Create cache dir (fresh each time is fine)
    cache_dst.mkdir(parents=True, exist_ok=True)

    # Create container-specific cache dirs on host (separate from host Emacs cache)
    # These persist across projects so elpaca only builds once for the container's
    # Emacs version + musl libc combination.
    container_cache = home / ".cache" / "emacs-container"
    (container_cache / "elpaca").mkdir(parents=True, exist_ok=True)
    (container_cache / "tree-sitter").mkdir(parents=True, exist_ok=True)

    # Copy entire config directory, excluding heavy/redundant dirs
    ignore_func = shutil.ignore_patterns(
        ".git",
        "elpaca",
        "straight",
        "eln-cache",
        "tree-sitter",
        "elpa",
        "auto-save-list",
        "tramp",
        "server",
    )

    if emacs_dst.exists():
        clear_directory_contents(emacs_dst)
        shutil.copytree(
            emacs_src,
            emacs_dst,
            symlinks=True,
            dirs_exist_ok=True,
            ignore=ignore_func,
        )
    else:
        shutil.copytree(
            emacs_src, emacs_dst, symlinks=True, ignore=ignore_func
        )


def setup_stash() -> None:
    stash = Path.home() / "stash"
    stash.mkdir(parents=True, exist_ok=True)


def merge_mcp_configs(target_config: dict, mcp_templates_dir: Path) -> dict:
    """Merge all MCP JSON templates into the provided config's mcpServers key.

    This allows for modular MCP configuration by simply dropping JSON files
    into the templates/mcp/ directory.
    """
    if not mcp_templates_dir.exists():
        return target_config

    mcp_servers = target_config.setdefault("mcpServers", {})

    for mcp_file in mcp_templates_dir.glob("*.json"):
        try:
            mcp_data = json.loads(mcp_file.read_text())
            if "mcpServers" in mcp_data:
                mcp_servers.update(mcp_data["mcpServers"])
        except Exception as e:
            print(
                f"Warning: Failed to load MCP template {mcp_file}: {e}",
                file=sys.stderr,
            )

    return target_config


def setup_credential_cache(workspace_dir: Path) -> None:
    """Stage AI credentials for container use.

    Claude: .credentials.json is mounted RW from the host (token refreshes
    persist). Only settings.json is copied (for notification hook injection).
    Gemini/Codex/Pi: fully copied to .devcontainer cache dirs.
    """
    home = Path.home()
    templates_dir = Path(__file__).resolve().parent.parent / "templates"
    mcp_templates = templates_dir / "mcp"

    # Claude credentials
    claude_cache = workspace_dir / ".devcontainer" / ".claude-cache"
    if claude_cache.exists():
        clear_directory_contents(claude_cache)
    else:
        claude_cache.mkdir(parents=True)

    # .credentials.json is mounted RW directly from the host (token refreshes persist).
    # Only copy settings.json (we inject notification hooks into it).
    claude_dir = home / ".claude"
    settings_src = claude_dir / "settings.json"
    if settings_src.exists():
        shutil.copy2(settings_src, claude_cache / "settings.json")

    claude_json_src = home / ".claude.json"
    claude_json_dst = workspace_dir / ".devcontainer" / ".claude.json"
    if claude_json_src.exists():
        shutil.copy2(claude_json_src, claude_json_dst)

        # Inject MCP servers into the copied .claude.json
        try:
            claude_config = json.loads(claude_json_dst.read_text())
            project_name = workspace_dir.name
            container_path = f"/workspaces/{project_name}"

            # Inject into the specific project's entry
            project_entry = claude_config.setdefault(
                "projects", {}
            ).setdefault(container_path, {})
            merge_mcp_configs(project_entry, mcp_templates)

            claude_json_dst.write_text(json.dumps(claude_config, indent=2))
        except Exception as e:
            print(
                f"Warning: Failed to inject MCP configs into .claude.json: {e}",
                file=sys.stderr,
            )

    # Gemini credentials
    gemini_cache = workspace_dir / ".devcontainer" / ".gemini-cache"
    if gemini_cache.exists():
        clear_directory_contents(gemini_cache)
    else:
        gemini_cache.mkdir(parents=True)

    gemini_dir = home / ".gemini"
    for filename in [
        "settings.json",
        "google_accounts.json",
        "oauth_creds.json",
    ]:
        src = gemini_dir / filename
        if src.exists():
            shutil.copy2(src, gemini_cache / filename)

    # Gemini CLI expects ~/.gemini/tmp/... to exist and be writable.
    (gemini_cache / "tmp").mkdir(parents=True, exist_ok=True)

    # Disable node-pty in container — it crashes on Alpine/musl (forkpty segfault).
    # Gemini falls back to child_process which works fine.
    settings_path = gemini_cache / "settings.json"

    if settings_path.exists():
        settings = json.loads(settings_path.read_text())
    else:
        settings = {}

    # FIXME: waiting for https://github.com/google-gemini/gemini-cli/issues/14087
    settings.setdefault("tools", {}).setdefault("shell", {})[
        "enableInteractiveShell"
    ] = False

    settings.setdefault("security", {}).setdefault("folderTrust", {})[
        "enabled"
    ] = True

    # Inject MCP servers into Gemini settings
    merge_mcp_configs(settings, mcp_templates)

    settings_path.write_text(json.dumps(settings, indent="\t"))

    trusted_folders_path = gemini_cache / "trustedFolders.json"
    project_path = f"/workspaces/{workspace_dir.name}"
    _patch_json_with_jq(
        trusted_folders_path,
        ["--arg", "path", project_path, "--arg", "value", "TRUST_FOLDER"],
        ".[$path] = $value",
    )

    # Codex credentials
    codex_cache = workspace_dir / ".devcontainer" / ".codex-cache"
    if codex_cache.exists():
        clear_directory_contents(codex_cache)
    else:
        codex_cache.mkdir(parents=True)

    codex_dir = home / ".codex"
    for filename in ["config.toml", "auth.json"]:
        src = codex_dir / filename
        if src.exists():
            shutil.copy2(src, codex_cache / filename)

    # Inject MCP servers into Codex config.toml
    codex_config_path = codex_cache / "config.toml"
    try:
        # We need the aggregated MCP config
        mcp_data = merge_mcp_configs({}, mcp_templates)
        mcp_servers = mcp_data.get("mcpServers", {})

        if mcp_servers:
            # Simple TOML generation for the mcp_servers section
            toml_lines = []
            if codex_config_path.exists():
                toml_content = codex_config_path.read_text()
                # If mcp_servers already exists, we might overwrite it or append.
                # For now, we'll append a fresh section if it's missing or update it.
                toml_lines.append(toml_content)
                if not toml_content.endswith("\n"):
                    toml_lines.append("")

            for name, server in mcp_servers.items():
                toml_lines.append(f"\n[mcp_servers.{name}]")
                toml_lines.append(f'command = "{server["command"]}"')
                args_str = ", ".join(f'"{a}"' for a in server.get("args", []))
                toml_lines.append(f"args = [{args_str}]")
                if "env" in server:
                    for k, v in server["env"].items():
                        toml_lines.append(f'env.{k} = "{v}"')

            codex_config_path.write_text("\n".join(toml_lines) + "\n")
    except Exception as e:
        print(
            f"Warning: Failed to inject MCP configs into Codex config.toml: {e}",
            file=sys.stderr,
        )

    # Pi credentials
    pi_cache = workspace_dir / ".devcontainer" / ".pi-cache"
    if pi_cache.exists():
        clear_directory_contents(pi_cache)
    else:
        pi_cache.mkdir(parents=True)

    pi_dir = home / ".pi"
    if pi_dir.exists():
        for item in pi_dir.iterdir():
            dst = pi_cache / item.name
            if item.is_dir():
                if dst.exists():
                    shutil.rmtree(dst)
                shutil.copytree(item, dst, symlinks=True)
            else:
                shutil.copy2(item, dst)


def _load_json_safe(path: Path) -> dict:
    """Load JSON from a file, returning empty dict on missing/corrupt files."""
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, ValueError):
        return {}


def setup_notification_hooks(
    workspace_dir: Path, notify_threshold: int = 60
) -> None:
    """Inject agent completion notification hooks into cached settings files.

    Adds hooks that call notify when agents finish.
    Merges with existing hooks (does not overwrite).
    Must be called after setup_credential_cache() so the cache dirs exist.
    """
    # Claude: inject SessionEnd hook into .claude-cache/settings.json
    claude_settings_path = (
        workspace_dir / ".devcontainer" / ".claude-cache" / "settings.json"
    )
    settings = _load_json_safe(claude_settings_path)

    hooks = settings.setdefault("hooks", {})

    # SessionEnd: always notify when agent exits
    session_hooks = hooks.setdefault("SessionEnd", [])
    notify_hook = {
        "hooks": [{"type": "command", "command": "AGENT=claude notify"}],
    }
    if not any("notify" in str(h) for h in session_hooks):
        session_hooks.append(notify_hook)

    # UserPromptSubmit: record timestamp for elapsed-time tracking
    prompt_hooks = hooks.setdefault("UserPromptSubmit", [])
    stamp_hook = {
        "hooks": [{"type": "command", "command": "notify stamp"}],
    }
    if not any("notify stamp" in str(h) for h in prompt_hooks):
        prompt_hooks.append(stamp_hook)

    # Stop: notify only if response took longer than threshold
    stop_hooks = hooks.setdefault("Stop", [])
    slow_hook = {
        "hooks": [
            {
                "type": "command",
                "command": f"AGENT=claude notify --if-slow {notify_threshold}",
            }
        ],
    }
    if not any("--if-slow" in str(h) for h in stop_hooks):
        stop_hooks.append(slow_hook)

    claude_settings_path.parent.mkdir(parents=True, exist_ok=True)
    claude_settings_path.write_text(json.dumps(settings, indent=2))

    # Gemini: inject SessionEnd hook into .gemini-cache/settings.json
    gemini_settings_path = (
        workspace_dir / ".devcontainer" / ".gemini-cache" / "settings.json"
    )
    settings = _load_json_safe(gemini_settings_path)

    hooks = settings.setdefault("hooks", {})
    session_end_hooks = hooks.setdefault("SessionEnd", [])
    notify_hook = {
        "hooks": [{"type": "command", "command": "AGENT=gemini notify"}],
    }
    if not any("notify" in str(h) for h in session_end_hooks):
        session_end_hooks.append(notify_hook)
    gemini_settings_path.parent.mkdir(parents=True, exist_ok=True)
    gemini_settings_path.write_text(json.dumps(settings, indent="\t"))

    # Codex: append notify setting to .codex-cache/config.toml (best-effort)
    codex_config_path = (
        workspace_dir / ".devcontainer" / ".codex-cache" / "config.toml"
    )
    if codex_config_path.exists():
        config = codex_config_path.read_text()
        has_notify = any(
            line.strip().startswith("notify") for line in config.splitlines()
        )
        if not has_notify:
            if not config.endswith("\n"):
                config += "\n"
            config += 'notify = ["sh", "-c", "AGENT=codex notify"]\n'
            codex_config_path.write_text(config)


def copy_template_files(target_dir: Path) -> None:
    """Copy template files to the target directory.

    Copies AGENTS.md, CLAUDE.md, GEMINI.md, .gitignore, and .editorconfig
    from the templates/ directory, plus docs/ directory (TODO.org, RESEARCH.org).

    Note: .pre-commit-config.yaml is generated dynamically based on language selection,
    not copied from templates.

    Prints a warning if templates/ directory doesn't exist but continues.
    """
    templates_dir = Path(__file__).resolve().parent.parent / "templates"

    if not templates_dir.exists():
        print(
            f"Warning: Templates directory not found: {templates_dir}",
            file=sys.stderr,
        )
        return

    template_files = [
        "AGENTS.md",
        "CLAUDE.md",
        "GEMINI.md",
        ".gitignore",
        ".editorconfig",
    ]

    for filename in template_files:
        src = templates_dir / filename
        if src.exists():
            dst = target_dir / filename
            shutil.copy2(src, dst)
            verbose_print(f"Copied template: {filename}")

    # Copy template directories (skills, agent config, docs)
    template_dirs = [".agents", ".claude", ".gemini", ".pi", "docs", "scripts"]
    for dirname in template_dirs:
        src = templates_dir / dirname
        if src.exists():
            dst = target_dir / dirname
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst, symlinks=True)
            verbose_print(f"Copied template dir: {dirname}/")


def ensure_test_gate_script(target_dir: Path) -> None:
    """Ensure scripts/test-gate exists in the target project."""
    templates_dir = Path(__file__).resolve().parent.parent / "templates"
    src = templates_dir / "scripts" / "test-gate"
    if not src.exists():
        print(
            f"Warning: test-gate template not found: {src}",
            file=sys.stderr,
        )
        return

    dst = target_dir / "scripts" / "test-gate"
    if dst.exists():
        return

    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    verbose_print("Copied template: scripts/test-gate")


def scaffold_devcontainer(
    project_name: str,
    target_dir: Path | None = None,
    config: dict | None = None,
    port: int | None = None,
) -> bool:
    """Create .devcontainer directory with templates.

    Returns True if created, False if already exists.
    Port is randomly assigned in 4000-5000 if not specified.
    """
    if target_dir is None:
        target_dir = Path.cwd()
    if config is None:
        config = constants.DEFAULT_CONFIG

    devcontainer_dir = target_dir / ".devcontainer"

    if devcontainer_dir.exists():
        return False

    devcontainer_dir.mkdir(parents=True)

    # Write devcontainer.json (dynamically built based on environment)
    json_content = build_devcontainer_json(
        project_name,
        port=port,
        base_image=config["base_image"],
        remote_user=os.environ.get("USER", "dev"),
    )
    (devcontainer_dir / "devcontainer.json").write_text(json_content)

    return True


def sync_devcontainer(
    project_name: str,
    target_dir: Path | None = None,
    config: dict | None = None,
    port: int | None = None,
) -> None:
    """Regenerate .devcontainer from template, overwriting existing files.

    Unlike scaffold_devcontainer, this always writes the files even if
    .devcontainer already exists. Preserves the existing port assignment
    unless a new one is explicitly provided.
    """
    if target_dir is None:
        target_dir = Path.cwd()
    if config is None:
        config = constants.DEFAULT_CONFIG

    # Preserve existing port if not explicitly overridden
    if port is None:
        port = read_port_from_devcontainer(target_dir)

    devcontainer_dir = target_dir / ".devcontainer"
    devcontainer_dir.mkdir(parents=True, exist_ok=True)

    # Write devcontainer.json (dynamically built based on environment)
    json_content = build_devcontainer_json(
        project_name,
        port=port,
        base_image=config["base_image"],
        remote_user=os.environ.get("USER", "dev"),
    )
    (devcontainer_dir / "devcontainer.json").write_text(json_content)

    print("Synced .devcontainer/ with current config")


def sync_skill_templates(target_dir: Path) -> None:
    """Sync template skills into an existing project.

    Copies each skill directory from templates/.agents/skills into
    .agents/skills, overwriting matching skills but preserving any
    extra skills the project may have added.
    """
    templates_dir = Path(__file__).resolve().parent.parent / "templates"
    skills_src = templates_dir / ".agents" / "skills"
    if not skills_src.exists():
        return

    skills_dst = target_dir / ".agents" / "skills"
    skills_dst.mkdir(parents=True, exist_ok=True)

    if skills_dst.resolve() == skills_src.resolve():
        verbose_print("Skills dst is symlinked to src, skipping sync")
        return

    for entry in skills_src.iterdir():
        if not entry.is_dir():
            continue
        dst = skills_dst / entry.name
        if dst.exists():
            shutil.rmtree(dst)
        shutil.copytree(entry, dst, symlinks=True)
        verbose_print(f"Synced skill: {entry.name}")

    # Ensure agent skill symlinks exist
    for agent_dir in [".claude", ".gemini", ".pi"]:
        link_dir = target_dir / agent_dir
        link_dir.mkdir(parents=True, exist_ok=True)
        link_path = link_dir / "skills"
        if not link_path.exists() and not link_path.is_symlink():
            os.symlink("../.agents/skills", link_path)
            verbose_print(f"Created {agent_dir}/skills symlink")


def get_secrets(config: dict | None = None) -> dict[str, str]:
    """Get API secrets from pass or environment variables."""
    if config is None:
        config = constants.DEFAULT_CONFIG

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

    # Get GitHub token from gh CLI or environment
    if "GH_TOKEN" not in secrets:
        gh_token = os.environ.get("GH_TOKEN", "") or os.environ.get(
            "GITHUB_TOKEN", ""
        )
        if not gh_token and shutil.which("gh"):
            try:
                result = subprocess.run(
                    ["gh", "auth", "token"],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    gh_token = result.stdout.strip()
            except (subprocess.TimeoutExpired, subprocess.SubprocessError):
                pass
        secrets["GH_TOKEN"] = gh_token

    return secrets


def add_user_mounts(devcontainer_json_path: Path, mounts: list[dict]) -> None:
    """Add user-specified mounts to devcontainer.json.

    Args:
        devcontainer_json_path: Path to devcontainer.json
        mounts: List of mount dicts with keys: source, target, readonly
    """
    if not mounts:
        return

    content = json.loads(devcontainer_json_path.read_text())

    if "mounts" not in content:
        content["mounts"] = []

    for mount in mounts:
        mount_str = (
            f"source={mount['source']},target={mount['target']},type=bind"
        )
        if mount["readonly"]:
            mount_str += ",readonly"
        content["mounts"].append(mount_str)

    devcontainer_json_path.write_text(json.dumps(content, indent=4))


def copy_user_files(copies: list[dict], workspace_dir: Path) -> None:
    """Copy user-specified files to workspace.

    Args:
        copies: List of copy dicts with keys: source, target
        workspace_dir: The workspace directory (project root)
    """
    for copy_spec in copies:
        source = Path(copy_spec["source"])
        # Convert absolute container path to workspace-relative path
        target_path = copy_spec["target"]
        if target_path.startswith("/workspaces/"):
            # Strip /workspaces/project/ prefix to get relative path
            parts = target_path.split("/", 3)
            if len(parts) >= 4:
                relative = parts[3]
                target = workspace_dir / relative
            else:
                # Just the project dir, use source basename
                target = workspace_dir / source.name
        else:
            # Absolute path outside workspace - copy there directly
            target = Path(target_path)

        if not source.exists():
            sys.exit(f"Error: Copy source does not exist: {source}")

        # Create parent directories if needed
        target.parent.mkdir(parents=True, exist_ok=True)

        # Copy file
        shutil.copy2(source, target)
        verbose_print(f"Copied {source} -> {target}")


def add_worktree_git_mount(
    devcontainer_json_path: Path, main_git_dir: Path
) -> None:
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


def write_prompt_file(workspace_dir: Path, agent: str, prompt: str) -> None:
    """Write prompt and agent name files for tmux-layout.sh to pick up on start."""
    devcontainer_dir = workspace_dir / ".devcontainer"
    devcontainer_dir.mkdir(parents=True, exist_ok=True)
    (devcontainer_dir / ".agent-prompt").write_text(prompt)
    (devcontainer_dir / ".agent-name").write_text(agent)
