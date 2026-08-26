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

from . import constants
from .cli import (
    detect_flavors,
    get_container_name,
    read_port_from_devcontainer,
    verbose_print,
)
from .container import build_devcontainer_json

DEFAULT_CODEX_REASONING_EFFORT = "high"

# The image ships pnpm only (npm is shimmed to fail), so point pi's package
# installer at pnpm — otherwise `pi install` and startup auto-install both die.
PI_NPM_COMMAND = ["pnpm"]


def write_json(
    path: Path, obj, indent: int | str = 2, newline: bool = True
) -> None:
    """Write `obj` as JSON to `path`. Defaults match most call sites:
    2-space indent with a trailing newline. Override per site as needed."""
    text = json.dumps(obj, indent=indent)
    path.write_text(text + "\n" if newline else text)


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
    (elpaca, tree-sitter) are in ~/.cache/jolo/ on the host,
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
    container_cache = home / ".cache" / "jolo"
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


def _upsert_toml_table_keys(
    content: str, table: str, updates: dict[str, str]
) -> str:
    """Set string keys in [table], creating the table if needed."""
    lines = content.splitlines()
    header = f"[{table}]"
    try:
        start = next(i for i, ln in enumerate(lines) if ln.strip() == header)
    except StopIteration:
        block = [header] + [f'{k} = "{v}"' for k, v in updates.items()]
        body = content.rstrip()
        prefix = f"{body}\n\n" if body else ""
        return prefix + "\n".join(block) + "\n"

    end = start + 1
    while end < len(lines) and not lines[end].strip().startswith("["):
        end += 1
    remaining = dict(updates)
    new_section = []
    for ln in lines[start + 1 : end]:
        m = re.match(r"^\s*([A-Za-z0-9_]+)\s*=", ln)
        if m and m.group(1) in remaining:
            new_section.append(f'{m.group(1)} = "{remaining.pop(m.group(1))}"')
        else:
            new_section.append(ln)
    new_section.extend(f'{k} = "{v}"' for k, v in remaining.items())
    return "\n".join(lines[: start + 1] + new_section + lines[end:]) + "\n"


