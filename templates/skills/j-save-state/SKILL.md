---
name: j-save-state
description: Save current session knowledge to shared project files and agent-private memory.
---

# /j-save-state

Persist what you've learned this session so it survives context loss and is available to all agents.

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

### 2. Update TODO.org

- Add new tasks discovered during the session as `TODO` headings
- Mark completed tasks as `DONE` using `bergheim/agent-org-set-state`
- Update existing task notes with new information

### 3. Agent-private memory (for you only)

Only put things here that are specific to YOUR workflow — mistake patterns,
personal preferences, agent-specific quirks. Everything about the project goes
in denote notes.

- **Claude**: `.claude/MEMORY.md`
- **Gemini**: `.gemini/MEMORY.md`
- **Codex**: `.codex/MEMORY.md`
- **Pi**: `.pi/MEMORY.md`

### 4. Commit

Always `git commit` the changes to docs/ without waiting for the user to ask.
Use a short commit message like "save-state: <brief summary>".

### 5. Summary

After saving and committing, print a brief summary of what was written and where.

## Rules

- **One topic per note** — don't create catch-all dumps
- **Be concise** — future-you reads this months later; key facts only, no filler
- **Tag generously** — kind + topics make search useful
- **No duplicates** — check existing notes with `agent-denote-find` before creating
- **Write-once** — never edit existing notes; create new ones instead
