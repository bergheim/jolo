"""Filesystem and credential setup functions for jolo."""

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

from _jolo import constants
from _jolo.cli import (
    detect_flavors,
    read_port_from_devcontainer,
    verbose_print,
)
from _jolo.container import build_devcontainer_json

DEFAULT_CODEX_REASONING_EFFORT = "high"
PI_LLAMA_PROVIDER = "llama"
PI_LLAMA_CONTEXT_WINDOW = 32768
PI_LLAMA_MAX_TOKENS = 8192
PI_LLAMA_DEFAULT_MODEL_PRIORITY = [
    "qwen3-coder-next",
    "qwen3-coder",
    "qwen3.6",
    "qwen3.6-small",
    "qwen3.5",
]


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


def _ensure_top_level_toml_key(toml_content: str, key: str, value: str) -> str:
    if any(
        re.match(rf"^{re.escape(key)}\s*=", line.strip())
        for line in toml_content.splitlines()
    ):
        return toml_content

    new_setting = f'{key} = "{value}"'
    table_match = re.search(r"(?m)^\s*\[", toml_content)
    if table_match:
        before = toml_content[: table_match.start()]
        after = toml_content[table_match.start() :]
        if before and not before.endswith("\n"):
            before += "\n"
        return f"{before}{new_setting}\n\n{after}"

    content = toml_content
    if content and not content.endswith("\n"):
        content += "\n"
    return f"{content}{new_setting}\n"


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

            claude_config["effortCalloutV2Dismissed"] = True

            # Inject into the specific project's entry
            project_entry = claude_config.setdefault(
                "projects", {}
            ).setdefault(container_path, {})
            project_entry["hasTrustDialogAccepted"] = True
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

    # Extensions and enablement config
    extensions_src = gemini_dir / "extensions"
    if extensions_src.is_dir():
        shutil.copytree(
            extensions_src, gemini_cache / "extensions", symlinks=True
        )
    enablement_src = gemini_dir / "extension-enablement.json"
    if enablement_src.exists():
        shutil.copy2(
            enablement_src, gemini_cache / "extension-enablement.json"
        )

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
    if codex_config_path.exists():
        config = codex_config_path.read_text()
        config = _ensure_top_level_toml_key(
            config,
            "model_reasoning_effort",
            DEFAULT_CODEX_REASONING_EFFORT,
        )
        codex_config_path.write_text(config)

    # Trust the container workspace
    if codex_config_path.exists():
        project_name = workspace_dir.name
        container_path = f"/workspaces/{project_name}"
        config = codex_config_path.read_text()
        section = f'[projects."{container_path}"]'
        if section not in config:
            config = (
                config.rstrip() + f'\n\n{section}\ntrust_level = "trusted"\n'
            )
            codex_config_path.write_text(config)

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

    llama_host = os.environ.get("LLAMA_HOST")
    if llama_host:
        _write_pi_llama_config(pi_cache, llama_host)


def _load_json_safe(path: Path) -> dict:
    """Load JSON from a file, returning empty dict on missing/corrupt files."""
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, ValueError):
        return {}


def _llama_v1_base_url(llama_host: str) -> str:
    return llama_host.rstrip("/") + "/v1"


def _fetch_llama_model_ids(llama_host: str) -> list[str]:
    models_url = _llama_v1_base_url(llama_host) + "/models"
    try:
        with urllib.request.urlopen(models_url, timeout=3) as response:
            payload = json.loads(response.read().decode())
    except (
        OSError,
        TimeoutError,
        urllib.error.URLError,
        json.JSONDecodeError,
    ) as e:
        print(
            f"Warning: Failed to fetch llama-swap models from {models_url}: {e}",
            file=sys.stderr,
        )
        return []

    return [
        item["id"]
        for item in payload.get("data", [])
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    ]


def _pi_chat_model_ids(model_ids: list[str]) -> list[str]:
    blocked = ("embed", "embedding", "bge", "e5")
    return [
        model_id
        for model_id in model_ids
        if not any(part in model_id.lower() for part in blocked)
    ]


