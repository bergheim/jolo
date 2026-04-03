---
name: sync-docs
description: Reconcile project docs (MEMORY.org, TODO.org, AGENTS.md) with the current state of the code and recent commits.
---

# /sync-docs

Audit project documentation against the actual codebase and fix drift.

## Instructions

### 1. Determine what changed since docs were last touched

Find the most recent modification time across doc files, then get commits since:

```bash
last_update=$(stat -c %Y docs/MEMORY.org docs/TODO.org docs/RESEARCH.org AGENTS.md 2>/dev/null | sort -rn | head -1)
git log --since="@${last_update}" --oneline
```

If no doc files exist yet, review the last 20 commits instead.

Read the diff for those commits to understand what changed:

```bash
git diff "@{$(date -d @${last_update} '+%Y-%m-%d')}"..HEAD --stat
```

### 2. Reconcile each doc

For each file, check whether the content matches reality:

**`AGENTS.md` / `CLAUDE.md`**:
- Do command examples still work? (check function signatures, CLI flags)
- Are file paths and architecture descriptions accurate?
- Are new tools/features documented?
- Are removed features still mentioned?

**`docs/TODO.org`**:
- Mark completed tasks as `DONE` (check git log for evidence)
- Flag tasks that reference deleted branches or merged PRs
- Add any new tasks discovered from the commits

**`docs/MEMORY.org`**:
- Flag entries that reference renamed/deleted files or functions
- Add patterns or gotchas discovered in recent commits
- Remove entries that are no longer true

**`docs/RESEARCH.org`** (read-only check):
- Flag entries whose referenced files/functions no longer exist
- Do not rewrite research entries — just note staleness

### 3. Apply fixes

Edit the files to fix any drift found. Be surgical — only change what's wrong.

### 4. Commit

Commit all doc changes with: `sync-docs: <brief summary of what was reconciled>`

### 5. Summary

Print what was updated and why, grouped by file.

## Rules

- **Read the code** before changing docs — verify claims against actual files
- **Be conservative** — only fix clear drift, don't rewrite for style
- **Org-mode format** for TODO.org, MEMORY.org, RESEARCH.org
- **No duplicates** — check existing entries before adding
- **Don't invent** — only document what you can verify in the codebase or git history
