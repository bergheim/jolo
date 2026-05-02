---
name: using-git-worktrees
description: Use when starting feature work that needs isolation from current workspace or before executing implementation plans - creates isolated git worktrees with smart directory selection and safety verification
---

# Using Git Worktrees

## Overview

Git worktrees create isolated workspaces sharing the same repository, allowing work on multiple branches simultaneously without switching.

**Core principle:** Systematic directory selection + safety verification = reliable isolation.

**Higher-level rule:** If the repo already has a native worktree workflow
(`just wt`, project scripts, AGENTS/CLAUDE instructions, tmux/session
integration), use that instead of raw `git worktree add`.

**Announce at start:** "I'm using the using-git-worktrees skill to set up an isolated workspace."

## Workflow Selection Process

Follow this priority order:

### 1. Check For Repo-Native Worktree Commands

Look for project-specific worktree workflows before deciding any path:

```bash
just --list 2>/dev/null | rg '^\s*wt\s' || true
rg -n 'just wt|worktree' AGENTS.md CLAUDE.md README* justfile justfile.common 2>/dev/null || true
```

**If the repo provides a worktree workflow:** use it.

Examples:
- `just wt new <name>`
- project scripts that create worktrees under `/workspaces/...`
- repo docs that explicitly say where worktrees belong

**Why:** native workflows may also create tmux sessions, assign ports,
or enforce cleanup/land conventions. Raw `git worktree add` would bypass
those integrations.

### 2. Check Repo Policy Files

Before picking any fallback directory, read repo instructions:

```bash
rg -n 'worktree' AGENTS.md CLAUDE.md 2>/dev/null || true
```

**If policy says worktrees live under `/workspaces/`:** obey that and do
not use `~/.config/superpowers/worktrees/...`.

**Container rule:** inside devcontainers or similar containerized
workspaces, prefer `/workspaces/...` over `~/.config/...` even when using
the generic fallback. Home-directory paths may disappear on container
recreate.

## Directory Selection Process

Follow this priority order:

### 1. Check Existing Project-Local Directories

```bash
# Check in priority order
ls -d .worktrees 2>/dev/null     # Preferred (hidden)
ls -d worktrees 2>/dev/null      # Alternative
```

**If found:** Use that directory. If both exist, `.worktrees` wins.

### 2. Check Repo Policy For `/workspaces/...` Preference

```bash
rg -n 'worktree|/workspaces/' AGENTS.md CLAUDE.md 2>/dev/null
```

**If `/workspaces/...` is specified:** use a path under `/workspaces/`
without asking.

Suggested generic fallback:

```bash
project=$(basename "$(git rev-parse --show-toplevel)")
path="/workspaces/.worktrees/$project/$BRANCH_NAME"
```

### 3. Choose A Default Non-Interactively

If no directory exists and no repo policy specifies a location, choose a
default without asking:

- If `/workspaces` exists, use `/workspaces/.worktrees/<project-name>/`
- Otherwise use `.worktrees/` and verify it is ignored
- Use `~/.config/superpowers/worktrees/...` only as a last-resort host fallback

## Safety Verification

### For Project-Local Directories (.worktrees or worktrees)

**MUST verify directory is ignored before creating worktree:**

```bash
# Check if directory is ignored (respects local, global, and system gitignore)
git check-ignore -q .worktrees 2>/dev/null || git check-ignore -q worktrees 2>/dev/null
```

**If NOT ignored:**

Per Jesse's rule "Fix broken things immediately":
1. Add appropriate line to .gitignore
2. Commit the change
3. Proceed with worktree creation

**Why critical:** Prevents accidentally committing worktree contents to repository.

### For `/workspaces/...` Fallback Directories

No .gitignore verification needed when the directory is outside the repo.

### For Global Directory (~/.config/superpowers/worktrees)

Use only as a last resort on host systems without a repo-local or
`/workspaces/...` convention. Avoid it inside devcontainers.

## Creation Steps

### 1. Detect Project Name

```bash
repo_root=$(git rev-parse --show-toplevel)
project=$(basename "$(git rev-parse --show-toplevel)")
```

### 2. Prefer Repo-Native Creation

If the repo supports a native command, use it:

```bash
just wt new "$BRANCH_NAME"
```

Then discover the resulting path:

```bash
git worktree list
```

### 3. Generic Create Worktree

