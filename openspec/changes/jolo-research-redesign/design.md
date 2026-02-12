## Context

Current `run_research_mode()` calls `validate_tree_mode()` (requires git repo), creates
a worktree, starts a new container per task, wraps the agent with `kill 1` for auto-stop,
and spawns a background watcher to clean up the worktree. This is ~100 lines of complex
shell escaping and process management.

The new design: one persistent repo, one persistent container, fire-and-forget exec.

## Goals / Non-Goals

**Goals:**
- Works from any directory (no git repo required)
- Multiple concurrent research tasks (each writes its own file)
- Prompt saved in the output file
- ntfy notification on completion (via existing agent hooks)
- Auto-creates research repo on first use

**Non-Goals:**
- Custom devcontainer config for the research repo (standard scaffold is fine)
- Worktree isolation between tasks (unnecessary — different files, no conflicts)
- Container auto-stop (stays running for reuse)

## Decisions

### 1. Single persistent container, exec per task

**Choice:** Start container once with `devcontainer up`, then `devcontainer exec` each
agent command backgrounded with `nohup ... &`.

**Rationale:** Avoids container startup overhead for each research task. Supports
concurrency naturally — multiple backgrounded execs in the same container, each writing
different files.

**Alternative considered:** New container per task (current approach). Rejected — slow
startup, no concurrency, requires worktrees for isolation.

### 2. Agent runs in `-p` (print) mode

**Choice:** `agent -p "/research ..."` for non-interactive fire-and-forget execution.

**Rationale:** Print mode runs the prompt, executes any skills (including `/research`),
and exits. No tmux window needed. The agent's session-end hook fires ntfy.

### 3. Minimal research repo scaffold

**Choice:** `ensure_research_repo()` creates only: git repo + `.devcontainer/` +
`.agents/skills/research/` (the research skill).

**Rationale:** The research repo is just a collection of org files. No justfile, no
AGENTS.md, no docs/ directory. Keep it minimal.

### 4. Filename generation on the host

**Choice:** Host generates `YYYY-MM-DD-slug.org` and passes it in the prompt. Agent
writes to that file.

**Rationale:** Deterministic naming, no coordination needed. User sees the filename
immediately in the confirmation message.

## Risks / Trade-offs

- **[`-p` mode + slash commands]** — `/research` must work in print mode. If an agent
  doesn't support slash commands in print mode, the skill won't trigger. Mitigation:
  Claude and Gemini both support this; test on first use.

- **[Concurrent git commits]** — Two agents finishing simultaneously could get a commit
  conflict on HEAD. Mitigation: different files means `git add + commit` rarely races,
  and agents retry on failure as part of their git hygiene.

- **[Container stays running]** — The research container persists until manually stopped.
  Mitigation: acceptable — it's one container, and `jolo prune` can clean it up.