def _pi_default_llama_model(model_ids: list[str]) -> str | None:
    for preferred in PI_LLAMA_DEFAULT_MODEL_PRIORITY:
        if preferred in model_ids:
            return preferred
    return model_ids[0] if model_ids else None


def _write_pi_llama_config(pi_cache: Path, llama_host: str) -> None:
    agent_dir = pi_cache / "agent"
    agent_dir.mkdir(parents=True, exist_ok=True)

    model_ids = _pi_chat_model_ids(_fetch_llama_model_ids(llama_host))
    if not model_ids:
        return

    models_path = agent_dir / "models.json"
    models = _load_json_safe(models_path)
    providers = models.setdefault("providers", {})
    providers[PI_LLAMA_PROVIDER] = {
        "baseUrl": _llama_v1_base_url(llama_host),
        "api": "openai-completions",
        "apiKey": "llama",
        "compat": {
            "supportsDeveloperRole": False,
            "supportsReasoningEffort": False,
            "supportsUsageInStreaming": False,
            "maxTokensField": "max_tokens",
        },
        "models": [
            {
                "id": model_id,
                "name": f"{model_id} (llama.cpp)",
                "reasoning": False,
                "input": ["text"],
                "contextWindow": PI_LLAMA_CONTEXT_WINDOW,
                "maxTokens": PI_LLAMA_MAX_TOKENS,
                "cost": {
                    "input": 0,
                    "output": 0,
                    "cacheRead": 0,
                    "cacheWrite": 0,
                },
            }
            for model_id in model_ids
        ],
    }
    models_path.write_text(json.dumps(models, indent=2) + "\n")

    default_model = _pi_default_llama_model(model_ids)
    if default_model is None:
        return

    settings_path = agent_dir / "settings.json"
    settings = _load_json_safe(settings_path)
    settings["defaultProvider"] = PI_LLAMA_PROVIDER
    settings["defaultModel"] = default_model
    settings_path.write_text(json.dumps(settings, indent=2) + "\n")


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

    # Migrate: remove stale notify-done hooks (renamed to notify)
    for hook_list in hooks.values():
        hook_list[:] = [h for h in hook_list if "notify-done" not in str(h)]

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
    # Replace existing --if-slow hook (threshold may have changed), or append
    replaced = False
    for i, h in enumerate(stop_hooks):
        if "notify --if-slow" in str(h):
            stop_hooks[i] = slow_hook
            replaced = True
            break
    if not replaced:
        stop_hooks.append(slow_hook)

    claude_settings_path.parent.mkdir(parents=True, exist_ok=True)
    claude_settings_path.write_text(json.dumps(settings, indent=2))

    # Gemini: inject SessionEnd hook into .gemini-cache/settings.json
    gemini_settings_path = (
        workspace_dir / ".devcontainer" / ".gemini-cache" / "settings.json"
    )
    settings = _load_json_safe(gemini_settings_path)

    hooks = settings.setdefault("hooks", {})
    for hook_list in hooks.values():
        hook_list[:] = [h for h in hook_list if "notify-done" not in str(h)]
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


TEMPLATE_HASHES_FILE = ".devcontainer/.template-hashes.json"

# Files that sync_template_files manages
SYNCABLE_TEMPLATE_FILES = [
    "AGENTS.md",
    "CLAUDE.md",
    "GEMINI.md",
]

# Files that sync should drop in if missing but never overwrite if present.
# Currently empty — perf-rig.toml graduated to strictly-owned sync so
# `--force` can actually retrofit placeholder renames and the like.
# User tuning (scenarios, thresholds) is recovered via `.jolonew` on a
# no-force sync of an edited file, or from git when they --force.
COPY_IF_MISSING_TEMPLATES: list[str] = []


