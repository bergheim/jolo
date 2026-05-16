---
name: j-resume
description: Write a paste-back resume note for the next session, especially before container recreate, image rebuild, or any context handoff.
---

# /j-resume

Produce a paste-back-ready note at `scratch/resume-session.md` so the next
session bootstraps with current state intact.

This is the ephemeral-handoff complement to `/j-save-state` (which persists
durable knowledge to denote notes and TODO.org). Use both when ending a
session with shippable work; use `/j-resume` alone when there's nothing
denote-worthy but state-of-play matters for the next bootstrap.

## Arguments

- `[focus]` — optional phrase emphasizing what to highlight ("rebuild prep",
  "post-PR", "before mosh restart"). Without focus, summarize the whole
  session.

## Instructions

### 1. Read the prior resume note

`scratch/resume-session.md` may already exist. Read it. Items under
**Still outstanding** / **parked** should usually carry forward verbatim
unless this session resolved them. The prior note is your starting point;
update, don't restart.

### 2. Gather current state

- `git status` and `git diff --stat` — what's uncommitted
- `git log --oneline -n 5` — what shipped this session
- TODO.org top items connected to the recent work (`rg -n "^\*+ (TODO|NEXT|INPROGRESS)" docs/TODO.org | head -10`)
- Anything you specifically verified working this session — envs, processes,
  ports, sockets, services. These become the verify commands in step 3.

### 3. Write the note

Overwrite `scratch/resume-session.md` with these sections:

- **Header** — one line: "Resuming. State at end of last session
  (YYYY-MM-DD)" with today's date.
- **Branch / commit context** — current branch, clean or dirty, what's
  uncommitted, recent shipped commits (short hashes + subjects).
- **What changed this session** — short bullets per change, each with WHY,
  not what.
- **Re-verify after [handoff event] (one batch)** — concrete shell
  commands to re-confirm the things you specifically verified.
  Copy-paste block. Include expected output where useful.
- **Still outstanding (parked, do NOT redo)** — items not addressed this
  session but worth knowing. Carry forward from prior resume note plus
  anything new discovered. Strike items resolved this session.
- **Don't** — rabbit holes / tangents to avoid without explicit go-ahead.
  Carry forward from prior note plus anything new this session warned off.

Format: markdown. Tight prose, focused bulleting where it helps.

### 4. Print confirmation

After writing, output:

```
Resume note saved to scratch/resume-session.md — paste this into the next session.
```

Nothing else.

## Rules

- **Read-only on the repo** except for `scratch/resume-session.md`. No
  commits, no docs/ edits, no TODO.org changes. That's `/j-save-state`'s
  job.
- **Don't duplicate save-state.** If durable knowledge surfaced this
  session, suggest the user run `/j-save-state` alongside — but don't run
  it yourself unless asked.
- **Carry forward parked items verbatim** unless this session resolved
  them. Future-you needs the same warnings that current-you was given.
- **Concrete verify commands.** Vague "make sure X works" is useless —
  paste the actual command. If you didn't verify it this session, don't
  put it in the verify block.
- **Date format:** use today's actual date (check `date +%Y-%m-%d` if
  unsure), not a relative phrase.
- **No fluff.** This file is read once and discarded. Keep it under
  ~80 lines.
