## Context

Claude Code uses OAuth tokens stored in `~/.claude/.credentials.json`. These tokens
expire and get refreshed during sessions. Currently, `jolo` copies credential files
to `.devcontainer/.claude-cache/` before each launch and bind-mounts that cache
directory as `~/.claude` inside the container. Token refreshes write to the copy,
not the host. Next launch re-copies stale credentials from the host.

The current mount in `BASE_MOUNTS`:
```
source=${localWorkspaceFolder}/.devcontainer/.claude-cache,target=/home/${localEnv:USER}/.claude,type=bind
```

This mounts the *entire directory* as one bind. We also copy `.claude.json` separately
and inject MCP server configs into it.

## Goals / Non-Goals

**Goals:**
- Token refreshes inside the container persist to the host's `~/.claude/.credentials.json`
- Notification hooks still get injected into a container-local copy of `settings.json`
- `projects/`, `history.jsonl`, `todos/` remain invisible to containers
- MCP server injection into `.claude.json` continues to work
- No changes to Gemini or Codex credential handling

**Non-Goals:**
- Solving the multi-instance race condition (upstream #22600)
- Mounting `~/.claude` fully read-write (too broad, leaks cross-project data)
- Changing the Gemini/Codex credential flow

## Decisions

### 1. Selective file mounts instead of directory mount

**Choice:** Replace the single `.claude-cache` directory mount with individual file/directory mounts.

**Rationale:** A directory mount is all-or-nothing — either the container sees everything in `~/.claude/` or nothing. Individual file mounts let us expose only `.credentials.json` (RW) and `statsig/` (RO) while keeping `projects/`, `history.jsonl`, `todos/` invisible.

**Alternative considered:** Mount `~/.claude` RW with symlink tricks to hide `projects/`. Too fragile — new files Claude Code creates would land on the host.

### 2. Keep `settings.json` as a copy

**Choice:** Continue copying `settings.json` to `.claude-cache/` and mounting it from there.

**Rationale:** We inject `SessionEnd`, `Stop`, and `UserPromptSubmit` hooks into
`settings.json` via `setup_notification_hooks()`. These are container-specific (they
reference `notify-done` which only exists in the container). Writing these to the
host's `settings.json` would break host-side Claude Code.

### 3. Keep `.claude.json` as a copy

**Choice:** Continue the copy+inject pattern for `.claude.json`.

**Rationale:** We inject project-specific MCP server configs keyed by
`/workspaces/<project>`. These are container paths that don't exist on the host.
Mounting RW would pollute the host's `.claude.json` with container-specific entries.

### 4. Mount `.credentials.json` as a single-file bind mount

**Choice:** `source=${localEnv:HOME}/.claude/.credentials.json,target=.../.claude/.credentials.json,type=bind`

**Rationale:** Single-file bind mounts work in Podman and survive file rewrites
*if* the application writes in-place (not atomic rename). Claude Code uses
`fs.writeFileSync` which writes in-place, so this works. If they switch to
atomic rename in the future, the mount would break — but that's a bridge we
cross when we get to it.

**Alternative considered:** Mount parent dir RO + overlay just the credentials file
RW. Overcomplicated for no benefit.

## Risks / Trade-offs

- **[Single-file mount brittleness]** → If Claude Code switches to atomic rename
  (write temp + rename), the bind mount breaks. Mitigation: monitor upstream,
  this is the standard pattern for `/etc/resolv.conf` etc. in containers.

- **[Multi-instance token races]** → Two containers refreshing tokens simultaneously
  could clobber each other's writes. Mitigation: not our problem to solve — same
  issue exists with multiple Claude Code instances outside containers (upstream #22600).

- **[statsig mount]** → Mounting `statsig/` read-only means the container can't
  update feature flags. This is fine — the host's Claude Code updates them, and
  the container reads stale-but-functional flags. Worse case: a flag check fails
  and falls back to default behavior.