def _file_hash(path: Path) -> str:
    """Return sha256 hex digest of a file's contents."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_template_hashes(target_dir: Path) -> dict:
    return _load_json_safe(target_dir / TEMPLATE_HASHES_FILE)


def _save_template_hashes(
    target_dir: Path, filenames: list[str], hashes: dict | None = None
) -> None:
    """Record hashes of template files as written to the target directory."""
    if hashes is None:
        hashes = _load_template_hashes(target_dir)
    for filename in filenames:
        dst = target_dir / filename
        if dst.exists():
            hashes[filename] = _file_hash(dst)
    path = target_dir / TEMPLATE_HASHES_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(hashes, indent=2) + "\n")


def record_template_hashes(target_dir: Path, filenames: list[str]) -> None:
    """Record hashes for managed files that were written outside sync."""
    if not filenames:
        return
    _save_template_hashes(target_dir, filenames)


def _sync_one_file(
    target_dir: Path,
    filename: str,
    new_bytes: bytes,
    hashes: dict,
    force: bool = False,
) -> str:
    """Sync one file. Under ``--force``, always overwrites — git is the
    safety net for user edits, and silently skipping fresh template
    bumps is the failure mode users cannot detect. Without ``--force``,
    an untracked or hand-edited file is left alone; a tracked file
    whose user diverged from the recorded hash gets a ``.jolonew``
    sibling so the user can diff and merge.

    Returns "written", "updated", "jolonew", "unchanged", or "untracked".
    """
    dst = target_dir / filename
    new_hash = hashlib.sha256(new_bytes).hexdigest()

    if not dst.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(new_bytes)
        hashes[filename] = new_hash
        verbose_print(f"Copied: {filename}")
        return "written"

    current_hash = _file_hash(dst)
    stored_hash = hashes.get(filename)

    if current_hash == new_hash:
        # Heal the hash only for files we already managed; don't claim
        # ownership of files that match by coincidence.
        if stored_hash is not None:
            hashes[filename] = new_hash
        return "unchanged"

    if force:
        dst.write_bytes(new_bytes)
        hashes[filename] = new_hash
        print(f"  Force-overwrote {filename}")
        return "updated"

    if stored_hash is None:
        return "untracked"

    if stored_hash == current_hash:
        dst.write_bytes(new_bytes)
        hashes[filename] = new_hash
        verbose_print(f"Synced: {filename}")
        return "updated"

    jolonew = target_dir / f"{filename}.jolonew"
    jolonew.write_bytes(new_bytes)
    print(f"  Template update available: {jolonew.name} (yours was edited)")
    return "jolonew"


_NO_SHARED_RECIPES_FLAVORS = {"meta"}


def _stage_touched_files(target_dir: Path, filenames: list[str]) -> None:
    """Stage files that ``--force`` rewrote so the user's next commit is
    not blocked by pre-commit's "config-must-be-staged" check, and so
    the overwrite is visible in ``git status`` rather than mixed with
    later edits. Silently skips when the target is not a git checkout."""
    if not (target_dir / ".git").exists():
        return
    existing = [f for f in filenames if (target_dir / f).exists()]
    if not existing:
        return
    try:
        subprocess.run(
            ["git", "add", "--", *existing],
            cwd=str(target_dir),
            check=False,
            capture_output=True,
        )
    except FileNotFoundError:
        pass


def _resolve_flavor(target_dir: Path, force: bool) -> str | None:
    """Pick the flavor to regen against. Returns ``None`` only when there
    is no flavor AND ``--force`` was not requested. Under ``--force`` the
    contract is "overwrite the file with the template, period" — so we
    fall back to ``other`` when detection finds nothing rather than
    silently skipping."""
    flavors = detect_flavors(target_dir)
    if flavors:
        return flavors[0]
    if force:
        return "other"
    return None


def _regenerated_justfile_common_bytes(
    target_dir: Path, force: bool = False
) -> bytes | None:
    """Return current ``justfile.common`` bytes for this project, or ``None``
    if flavor cannot be resolved or the flavor opts out of shared recipes."""
    from _jolo.templates import get_justfile_common_content

    flavor = _resolve_flavor(target_dir, force)
    if flavor is None:
        return None
    if flavor in _NO_SHARED_RECIPES_FLAVORS:
        return None
    return get_justfile_common_content(target_dir.name).encode()


def _regenerated_justfile_bytes(
    target_dir: Path, force: bool = False
) -> bytes | None:
    """Return current ``justfile`` bytes for this project, or ``None``
    when no flavor is resolvable without ``--force``.

    The ``justfile`` is normally user-owned (jolo only writes it once
    at create time), but ``jolo up --recreate --force`` reclaims it so
    a project can be returned to a known-good shape after the user's
    edits diverge from the template (e.g. duplicate recipes after
    ``git restore`` from a pre-split commit). Custom recipes the user
    wants to keep should be re-added afterwards from git history.
    """
    from _jolo.templates import get_justfile_content

    flavor = _resolve_flavor(target_dir, force)
    if flavor is None:
        return None
    return get_justfile_content(flavor, target_dir.name).encode()


def _regenerated_perf_rig_bytes(
    target_dir: Path, force: bool = False
) -> bytes | None:
    """Return current ``perf-rig.toml`` bytes for this project, or ``None``
    if flavor cannot be resolved or the flavor opts out of shared recipes."""
    from _jolo.templates import get_perf_rig_content

    flavor = _resolve_flavor(target_dir, force)
    if flavor is None:
        return None
    if flavor in _NO_SHARED_RECIPES_FLAVORS:
        return None
    return get_perf_rig_content(flavor, target_dir.name).encode()


def _regenerated_precommit_config_bytes(target_dir: Path) -> bytes | None:
    """Return current ``.pre-commit-config.yaml`` bytes for this project."""
    from _jolo.templates import generate_precommit_config

    flavors = detect_flavors(target_dir)
    return generate_precommit_config(flavors).encode()


def _regenerated_scaffold_files(
    target_dir: Path, force: bool = False
) -> list[tuple[str, bytes]]:
    """Return rendered scaffold files for the resolved flavor."""
    from _jolo.templates import (
        get_scaffold_files,
        to_pascal_case,
        to_snake_case,
    )

    flavor = _resolve_flavor(target_dir, force)
    if flavor is None:
        return []

    project_name = target_dir.name
    module_name = to_snake_case(project_name)
    pascal_name = to_pascal_case(project_name)

    def replace_placeholders(text: str) -> str:
        return (
            text.replace("{{PROJECT_NAME}}", project_name)
            .replace("{{PROJECT_NAME_UNDERSCORE}}", module_name)
            .replace("{{MODULE_NAME}}", pascal_name)
        )

    return [
        (
            replace_placeholders(rel_path),
            replace_placeholders(content).encode(),
        )
        for rel_path, content in get_scaffold_files(flavor)
    ]


# Managed-injection block for `.git/hooks/post-commit`. Bracketed by
# sentinel markers so jolo refreshes its block without touching the
# rest of the file, and other tools (pre-commit framework, husky,
# user scripts) can co-exist in the same hook.
_JOLO_POST_COMMIT_BEGIN = "# >>> jolo-perf-start <<<"
_JOLO_POST_COMMIT_END = "# >>> jolo-perf-end <<<"
_JOLO_POST_COMMIT_BLOCK = (
    f"{_JOLO_POST_COMMIT_BEGIN}\n"
    "# Managed by jolo. Edits inside this block will be overwritten\n"
    "# on the next `jolo up --recreate`. Edit outside the markers.\n"
    "(PERF_RAW=1 just perf >>.jolo-perf.log 2>&1 </dev/null &)\n"
    f"{_JOLO_POST_COMMIT_END}\n"
)
# Anchored to line starts (so a stray marker substring inside user
# content can't ever match), tolerant of trailing whitespace on the
# marker line and of CRLF line endings.
_JOLO_BLOCK_RE = re.compile(
    r"(?ms)^"
    + re.escape(_JOLO_POST_COMMIT_BEGIN)
    + r"[ \t]*\r?\n"
    + r".*?"
    + r"^"
    + re.escape(_JOLO_POST_COMMIT_END)
    + r"[ \t]*\r?\n?"
)


def _replace_or_append_jolo_block(existing: str, block: str) -> str:
    """Return `existing` with the jolo-managed block re-written at the end.

    Strips every existing managed block (so a previous duplication bug
    converges to a single block), then appends ``block``. A shebang is
    prepended only when the resulting file would otherwise lack one —
    catches the empty-input case AND the recover-from-block-only case
    (where strip leaves an empty buffer that needs to become a valid
    hook script).
    """
    stripped = _JOLO_BLOCK_RE.sub("", existing)
    if not stripped.startswith("#!"):
        stripped = "#!/bin/sh\n" + stripped
    elif not stripped.endswith("\n"):
        stripped += "\n"
    return stripped + block


# Self-contained installer that runs as a subprocess (or `python3 -c
# "..."` inside the devcontainer). Designed to work from either side
# of the bind mount: in the container `git rev-parse --git-path hooks`
# returns the canonical /workspaces/<proj>/.git/hooks and the user can
# write there; on the host the same path may not exist (or `core.hooksPath`
# may have been set to a container path), so we ALWAYS run this inside
# the container from `_setup_test_hooks`. Host-side use is reserved for
# unit tests.
JOLO_POST_COMMIT_INSTALL_SCRIPT = r"""
import fcntl
import re
import subprocess
from pathlib import Path

