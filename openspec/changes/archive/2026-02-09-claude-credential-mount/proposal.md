## Why

Claude Code refreshes its OAuth token periodically. The current copy-based isolation
(`setup_credential_cache()` copies `~/.claude/` files to `.devcontainer/.claude-cache/`)
means refreshed tokens are written to the copy, not back to the host. Next `jolo up`
re-copies stale host credentials, losing the refresh. Users hit auth failures that
require manual `claude login`.

## What Changes

- **Replace copy-based Claude credential isolation with selective RW mounts** — mount
  only the files Claude Code needs to read/write (`~/.claude/.credentials.json`,
  `~/.claude/statsig/`) directly from the host, so token refreshes persist.
- **Keep settings.json as a copy** — we inject notification hooks into it, so it
  must remain a writable copy that doesn't affect the host's settings.
- **Keep cross-project isolation** — `projects/`, `history.jsonl`, and `todos/`
  must NOT be visible inside the container.
- **Handle `.claude.json` mount** — currently copied and injected with MCP configs.
  Needs to either stay as copy (for MCP injection) or switch to mount with a
  different MCP injection strategy.

## Capabilities

### New Capabilities
- `claude-credential-persistence`: OAuth tokens refreshed inside the container
  persist back to the host, surviving container restarts and `jolo up` re-launches.

### Modified Capabilities
- (none — this is the first spec, no existing specs to modify)

## Impact

- **`_jolo/setup.py`** — `setup_credential_cache()` changes: fewer files copied,
  some replaced with mounts
- **`_jolo/constants.py`** — `BASE_MOUNTS` updated: `.claude-cache` mount replaced
  with selective file/dir mounts to `~/.claude/`
- **`_jolo/setup.py`** — `setup_notification_hooks()` still writes to a local copy
  of `settings.json` (path changes from `.claude-cache/settings.json` to a new
  location for the copied settings)
- **Multi-instance concern** — concurrent containers writing to the same
  `~/.claude/.credentials.json` could race (upstream issue #22600), but this is
  already the case for non-containerized usage
- **No Gemini/Codex changes** — their credential flows don't have this refresh problem
