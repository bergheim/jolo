---
name: j-worktree
description: Create an isolated git worktree in a new tmux window via `just wt new`. Use when the user asks to use, create, spin up, or work in a worktree in a jolo container.
---

# /j-worktree

When the user asks to use / create / spin up a worktree, run the in-container
`wt` manager — it makes the git worktree AND a tmux window in one step. Do NOT
hand-roll `git worktree add` or `tmux new-window`.

The launched `claude` starts CLEAN, but it is a full checkout: it auto-loads
`AGENTS.md`/`CLAUDE.md` and SessionStart hooks, and has `docs/TODO.org`,
`docs/notes/`, and `PROJECT.org` right there. So the task context is already
written up. Don't re-state it in `-p` — the only thing the agent is missing is
WHICH item to work on. Point at it:

```bash
just wt new [name] -p "Work the TODO '<heading>' in docs/TODO.org: read its body
and linked notes, mark it INPROGRESS, then implement."
```

- `-p "..."` is what launches `claude` (`wt` runs `claude <prompt>`). WITHOUT it
  the window is a bare shell and no agent starts — almost never wanted.
- `[name]`: use the name the user gave; if none, omit it and `wt` picks a random
  `adjective-noun` (never invent one).
- `--from <ref>`: base the branch on `<ref>` instead of current HEAD.
- Ad-hoc task not written anywhere? Prefer writing it as a TODO first (project
  rule: TODO.org is the source of truth), then point at it. Only inline the whole
  task in `-p` when it's genuinely one-off and small.

### Context gap to watch

A worktree branches off **committed HEAD**. If the task depends on UNCOMMITTED
changes in the main tree, they are NOT in the worktree. Commit them first (or
`--from` the right ref), or tell the user the worktree won't see them.

Result: worktree at `.worktrees/<name>` on new branch `<name>`, tmux window
`wt-<name>` in the `dev` session with `claude` running. Tell the user the window
name and that `C-b w` (or its number) jumps to it.

## Related wt commands (mention, don't run unprompted)

- `just wt ls` — list worktree windows
- `just wt sync [name]` — rebase the worktree on main's branch
- `just wt land [name] [--rm]` — merge it back into the current branch
- `just wt rm [name]` — remove worktree + branch + window

Worktrees live under `$WORKSPACE/.worktrees/` (bind-mounted, survives container
rebuilds). This is the jolo way — prefer it over `using-git-worktrees` here.