_BEGIN = "# >>> jolo-perf-start <<<"
_END = "# >>> jolo-perf-end <<<"
_BLOCK = (
    _BEGIN + "\n"
    "# Managed by jolo. Edits inside this block will be overwritten\n"
    "# on the next `jolo up --recreate`. Edit outside the markers.\n"
    "(PERF_RAW=1 just perf >>.jolo-perf.log 2>&1 </dev/null &)\n"
    + _END + "\n"
)
_RE = re.compile(
    r"(?ms)^"
    + re.escape(_BEGIN)
    + r"[ \t]*\r?\n.*?^"
    + re.escape(_END)
    + r"[ \t]*\r?\n?"
)


def _replace(existing: str, block: str) -> str:
    stripped = _RE.sub("", existing)
    if not stripped.startswith("#!"):
        stripped = "#!/bin/sh\n" + stripped
    elif not stripped.endswith("\n"):
        stripped += "\n"
    return stripped + block


result = subprocess.run(
    ["git", "rev-parse", "--git-path", "hooks"],
    capture_output=True,
    text=True,
    check=True,
)
hd = Path(result.stdout.strip())
if not hd.is_absolute():
    hd = Path.cwd() / hd
hd.mkdir(parents=True, exist_ok=True)
hp = hd / "post-commit"
with open(hp, "a+") as f:
    fcntl.flock(f.fileno(), fcntl.LOCK_EX)
    f.seek(0)
    existing = f.read()
    new_text = _replace(existing, _BLOCK)
    if new_text != existing:
        f.seek(0)
        f.truncate()
        f.write(new_text)
