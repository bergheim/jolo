---
name: j-save-state
description: Save current session knowledge to shared project files and agent-private memory.
---

# /j-save-state

Persist what you've learned this session so it survives context loss and is available to all agents.

## Arguments

- `[focus]` — optional keyword(s) or short phrase describing what to save
  around (e.g. `perf`, `grafana dashboards`, `jolo skills`, `public notes`).
  When given, bias note creation, TODO updates, commit message, and summary
  toward that topic.

Without a focus argument, save broadly as before.

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
short commit message like "save-state: <brief summary>".

If a focus argument was given, include it in the brief summary when it makes the
commit clearer, for example `save-state: grafana dashboard mount`.

**Public-notes mode (nested `docs/.git/`):** if the project is a public repo
where `docs/` is its own private notes repo (detect via `test -d docs/.git`),
do the commit inside `docs/` instead of in the outer repo. The emacs helpers
(`agent-org-set-state`, `agent-denote-create`, etc.) already auto-commit per
call; save-state's commit sweeps up any free-form edits that bypassed them
and pushes the lot.

```bash
if [ -d docs/.git ]; then
  (cd docs && git add -A && git commit -m "save-state: <brief>" 2>/dev/null && git push 2>/dev/null) || true
else
  git add docs/ && git commit -m "save-state: <brief>"
fi
```

In public-notes mode the outer repo's `docs/` is gitignored, so a second
outer-repo commit is not needed.

### 5. Summary

After saving and committing, print a brief summary of what was written and where.
If a focus argument was given, keep the summary scoped to that focus and mention
any intentionally skipped unrelated state.

## Rules

- **One topic per note** — don't create catch-all dumps
- **Be concise** — future-you reads this months later; key facts only, no filler
- **Tag generously** — kind + topics make search useful
- **No duplicates** — check existing notes with `agent-denote-find` before creating
- **Write-once** — never edit existing notes; create new ones instead
