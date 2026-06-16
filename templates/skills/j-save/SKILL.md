---
name: j-save
description: Save current session knowledge to shared project files and agent-private memory. Add the `resume` keyword to also write a paste-back handoff note for the next session.
---

# /j-save

Persist what you've learned this session so it survives context loss and is
available to all agents. The end-of-session complement to `/j-resume` (which
reads state back at the start of the next session).

## Arguments

`/j-save [resume] [focus]`

- `resume` — optional leading keyword. When present, also write the ephemeral
  handoff note `scratch/resume-session.md` so the next session can hit the
  ground running (see step 5). Without it, save durable knowledge only.
- `[focus]` — optional keyword(s) or short phrase describing what to save
  around (e.g. `perf`, `grafana dashboards`, `jolo skills`, `public notes`).
  When given, bias note creation, TODO updates, commit message, the handoff
  note, and the summary toward that topic. Anything after a leading `resume`
  is treated as focus.

Without arguments, save broadly as before.

## Instructions

### 1. Create denote notes for discoveries

For each significant discovery, convention, gotcha, decision, or investigation from
this session, create a denote note in `docs/notes/`:

```bash
emacsclient -e '(bergheim/agent-denote-create "docs/notes" "Title" (quote ("kind" "topic1" "topic2")) "Body text.")'
```

**Choose the right kind** (first keyword):
- `memory` — convention, pattern, how something works
- `research` — investigation, root cause analysis, benchmarks
- `decision` — architectural choice with rationale
- `gotcha` — trap that will bite someone again
- `convention` — coding standard, naming rule, process agreement
- `incident` — what broke, why, how it was fixed

If the emacsclient helper isn't available, create the file directly following
denote naming: `YYYYMMDDTHHMMSS--title-slug__kind_topic.org` with front matter:

```org
#+title:      Title here
#+date:       [2026-04-16 Thu 12:00]
#+filetags:   :kind:topic1:topic2:
#+identifier: 20260416T120000

Body text.
```

**Do not append to existing notes.** Notes are write-once. To add to a topic,
create a new note referencing the original.

**If a focus argument was given**, prioritize discoveries whose title,
keywords, or body match that focus. Still save off-focus discoveries only when
they are important enough that another agent would need them soon.

### 2. Update TODO.org

- Add new tasks discovered during the session as `TODO` headings
- Mark completed tasks as `DONE` using `bergheim/agent-org-set-state`
- Update existing task notes with new information
- If a focus argument was given, prefer TODO updates connected to that focus.
  Do not churn unrelated TODOs just because they are nearby.

### 3. Agent-private memory — usually skip this

**Default: do not write here.** Fragmented memory is worse than no memory.
Project knowledge in your private file is invisible to the other agents and
duplicates what belongs in denote notes.

Filter test: *"If Gemini / Codex / Pi ran into this tomorrow, would it help
them?"* If yes → denote note. Not private memory.

**Belongs in denote notes (NOT here):**
- Codebase quirks, file layouts, how a subsystem works
- Patterns, conventions, naming rules
- Gotchas that trip anyone working in the repo
- Session context / "what shipped today" / running diaries
- Decisions and their rationale
- User preferences about the project or workflow

**Belongs here (rare):**
- Your own mistake patterns — "I over-architect when X; stop and ask first"
- Tool-use quirks specific to your runtime — "Grep misses `_jolo/*.py`, fall back to bash grep"
- Model-specific behavior — things another model wouldn't experience

If you can't write the entry as "I tend to…" or "my tool X does…", it is not
personal memory. Route it to a denote note.

Do not use the running-log format (`2026-04-XX: …` dated entries). That pattern
is almost always project history masquerading as personal memory.

Files (only if the above filter passes):

- **Claude**: `.claude/MEMORY.md`
- **Gemini**: `.gemini/MEMORY.md`
- **Codex**: `.codex/MEMORY.md`
- **Pi**: `.pi/MEMORY.md`

### 4. Commit

Always `git commit` the changes without waiting for the user to ask. Use a
short commit message like "save: <brief summary>".

If a focus argument was given, include it in the brief summary when it makes the
commit clearer, for example `save: grafana dashboard mount`.

**Public-notes mode (nested `docs/.git/`):** if the project is a public repo
where `docs/` is its own private notes repo (detect via `test -d docs/.git`),
do the commit inside `docs/` instead of in the outer repo. The emacs helpers
(`agent-org-set-state`, `agent-denote-create`, etc.) already auto-commit per
call; this commit sweeps up any free-form edits that bypassed them and pushes
the lot.

```bash
if [ -d docs/.git ]; then
  (cd docs && git add -A && git commit -m "save: <brief>" 2>/dev/null && git push 2>/dev/null) || true
else
  git add docs/ && git commit -m "save: <brief>"
fi
```

In public-notes mode the outer repo's `docs/` is gitignored, so a second
outer-repo commit is not needed.

### 5. Handoff note (only if `resume` keyword given)

Write `scratch/resume-session.md` — the ephemeral, paste-back-ready state of
play for the next session. This is throwaway (`scratch/` is gitignored): no
commit, read once and discarded. Skip this whole step unless the `resume`
keyword was passed.

Read the prior `scratch/resume-session.md` first if it exists. Items under
**Still outstanding** / **Don't** usually carry forward verbatim unless this
session resolved them — the prior note is your starting point; update, don't
restart.

Gather: `git status` + `git diff --stat` (uncommitted), `git log --oneline -n 5`
(what shipped), top TODO items connected to the recent work, and anything you
specifically verified working this session (envs, ports, sockets, services).

Overwrite `scratch/resume-session.md` with these sections:

- **Header** — one line: "Resuming. State at end of last session (YYYY-MM-DD)"
  with today's actual date (`date +%Y-%m-%d` if unsure).
- **Branch / commit context** — current branch, clean or dirty, what's
  uncommitted, recent shipped commits (short hashes + subjects).
- **What changed this session** — short bullets, each with WHY, not what.
- **Re-verify (one batch)** — concrete copy-paste shell commands to re-confirm
  the things you specifically verified. Include expected output where useful.
  If you didn't verify it this session, don't put it here.
- **Still outstanding (parked, do NOT redo)** — carry forward from the prior
  note plus anything new; strike items resolved this session.
- **Don't** — rabbit holes to avoid without explicit go-ahead. Carry forward
  plus anything new this session warned off.

Tight prose, focused bullets, under ~80 lines.

### 6. Summary

After saving and committing, print a brief summary of what was written and where
(and that the handoff note was written, if `resume` was given). If a focus
argument was given, keep the summary scoped to that focus and mention any
intentionally skipped unrelated state.

## Rules

- **One topic per note** — don't create catch-all dumps
- **Be concise** — future-you reads this months later; key facts only, no filler
- **Tag generously** — kind + topics make search useful
- **No duplicates** — check existing notes with `agent-denote-find` before creating
- **Write-once** — never edit existing denote notes; create new ones instead
- **Handoff note carries forward** — parked/Don't items survive verbatim unless
  this session resolved them. Future-you needs the same warnings current-you got.