if not (hp.stat().st_mode & 0o100):
    hp.chmod(0o755)
"""


def install_jolo_post_commit_hook(project_root: Path) -> None:
    """Run the post-commit installer in ``project_root``.

    For unit tests and standalone host-side use only — the production
    flow runs ``JOLO_POST_COMMIT_INSTALL_SCRIPT`` inside the
    devcontainer (see commands._setup_test_hooks) so paths and
    permissions match the container's view of the bind mount.
    """
    subprocess.run(
        [sys.executable, "-c", JOLO_POST_COMMIT_INSTALL_SCRIPT],
        cwd=project_root,
        check=True,
    )


def sync_template_files(target_dir: Path, force: bool = False) -> None:
    """Sync template files. User-edited files get a .jolonew sibling.

    When force=True, every file in the sync set is overwritten with the
    latest template content (no .jolonew dance) and the touched files
    are git-staged so pre-commit doesn't block the next commit.
    """
    templates_dir = Path(__file__).resolve().parent.parent / "templates"
    if not templates_dir.exists():
        return

    if force:
        print(f"jolo --force: syncing templates into {target_dir}")

    hashes = _load_template_hashes(target_dir)
    touched: list[str] = []

    for filename in SYNCABLE_TEMPLATE_FILES:
        src = templates_dir / filename
        if not src.exists():
            continue
        result = _sync_one_file(
            target_dir, filename, src.read_bytes(), hashes, force=force
        )
        # "unchanged" also refreshes hashes[filename] so a stale record heals.
        if result in {"written", "updated", "unchanged"}:
            touched.append(filename)

    regenerated_common = _regenerated_justfile_common_bytes(
        target_dir, force=force
    )
    if regenerated_common is not None:
        result = _sync_one_file(
            target_dir,
            "justfile.common",
            regenerated_common,
            hashes,
            force=force,
        )
        if result in {"written", "updated", "unchanged"}:
            touched.append("justfile.common")

    regenerated_justfile = _regenerated_justfile_bytes(target_dir, force=force)
    if regenerated_justfile is not None:
        result = _sync_one_file(
            target_dir,
            "justfile",
            regenerated_justfile,
            hashes,
            force=force,
        )
        if result in {"written", "updated", "unchanged"}:
            touched.append("justfile")

    regenerated_rig = _regenerated_perf_rig_bytes(target_dir, force=force)
    if regenerated_rig is not None:
        result = _sync_one_file(
            target_dir,
            "perf-rig.toml",
            regenerated_rig,
            hashes,
            force=force,
        )
        if result in {"written", "updated", "unchanged"}:
            touched.append("perf-rig.toml")

    regenerated_precommit = _regenerated_precommit_config_bytes(target_dir)
    if regenerated_precommit is not None:
        result = _sync_one_file(
            target_dir,
            ".pre-commit-config.yaml",
            regenerated_precommit,
            hashes,
            force=force,
        )
        if result in {"written", "updated", "unchanged"}:
            touched.append(".pre-commit-config.yaml")

    for filename, new_bytes in _regenerated_scaffold_files(
        target_dir, force=force
    ):
        result = _sync_one_file(
            target_dir,
            filename,
            new_bytes,
            hashes,
            force=force,
        )
        if result in {"written", "updated", "unchanged"}:
            touched.append(filename)

    if touched:
        _save_template_hashes(target_dir, touched, hashes)
        if force:
            _stage_touched_files(target_dir, touched)
            print(f"  Touched: {', '.join(touched)}")
    elif force:
        print("  (no template files needed updating)")

    for filename in COPY_IF_MISSING_TEMPLATES:
        src = templates_dir / filename
        dst = target_dir / filename
        if src.exists() and not dst.exists():
            shutil.copy2(src, dst)
            verbose_print(f"Copied (first time): {filename}")


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

    _save_template_hashes(target_dir, SYNCABLE_TEMPLATE_FILES)

    # Copy template directories (skills, agent config, docs)
    template_dirs = [
        ".claude",
        ".codex",
        ".gemini",
        ".pi",
        ".playwright",
        "docs",
        "scripts",
    ]
    for dirname in template_dirs:
        src = templates_dir / dirname
        if src.exists():
            dst = target_dir / dirname
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst, symlinks=True)
            verbose_print(f"Copied template dir: {dirname}/")

    sync_skill_templates(target_dir)


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
    has_web: bool = False,
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
    devcontainer_json = devcontainer_dir / "devcontainer.json"

    if devcontainer_json.exists():
        return False

    devcontainer_dir.mkdir(parents=True, exist_ok=True)

    # Write devcontainer.json (dynamically built based on environment)
    json_content = build_devcontainer_json(
        project_name,
        port=port,
        base_image=config["base_image"],
        remote_user=os.environ.get("USER", "dev"),
        has_web=has_web,
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
    and NOTIFY_APP unless a new one is explicitly provided.
    """
    if target_dir is None:
        target_dir = Path.cwd()
    if config is None:
        config = constants.DEFAULT_CONFIG

    # Preserve existing port if not explicitly overridden
    if port is None:
        port = read_port_from_devcontainer(target_dir)

    # Preserve existing NOTIFY_APP setting
    has_web = False
    devcontainer_json = target_dir / ".devcontainer" / "devcontainer.json"
    if devcontainer_json.exists():
        try:
            existing = json.loads(devcontainer_json.read_text())
            has_web = existing.get("containerEnv", {}).get("NOTIFY_APP") == "1"
        except (json.JSONDecodeError, ValueError):
            pass

    devcontainer_dir = target_dir / ".devcontainer"
    devcontainer_dir.mkdir(parents=True, exist_ok=True)

    # Write devcontainer.json (dynamically built based on environment)
    json_content = build_devcontainer_json(
        project_name,
        port=port,
        base_image=config["base_image"],
        remote_user=os.environ.get("USER", "dev"),
        has_web=has_web,
    )
    (devcontainer_dir / "devcontainer.json").write_text(json_content)

    print("Synced .devcontainer/ with current config")


