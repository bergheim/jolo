# claude-credential-persistence Specification

## Purpose
TBD - created by archiving change claude-credential-mount. Update Purpose after archive.
## Requirements
### Requirement: OAuth token refreshes persist to host

The system SHALL mount `~/.claude/.credentials.json` from the host as a read-write
bind mount so that token refreshes performed by Claude Code inside the container
are written back to the host filesystem.

#### Scenario: Token refresh survives container restart
- **WHEN** Claude Code refreshes the OAuth token during a session, and the container
  is stopped and restarted with `jolo up`
- **THEN** the container starts with the refreshed token (no re-copy of stale credentials)

#### Scenario: Token refresh survives jolo up re-launch
- **WHEN** Claude Code refreshes the OAuth token, the container is stopped, and the
  user runs `jolo up` again
- **THEN** `setup_credential_cache()` does NOT overwrite the host's `.credentials.json`
  and the container mounts the current (refreshed) host file

### Requirement: Cross-project data remains isolated

The system SHALL NOT expose `~/.claude/projects/`, `~/.claude/history.jsonl`, or
`~/.claude/todos/` inside the container. Only the specific files needed for auth
and feature flags SHALL be mounted.

#### Scenario: Container cannot read project memory from other projects
- **WHEN** the container is running
- **THEN** `ls ~/.claude/projects/` inside the container fails or shows empty
  (the directory does not exist in the container's view of `~/.claude/`)

#### Scenario: Container cannot read global history
- **WHEN** the container is running
- **THEN** `~/.claude/history.jsonl` does not exist inside the container

### Requirement: Notification hooks injected into container-local settings

The system SHALL continue to use a copied (not mounted) `settings.json` for Claude
Code's settings inside the container, so that container-specific notification hooks
can be injected without affecting the host's settings.

#### Scenario: Host settings unaffected by container hook injection
- **WHEN** `setup_notification_hooks()` injects `SessionEnd` and `Stop` hooks
- **THEN** the host's `~/.claude/settings.json` is unchanged
- **AND** the container's `~/.claude/settings.json` contains the notification hooks

### Requirement: MCP configs injected into container-local .claude.json

The system SHALL continue to use a copied (not mounted) `.claude.json` so that
container-specific MCP server configs can be injected without affecting the host file.

#### Scenario: Host .claude.json unaffected by MCP injection
- **WHEN** `setup_credential_cache()` injects MCP server configs for `/workspaces/<project>`
- **THEN** the host's `~/.claude.json` is unchanged
- **AND** the container's `~/.claude.json` contains the injected MCP configs

### Requirement: Feature flags available read-only

The system SHALL mount `~/.claude/statsig/` from the host as a read-only bind mount
so Claude Code can read subscription and feature flag data.

#### Scenario: Feature flags readable but not writable
- **WHEN** Claude Code reads feature flags from `~/.claude/statsig/`
- **THEN** the read succeeds with the host's current flag data
- **AND** any write attempt to `~/.claude/statsig/` inside the container fails
  (read-only mount)