def _write_if_changed(path: Path, content: str) -> None:
    """Write only on a real change. ~/.grok and ~/.codex are host-owned and
    shared across every project, so a no-op rewrite is churn on the host."""
    if not path.exists() or path.read_text() != content:
        path.write_text(content)


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

    Claude: ~/.claude and ~/.claude.json are mounted whole from the host;
    jolo copies nothing and only creates bind sources. Notification hooks go
    to project-level .claude/settings.json (see setup_notification_hooks).
    Gemini/Codex: fully copied to .devcontainer cache dirs.
    Pi: ~/.pi is mounted directly from the host; jolo writes nothing there.
    """
    home = Path.home()
    templates_dir = Path(__file__).resolve().parent.parent / "templates"
    mcp_templates = templates_dir / "mcp"

    # Claude: ~/.claude and ~/.claude.json are bound whole from the host, so
    # nothing is copied and no host-absolute path is rewritten. Only create
    # the bind sources; podman fails the rebuild if they are absent.
    claude_dir = home / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    # The per-project shadows below nest inside that dir bind, so their
    # targets must exist on the host too. Podman creates a missing target as
    # a directory, which would be fatal for the history file.
    (claude_dir / "sessions").mkdir(exist_ok=True)
    (claude_dir / "history.jsonl").touch(exist_ok=True)

    devcontainer_dir = workspace_dir / ".devcontainer"
    devcontainer_dir.mkdir(parents=True, exist_ok=True)
    # Per-project shadows over the shared dir. sessions/ is the peer registry,
    # reaped by local PID liveness, so sharing it would have each container
    # collect the others' live records. history.jsonl is one flat file.
    (devcontainer_dir / ".claude-sessions").mkdir(exist_ok=True)
    (devcontainer_dir / ".claude-history.jsonl").touch(exist_ok=True)

    # MCP servers and the trust flag go straight into the host file, keyed by
    # the container path, so they do not touch any host project's entry.
    # caveman is mounted whole from the host so its binaries resolve at the
    # same absolute path agents' hooks were written with. Only the directory
    # is guaranteed; a host without caveman gets an empty one and the hooks
    # degrade instead of failing the rebuild.
    (home / ".caveman").mkdir(parents=True, exist_ok=True)
    (home / ".caveman-cloud").mkdir(parents=True, exist_ok=True)
    (home / ".agents" / "skills").mkdir(parents=True, exist_ok=True)
    # Bind source; empty until the host fills in service URLs.
    (home / ".profile.container").touch(exist_ok=True)

    # Bind source must exist or podman statfs fails the rebuild on a host
    # that has never run Claude.
    claude_json = home / ".claude.json"
    if not claude_json.exists():
        claude_json.write_text("{}")

    try:
        claude_config = json.loads(claude_json.read_text())
        container_path = f"/workspaces/{workspace_dir.name}"

        claude_config["effortCalloutV2Dismissed"] = True

        project_entry = claude_config.setdefault("projects", {}).setdefault(
            container_path, {}
        )
        project_entry["hasTrustDialogAccepted"] = True
        merge_mcp_configs(project_entry, mcp_templates)

        write_json(claude_json, claude_config, newline=False)
    except Exception as e:
        print(
            f"Warning: Failed to inject MCP configs into .claude.json: {e}",
            file=sys.stderr,
        )

    # Gemini credentials
    gemini_cache = workspace_dir / ".devcontainer" / ".gemini-cache"

    # OAuth tokens that must survive cache rebuilds across containers. The host
    # keeps these in the Secret Service keyring (no file), so containers
    # file-fall-back and the live token only exists in this project's cache.
    # Round-trip each through a shared host store: write back any token a
    # container refreshed (before we wipe the cache), then re-seed below.
    jolo_store = home / ".config" / "jolo"
    agy_dir = gemini_cache / "antigravity-cli"
    persistent_creds = [
        (
            gemini_cache / "gemini-credentials.json",
            jolo_store / "gemini-credentials.json",
        ),
        (
            agy_dir / "antigravity-oauth-token",
            jolo_store / "antigravity-oauth-token",
        ),
    ]
    jolo_store.mkdir(parents=True, exist_ok=True)
    for cache_token, store_token in persistent_creds:
        if cache_token.exists() and (
            not store_token.exists()
            or cache_token.stat().st_mtime > store_token.stat().st_mtime
        ):
            shutil.copy2(cache_token, store_token)

    if gemini_cache.exists():
        clear_directory_contents(gemini_cache)
    else:
        gemini_cache.mkdir(parents=True)
    agy_dir.mkdir(parents=True, exist_ok=True)

    gemini_dir = home / ".gemini"
    for filename in [
        "settings.json",
        "google_accounts.json",
        "gemini-credentials.json",
    ]:
        src = gemini_dir / filename
        if src.exists():
            shutil.copy2(src, gemini_cache / filename)

    # Seed from the shared store last so it wins over any stale host file
    # (the store is the authoritative cross-container copy).
    for cache_token, store_token in persistent_creds:
        if store_token.exists():
            shutil.copy2(store_token, cache_token)

    # Bake agy (Antigravity CLI) first-run defaults so a fresh container never
    # prompts: light theme, telemetry off (forced — we say no), and onboarding
    # marked done. agy gates the prompts on cache/onboarding.json, NOT on
    # settings.json, so both files are required. agy ignores gemini's
    # trustedFolders.json; workspace trust lives in trustedWorkspaces here.
    write_json(
        agy_dir / "settings.json",
        {
            "colorScheme": "light",
            "enableTelemetry": False,
            "trustedWorkspaces": [
                f"/workspaces/{workspace_dir.name}",
                "/workspaces/stash",
            ],
        },
        newline=False,
    )
    (agy_dir / "cache").mkdir(exist_ok=True)
    write_json(
        agy_dir / "cache" / "onboarding.json",
        {
            "consumerOnboardingComplete": True,
            "enterpriseOnboardingComplete": False,
            "onboardingComplete": True,
        },
        newline=False,
    )

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

    write_json(settings_path, settings, indent="\t", newline=False)

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
        _write_if_changed(
            codex_config_path,
            _upsert_toml_table_keys(
                codex_config_path.read_text(),
                f'projects."/workspaces/{workspace_dir.name}"',
                {"trust_level": "trusted"},
            ),
        )

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

    # Pi config is the host's, mounted directly into every container — no cache
    # copy, so an OAuth login or `pi install` done inside a container persists
    # and is live everywhere. Sessions are mounted per-project over the top.
    # Both ends of that nested mount must exist first, or podman aborts the run:
    # the per-project source, and the target inside the now-shared ~/.pi.
    pi_home = home / ".pi"
    (pi_home / "agent" / "sessions").mkdir(parents=True, exist_ok=True)
    (workspace_dir / ".devcontainer" / ".pi-sessions").mkdir(
        parents=True, exist_ok=True
    )

    # grok follows the same rule as pi: shared host config, per-project sessions
    # and worktrees nested over it. Same both-ends-must-exist constraint.
    grok_home = home / ".grok"
    for nested in ("sessions", "worktrees"):
        (grok_home / nested).mkdir(parents=True, exist_ok=True)
        (workspace_dir / ".devcontainer" / f".grok-{nested}").mkdir(
            parents=True, exist_ok=True
        )
    # Native grok worktrees are standalone clones under ~/.grok — magit cannot
    # switch to them. Force /new and /fork onto just wt (.worktrees/).
    grok_config = grok_home / "config.toml"
    _write_if_changed(
        grok_config,
        _upsert_toml_table_keys(
            grok_config.read_text() if grok_config.exists() else "",
            "hints",
            {
                "new_session_worktree_mode": "never",
                "fork_worktree_mode": "never",
            },
        ),
    )

    _write_pi_project_settings(workspace_dir)


def _write_pi_project_settings(workspace_dir: Path) -> None:
    """Pin pnpm for this workspace only.

    The image shims npm to fail, so pi's installer needs pnpm — but ~/.pi is
    shared with the host, where npm is fine. Project settings override global
    per-key; the workspace's pi trust is host config, not jolo's concern.
    """
    settings_path = workspace_dir / ".pi" / "settings.json"
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings = _load_json_safe(settings_path)
    settings["npmCommand"] = PI_NPM_COMMAND
    write_json(settings_path, settings)


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
    """Inject agent completion notification hooks.

    Adds hooks that call notify when agents finish.
    Merges with existing hooks (does not overwrite).
    Claude hooks go to the project's .claude/settings.json, since ~/.claude is
    shared with the host and `notify` is container-only. Gemini still uses its
    .devcontainer cache, so this must run after setup_credential_cache().
    """
    # Claude: project-level settings, not the user-level file. ~/.claude is
    # shared with the host now, and `notify` only exists inside the container,
    # so a hook there would fail on every host turn. Claude merges project
    # settings over user settings, so this lands the same either way.
    claude_settings_path = workspace_dir / ".claude" / "settings.json"
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
    write_json(claude_settings_path, settings, newline=False)

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
    write_json(gemini_settings_path, settings, indent="\t", newline=False)

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
    ".gitignore",
    ".editorconfig",
    "biome.json",
    "docs/agent-ops.md",
]

# The string jolo used to hardcode as postStartCommand. On sync, an
# existing devcontainer.json carrying *exactly* this value is treated as
# stale plumbing and dropped — the symlink lives in entrypoint.sh now.
# Any other value (including the old default with extra suffix like
# "&& scripts/pg-init") is preserved verbatim.
_OLD_CANONICAL_POST_START_COMMAND = (
    "ln -sfn $HOME/.agents/skills $HOME/.claude/skills"
)


# Files that sync should drop in if missing but never overwrite if present.
# Currently empty — perf-rig.toml graduated to strictly-owned sync so
# `--force` can actually retrofit placeholder renames and the like.
# User tuning (scenarios, thresholds) is recovered via `.jolonew` on a
# no-force sync of an edited file, or from git when they --force.
COPY_IF_MISSING_TEMPLATES: list[str] = []


def _is_meta_project(target_dir: Path) -> bool:
    return detect_flavors(target_dir) == ["meta"]


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
    write_json(path, hashes)


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
    from .templates import get_justfile_common_content

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
    from .templates import get_justfile_content

    flavor = _resolve_flavor(target_dir, force)
    if flavor is None:
        return None
    return get_justfile_content(flavor, target_dir.name).encode()


def _regenerated_perf_rig_bytes(
    target_dir: Path, force: bool = False
) -> bytes | None:
    """Return current ``perf-rig.toml`` bytes for this project, or ``None``
    if flavor cannot be resolved or the flavor opts out of shared recipes."""
    from .templates import get_perf_rig_content

    flavor = _resolve_flavor(target_dir, force)
    if flavor is None:
        return None
    if flavor in _NO_SHARED_RECIPES_FLAVORS:
        return None
    return get_perf_rig_content(flavor, target_dir.name).encode()


def _regenerated_envrc_bytes(
    target_dir: Path, force: bool = False
) -> bytes | None:
    """Return current ``.envrc`` bytes for web projects, or ``None``."""
    from .templates import get_envrc_content

    flavor = _resolve_flavor(target_dir, force)
    if flavor is None:
        return None
    content = get_envrc_content(flavor)
    if not content:
        return None
    return content.encode()


def _regenerated_precommit_config_bytes(target_dir: Path) -> bytes | None:
    """Return current ``.pre-commit-config.yaml`` bytes for this project."""
    from .templates import generate_precommit_config

    flavors = detect_flavors(target_dir)
    return generate_precommit_config(flavors).encode()


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
    syncable_template_files = (
        [] if _is_meta_project(target_dir) else SYNCABLE_TEMPLATE_FILES
    )

    for filename in syncable_template_files:
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

    regenerated_envrc = _regenerated_envrc_bytes(target_dir, force=force)
    if regenerated_envrc is not None:
        result = _sync_one_file(
            target_dir,
            ".envrc",
            regenerated_envrc,
            hashes,
            force=force,
        )
        if result in {"written", "updated", "unchanged"}:
            touched.append(".envrc")

    regenerated_precommit = (
        None
        if _is_meta_project(target_dir)
        else _regenerated_precommit_config_bytes(target_dir)
    )
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
    from the templates/ directory, plus docs/ directory.

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
        "biome.json",
    ]

    for filename in template_files:
        src = templates_dir / filename
        if src.exists():
            dst = target_dir / filename
            shutil.copy2(src, dst)
            verbose_print(f"Copied template: {filename}")

    # Copy template directories (agent config, docs).
    # `scripts/` is intentionally excluded — callers use
    # `ensure_test_gate_script()` and `ensure_lighthouse_run_script()`
    # so per-script gating (e.g. lighthouse only for web flavors)
    # works in create mode.
    template_dirs = [
        ".claude",
        ".codex",
        ".gemini",
        ".pi",
        ".playwright",
        "docs",
    ]
    for dirname in template_dirs:
        src = templates_dir / dirname
        if src.exists():
            dst = target_dir / dirname
            if dst.exists():
                shutil.rmtree(dst)
            shutil.copytree(src, dst, symlinks=True)
            verbose_print(f"Copied template dir: {dirname}/")

    _save_template_hashes(target_dir, SYNCABLE_TEMPLATE_FILES)


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


def ensure_lighthouse_run_script(target_dir: Path, flavor: str) -> None:
    """Ensure scripts/lighthouse-run exists for web-flavor projects."""
    if not flavor.endswith("-web"):
        return

    templates_dir = Path(__file__).resolve().parent.parent / "templates"
    src = templates_dir / "scripts" / "lighthouse-run"
    if not src.exists():
        print(
            f"Warning: lighthouse-run template not found: {src}",
            file=sys.stderr,
        )
        return

    dst = target_dir / "scripts" / "lighthouse-run"
    if dst.exists():
        return

    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    verbose_print("Copied template: scripts/lighthouse-run")


def scaffold_devcontainer(
    project_name: str,
    target_dir: Path | None = None,
    config: dict | None = None,
    port: int | None = None,
    has_web: bool = False,
    cross_container: bool = False,
) -> bool:
    """Create .devcontainer directory with templates.

    Returns True if created, False if already exists.
    Port is randomly assigned in 4000-5000 if not specified.
    """
    if target_dir is None:
        target_dir = Path.cwd()
    if config is None:
        config = constants.DEFAULT_CONFIG
    assert config is not None

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
        cross_container=cross_container,
        container_name=get_container_name(str(target_dir)),
    )
    (devcontainer_dir / "devcontainer.json").write_text(json_content)

    return True


def sync_devcontainer(
    project_name: str,
    target_dir: Path | None = None,
    config: dict | None = None,
    port: int | None = None,
    cross_container: bool = False,
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
    assert config is not None

    # Preserve existing port if not explicitly overridden
    if port is None:
        port = read_port_from_devcontainer(target_dir)

    # Preserve existing NOTIFY_APP and postStartCommand settings.
    # postStartCommand is user-owned (e.g. demokrate's scripts/pg-init);
    # the skills symlink is baked into the image now. Projects
    # that still have the exact old canonical default get cleaned up so
    # ownership of the key really is 100% the user's.
    has_web = False
    post_start_command: str | None = None
    devcontainer_json = target_dir / ".devcontainer" / "devcontainer.json"
    if devcontainer_json.exists():
        try:
            existing = json.loads(devcontainer_json.read_text())
            has_web = existing.get("containerEnv", {}).get("NOTIFY_APP") == "1"
            existing_post_start = existing.get("postStartCommand")
            if existing_post_start != _OLD_CANONICAL_POST_START_COMMAND:
                post_start_command = existing_post_start
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
        cross_container=cross_container,
        post_start_command=post_start_command,
        container_name=get_container_name(str(target_dir)),
    )
    (devcontainer_dir / "devcontainer.json").write_text(json_content)

    print("Synced .devcontainer/ with current config")


def get_secrets(config: dict | None = None) -> dict[str, str]:
    """Get API secrets from pass or environment variables."""
    if config is None:
        config = constants.DEFAULT_CONFIG
    assert config is not None

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

    # LiteLLM master key — host-side only, used to mint per-project virtual keys.
    # Never injected into a container.
    if "LITELLM_MASTER_KEY" not in secrets:
        master = ""
        if pass_available:
            try:
                result = subprocess.run(
                    ["pass", "show", config["pass_path_litellm_master"]],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    master = result.stdout.strip()
            except (subprocess.TimeoutExpired, subprocess.SubprocessError):
                pass
        secrets["LITELLM_MASTER_KEY"] = master or os.environ.get(
            "LITELLM_MASTER_KEY", ""
        )

    # Shared Crawl4AI bearer token, injected into containers via containerEnv.
    if "CRAWL4AI_API_TOKEN" not in secrets:
        token = ""
        if pass_available:
            try:
                result = subprocess.run(
                    ["pass", "show", config["pass_path_crawl4ai"]],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    token = result.stdout.strip()
            except (subprocess.TimeoutExpired, subprocess.SubprocessError):
                pass
        secrets["CRAWL4AI_API_TOKEN"] = token or os.environ.get(
            "CRAWL4AI_API_TOKEN", ""
        )

    return secrets


def _litellm_key_store_path() -> Path:
    return Path.home() / ".config" / "jolo" / "litellm-keys.json"


def _load_litellm_key_store() -> dict:
    return _load_json_safe(_litellm_key_store_path())


def _save_litellm_key_store(store: dict) -> None:
    path = _litellm_key_store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(store, indent=2) + "\n")
    # Holds live virtual keys — keep it owner-only.
    path.chmod(0o600)


def _litellm_generate_key(
    base_url: str, master_key: str, project_name: str, config: dict
) -> str | None:
    body = {
        "key_alias": f"jolo-{project_name}",
        "max_budget": config.get("litellm_key_max_budget"),
        "budget_duration": config.get("litellm_key_budget_duration"),
        "metadata": {"project": project_name, "source": "jolo"},
    }
    models = config.get("litellm_key_models") or []
    if models:
        body["models"] = models
    req = urllib.request.Request(
        base_url.rstrip("/") + "/key/generate",
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {master_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
    except (
        OSError,
        TimeoutError,
        urllib.error.URLError,
        json.JSONDecodeError,
    ) as e:
        print(
            f"Warning: LiteLLM key mint failed for {project_name}: {e}",
            file=sys.stderr,
        )
        return None
    key = data.get("key")
    return key if isinstance(key, str) and key else None


def ensure_litellm_project_key(
    project_name: str, cfg: dict | None = None
) -> str | None:
    """Return the project's LiteLLM virtual key, minting + caching it once.

    LiteLLM only reveals a key's secret at creation, so jolo caches it per
    project in ~/.config/jolo/litellm-keys.json and reuses it across launches
    and worktrees (stable keys keep spend attribution clean). Returns None
    (graceful) if the gateway base URL or master key is absent, or if minting
    fails — the caller then launches without a cloud key.
    """
    config = cfg or constants.DEFAULT_CONFIG
    base_url = config.get("litellm_base_url")
    master_key = os.environ.get("LITELLM_MASTER_KEY")
    if not base_url or not master_key:
        return None
    store = _load_litellm_key_store()
    existing = store.get(project_name)
    if isinstance(existing, str) and existing:
        return existing
    key = _litellm_generate_key(base_url, master_key, project_name, config)
    if key:
        store[project_name] = key
        _save_litellm_key_store(store)
    return key


def litellm_gateway_reachable(base_url: str) -> bool:
    """True if the LiteLLM gateway answers its liveness probe."""
    if not base_url:
        return False
    url = base_url.rstrip("/") + "/health/liveliness"
    try:
        with urllib.request.urlopen(url, timeout=3):
            return True
    except (OSError, TimeoutError, urllib.error.URLError):
        return False


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

    write_json(devcontainer_json_path, content, indent=4)


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

    write_json(devcontainer_json_path, content, indent=4)


def write_prompt_file(workspace_dir: Path, agent: str, prompt: str) -> None:
    """Write prompt and agent name files for tmux-layout.sh to pick up on start."""
    devcontainer_dir = workspace_dir / ".devcontainer"
    devcontainer_dir.mkdir(parents=True, exist_ok=True)
    (devcontainer_dir / ".agent-prompt").write_text(prompt)
    (devcontainer_dir / ".agent-name").write_text(agent)