def _copy_skill_dir(src: Path, dst_root: Path, overwrite: bool) -> None:
    for entry in src.iterdir():
        if not entry.is_dir():
            continue
        dst = dst_root / entry.name
        if dst.exists() and not overwrite:
            continue
        shutil.copytree(entry, dst, symlinks=True, dirs_exist_ok=overwrite)
        verbose_print(f"Synced skill: {entry.name}")


def _host_skill_sources(home: Path) -> list[Path]:
    sources = [home / ".agents" / "skills"]

    codex_plugin_root = home / ".codex" / ".tmp" / "plugins" / "plugins"
    if codex_plugin_root.exists():
        sources.extend(
            plugin / "skills"
            for plugin in codex_plugin_root.iterdir()
            if (plugin / "skills").is_dir()
        )

    claude_plugin_cache = home / ".claude" / "plugins" / "cache"
    if claude_plugin_cache.exists():
        sources.extend(claude_plugin_cache.glob("*/*/*/skills"))

    return sources


def sync_skill_templates(target_dir: Path) -> None:
    """Sync host skills, then overlay repo template skills into .jolo/skills."""
    templates_dir = Path(__file__).resolve().parent.parent / "templates"
    skills_src = templates_dir / "skills"
    skills_dst = target_dir / ".jolo" / "skills"
    skills_dst.mkdir(parents=True, exist_ok=True)

    if skills_src.exists() and skills_dst.resolve() == skills_src.resolve():
        return

    for host_skills in _host_skill_sources(Path.home()):
        if (
            host_skills.exists()
            and host_skills.resolve() != skills_dst.resolve()
        ):
            _copy_skill_dir(host_skills, skills_dst, overwrite=False)

    if skills_src.exists():
        _copy_skill_dir(skills_src, skills_dst, overwrite=True)