```bash
# Choose LOCATION from the earlier discovery steps before entering this branch.
# Determine full path
case $LOCATION in
  .worktrees|worktrees)
    path="$repo_root/$LOCATION/$BRANCH_NAME"
    ;;
  /workspaces/*)
    path="/workspaces/.worktrees/$project/$BRANCH_NAME"
    ;;
  ~/.config/superpowers/worktrees/*)
    path="$HOME/.config/superpowers/worktrees/$project/$BRANCH_NAME"
    ;;
esac

# Create worktree with new branch
git -C "$repo_root" worktree add "$path" -b "$BRANCH_NAME"
cd "$path"
```

### 4. Run Project Setup

Auto-detect and run appropriate setup:

```bash
# Project-native setup first
if [ -f justfile ] && just --list 2>/dev/null | rg '^\s*install\s'; then just install; fi

# Python
if [ -f uv.lock ]; then uv sync; fi
if [ -f package.json ]; then npm install; fi

# Rust
if [ -f Cargo.toml ]; then cargo build; fi

if [ -f requirements.txt ]; then pip install -r requirements.txt; fi
if [ -f pyproject.toml ]; then poetry install; fi

# Go
if [ -f go.mod ]; then go mod download; fi
```

### 5. Verify Clean Baseline

Run tests to ensure worktree starts clean:

```bash
# Examples - use project-appropriate command
npm test
cargo test
pytest
go test ./...
```

**If tests fail:** Report failures, ask whether to proceed or investigate.

**If tests pass:** Report ready.

### 6. Report Location

```
Worktree ready at <full-path>
Tests passing (<N> tests, 0 failures)
Ready to implement <feature-name>
```

## Quick Reference

| Situation | Action |
|-----------|--------|
| Repo has `just wt` or equivalent | Use it instead of raw `git worktree add` |
| AGENTS/CLAUDE says `/workspaces/` | Use `/workspaces/...` |
| `.worktrees/` exists | Use it (verify ignored) |
| `worktrees/` exists | Use it (verify ignored) |
| Both exist | Use `.worktrees/` |
| Neither exists | Check repo policy → choose default automatically |
| Directory not ignored | Add to .gitignore + commit |
| Tests fail during baseline | Report failures + ask |
| No package.json/Cargo.toml | Skip dependency install |

## Common Mistakes

### Skipping ignore verification

- **Problem:** Worktree contents get tracked, pollute git status
- **Fix:** Always use `git check-ignore` before creating project-local worktree

### Assuming directory location

- **Problem:** Creates inconsistency, violates project conventions
- **Fix:** Follow priority: repo-native workflow > repo policy > existing dirs > ask

### Asking the user when a safe default exists

- **Problem:** Conflicts with non-interactive/autonomous agent operation
- **Fix:** Prefer repo-native workflow, then `/workspaces/...`, then `.worktrees/`

### Using `~/.config/superpowers/worktrees` inside a devcontainer

- **Problem:** Worktrees may disappear on container recreate and bypass
  repo-native integrations.
- **Fix:** Prefer `just wt` or `/workspaces/...`

### Proceeding with failing tests

- **Problem:** Can't distinguish new bugs from pre-existing issues
- **Fix:** Report failures, get explicit permission to proceed

### Hardcoding setup commands

- **Problem:** Breaks on projects using different tools
- **Fix:** Auto-detect from project files (package.json, etc.)

## Example Workflow

```
You: I'm using the using-git-worktrees skill to set up an isolated workspace.

[Check .worktrees/ - exists]
[Verify ignored - git check-ignore confirms .worktrees/ is ignored]
[Create worktree: git worktree add .worktrees/auth -b feature/auth]
[Run npm install]
[Run npm test - 47 passing]

Worktree ready at /Users/jesse/myproject/.worktrees/auth
Tests passing (47 tests, 0 failures)
Ready to implement auth feature
```

## Red Flags

**Never:**
- Bypass a repo-native worktree workflow like `just wt`
- Create worktree without verifying it's ignored (project-local)
- Skip baseline test verification
- Proceed with failing tests without asking
- Assume directory location when ambiguous
- Skip AGENTS/CLAUDE repo-policy check

**Always:**
- Prefer repo-native worktree commands when present
- Follow priority: repo-native workflow > repo policy > existing dirs > ask
- Verify directory is ignored for project-local
- Auto-detect and run project setup
- Verify clean test baseline

## Integration

**Called by:**
- **brainstorming** (Phase 4) - REQUIRED when design is approved and implementation follows
- **subagent-driven-development** - REQUIRED before executing any tasks
- **executing-plans** - REQUIRED before executing any tasks
- Any skill needing isolated workspace

**Pairs with:**
- **finishing-a-development-branch** - REQUIRED for cleanup after work complete
