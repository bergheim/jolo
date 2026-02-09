---
name: save-state
description: Save current session knowledge to shared project files and agent-private memory.
---

# /save-state

Persist what you've learned this session so it survives context loss and is available to all agents.

## Instructions

### 1. Shared project state (for all agents)

**`RESEARCH.org`** (repo root) — findings, investigations, technical knowledge:

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

**`TODO.org`** (repo root) — tasks, plans, action items:

- Add new tasks discovered during the session as `TODO` headings
- Mark completed tasks as `DONE`
- Update existing task notes with new information

### 2. Agent-private memory (for you only)

Write learnings specific to YOUR workflow to your own memory system:

- **Claude**: Write to your auto-memory `MEMORY.md` file
- **Gemini**: Note in your session context (no persistent memory available)
- **Codex**: Note in your session context (no persistent memory available)

Focus on: mistake patterns, things that worked/failed, codebase quirks, user preferences.

### 3. Summary

After saving, print a brief summary of what was written and where.

## Rules

- **Org-mode format only** for TODO.org and RESEARCH.org
- **Append, don't overwrite** — add new headings, don't replace existing content
- **Be concise** — future-you reads this months later; key facts only, no filler
- **Tag generously** — tags make org-mode search useful
- **No duplicates** — check existing entries before adding