def get_secrets(config: dict | None = None) -> dict[str, str]:
    """Get API secrets from pass or environment variables."""
    if config is None:
        config = constants.DEFAULT_CONFIG

    secrets = {}

    # Check if pass is available
    pass_available = shutil.which("pass") is not None

    if pass_available:
        # Try to get secrets from pass using configured paths
        # Values can be a string or list of paths (tried in order, first wins)
        for key, pass_paths in [
            ("ANTHROPIC_API_KEY", config["pass_path_anthropic"]),
            ("OPENAI_API_KEY", config["pass_path_openai"]),
            ("GEMINI_API_KEY", config["pass_path_gemini"]),
        ]:
            if isinstance(pass_paths, str):
                pass_paths = [pass_paths]
            for pass_path in pass_paths:
                try:
                    result = subprocess.run(
                        ["pass", "show", pass_path],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    if result.returncode == 0:
                        secrets[key] = result.stdout.strip()
                        break
                except (subprocess.TimeoutExpired, subprocess.SubprocessError):
                    pass

    # Fallback to environment variables for any missing secrets
    for key in ["ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY"]:
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

    devcontainer_json_path.write_text(json.dumps(content, indent=4) + "\n")


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

    devcontainer_json_path.write_text(json.dumps(content, indent=4) + "\n")


def write_prompt_file(workspace_dir: Path, agent: str, prompt: str) -> None:
    """Write prompt and agent name files for tmux-layout.sh to pick up on start."""
    devcontainer_dir = workspace_dir / ".devcontainer"
    devcontainer_dir.mkdir(parents=True, exist_ok=True)
    (devcontainer_dir / ".agent-prompt").write_text(prompt)
    (devcontainer_dir / ".agent-name").write_text(agent)
