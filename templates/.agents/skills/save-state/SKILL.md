---
name: jolo:save-state
description: Save current session knowledge to shared project files and agent-private memory.
---

# /jolo:save-state

Persist what you've learned this session so it survives context loss and is available to all agents.

## Instructions

### 1. Shared project state (for all agents)

Everything about the project goes in `docs/` — this is the shared knowledge base that all agents read.

**`docs/MEMORY.org`** — conventions, patterns, gotchas:

- Add new patterns, conventions, or gotchas discovered this session
- Tag with relevant keywords (e.g., `:musl:auth:perf:`)
- Remove or update entries that are no longer true

**`docs/RESEARCH.org`** — findings, investigations, technical knowledge:

- Create the file if it doesn't exist (use the template below)
- Add a new top-level heading with a descriptive title
- Include: what was investigated, root cause, solution, key files, links
- Tag with relevant keywords (e.g., `:musl:nodejs:container:`)
- Use org-mode format: headings, lists, src blocks

Template for new file:
```org
#+TITLE: Research Notes
#+STARTUP: overview

```

Example entry:
```org
* Gemini CLI crashes on Alpine/musl                        :musl:nodejs:gemini:
:PROPERTIES:
:DATE: 2026-02-09
:END:

node-pty prebuilt binary segfaults during PTY cleanup on musl libc.

** Root cause
~@lydell/node-pty-linux-x64/pty.node~ is compiled against glibc.
The ~forkpty()~ call works but cleanup/destroy segfaults on musl.

** Fix
Set ~tools.shell.enableInteractiveShell: false~ in gemini settings.
This bypasses node-pty and uses ~child_process~ fallback.

** Refs
- https://github.com/google-gemini/gemini-cli/issues/14087
```

**`docs/TODO.org`** — tasks, plans, action items:

- Add new tasks discovered during the session as `TODO` headings
- Mark completed tasks as `DONE`
- Update existing task notes with new information

### 2. Agent-private memory (for you only)

Only put things here that are specific to YOUR workflow — mistake patterns, personal preferences, agent-specific quirks. Everything about the project itself goes in `docs/`.

- **Claude**: `.claude/MEMORY.md`
- **Gemini**: `.gemini/MEMORY.md`
- **Codex**: `.codex/MEMORY.md`
- **Pi**: `.pi/MEMORY.md`

### 3. Commit

Always `git commit` the changes to docs/ without waiting for the user to ask. Use a short commit message like "save-state: <brief summary>".

### 4. Summary

After saving and committing, print a brief summary of what was written and where.

## Rules

- **Org-mode format only** for TODO.org, MEMORY.org, and RESEARCH.org
- **Append, don't overwrite** — add new headings, don't replace existing content
- **Be concise** — future-you reads this months later; key facts only, no filler
- **Tag generously** — tags make org-mode search useful
- **No duplicates** — check existing entries before adding
