---
name: j-load-state
description: Load shared project knowledge and current priorities at session start.
---

# /j-load-state

Prime the agent with accumulated project knowledge. Run at the start of a session
to pick up where previous sessions left off.

## Arguments

- `[focus]` — optional keyword(s) to narrow the load. When given, bias note
  selection and the summary toward that topic (e.g. `voice`, `jolo`, `skills`,
  `security`, `autonomous`, `emacs`). Use it when you know what this session is
  about — saves context and surfaces more relevant prior work.

Without a focus argument, load broadly as before.

## Instructions

### 1. Read structured state

Read these files (skip any that don't exist):

- `docs/PROJECT.org` — project context, architecture, key decisions
- `docs/TODO.org` — current tasks and priorities

Also check legacy files if they exist (being replaced by denote notes):
- `docs/MEMORY.org` — legacy conventions
- `docs/RESEARCH.org` — legacy investigations (only last 3 top-level headings)

### 2. Scan denote notes

If `docs/notes/` exists, scan note filenames for context:

```bash
emacsclient -e '(bergheim/agent-denote-list "docs/notes" 15)'
```

This returns the 15 most recent notes with titles and keywords. Read the full
content of notes relevant to the current session (gotchas, conventions, recent
decisions). Skip notes that are clearly unrelated.

**If a focus argument was given**, prefer notes whose title or keywords match
the focus — read their full bodies even if they fall outside the 15 most
recent. Use a filename grep as a helper:

```bash
ls docs/notes/*__*_<focus>*.org 2>/dev/null   # keyword match
ls docs/notes/*<focus>*.org 2>/dev/null        # title-slug match
```

De-prioritize notes that clearly don't touch the focus — skim titles only.

If the helper isn't available, fall back to listing filenames directly:

```bash
ls -t docs/notes/*.org 2>/dev/null | head -15
```

Denote filenames encode metadata: `YYYYMMDDTHHMMSS--title-slug__kind_topic.org`

If the session touches shared tooling or workflow (for example Emacs,
org-mode, denote, devcontainers, agent behavior, or host integration), also
scan stash note filenames:

```bash
emacsclient -e '(bergheim/agent-denote-list "/workspaces/stash/notes" 15)'
```

Read the full content of stash notes relevant to the current session. Skip
stash notes that are clearly unrelated. Apply the same focus-filtering logic
to stash notes when a focus argument is given.

### 3. Read agent-private memory

- **Claude**: `.claude/MEMORY.md` (auto-memory index)
- **Gemini**: `.gemini/MEMORY.md`
- **Codex**: `.codex/MEMORY.md`
- **Pi**: `.pi/MEMORY.md`

### 4. Synthesize

Print a brief summary covering:

- **Active work**: open TODOs and recent decisions/research from notes
- **Key gotchas**: any gotcha or convention notes likely to bite this session
- **Stale items**: flag any TODOs or notes that look outdated

If a focus argument was given, scope the summary to that topic: list TODOs
that match the focus first, surface the gotchas most likely to bite *this*
kind of work, and say "no open TODOs match this focus" if that's the case.
Don't pad by including unrelated items just to fill the summary.

Use 3-4 short paragraphs. No bullet lists unless the user asks.

## Rules

- Read-only: do not modify any files.
- Do not dump raw file contents — summarize.
- If a file is missing, skip it silently.
- Prefer denote notes over legacy MEMORY.org/RESEARCH.org when both exist.
