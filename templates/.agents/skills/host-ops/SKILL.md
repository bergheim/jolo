---
name: host-ops
description: Plan and guide host-machine operations that must be run manually outside this devcontainer. Use when the task targets local/remote hosts (not the current workspace container), especially SSH/mosh/tmux/terminal/network setup.
---

# /host-ops

Use this skill when work must happen on real hosts instead of inside this container.

## Host Labels

- `tux` = laptop/client machine
- `berghome` = home/server machine

Always group commands by these labels.

## Rules

1. Do not run host-changing commands from this container.
2. Provide copy-paste commands for `tux`, `berghome`, or `both`.
3. Include verify steps and expected output for each phase.
4. Include rollback steps for anything stateful (services, packages, firewall, config).
5. Keep steps short and linear.

## Output Format

Use this structure:

1. Goal (one sentence)
2. Preconditions
3. Steps
   - `tux` commands
   - `berghome` commands
4. Verify
5. Rollback
6. What to report back (specific command outputs to paste)

## Default Safety

- Prefer reversible changes.
- Prefer scoped exposure (for example Tailscale-only binds/firewall rules).
- Call out privilege level (`sudo` vs user) explicitly.
- If uncertain about host state, ask for command output before the next step.
