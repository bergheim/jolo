## Why

`jolo research "topic"` requires being inside a git repo and creates ephemeral worktrees
with their own containers. This is overcomplicated — research is a standalone activity
unrelated to the current project. Running it from `~/dev/playground` fails with
"Not in a git repository."

Users want to fire off research from anywhere, have multiple concurrent tasks, and
get results as org files they can browse later.

## What Changes

- **Replace worktree-based isolation with a single persistent research repo** at
  `~/jolo/research/` (configurable). Created automatically on first use.
- **Replace per-task containers with a persistent container** — `devcontainer up`
  once, then `devcontainer exec` for each research task. Container stays running.
- **Each research task writes to its own file** — `YYYY-MM-DD-slug.org` with the
  original prompt at the top. Agent commits directly to main.
- **Delete all worktree/watcher machinery** — no `_spawn_research_watcher()`, no
  `.research-mode` flag, no research mode in `tmux-layout.sh`.

## Capabilities

### New Capabilities
- `standalone-research`: Run `jolo research "topic"` from any directory without
  being in a git repo. Results accumulate in `~/jolo/research/` as dated org files.

### Modified Capabilities
- `research-command`: Simplified from worktree+container+watcher to exec-into-persistent-container.

## Impact

- **`_jolo/commands.py`** — rewrite `run_research_mode()`, delete `_spawn_research_watcher()`,
  add `ensure_research_repo()`
- **`_jolo/cli.py`** — add `slugify_prompt()` helper
- **`_jolo/constants.py`** — add `research_home` to `DEFAULT_CONFIG`
- **`container/tmux-layout.sh`** — delete research mode block (lines 29-51)
- **`templates/.agents/skills/research/SKILL.md`** — support per-file output with prompt
- **`tests/test_research.py`** — rewrite for new behavior
