---
name: j:load-state
description: Load shared project knowledge and current priorities at session start.
---

# /j:load-state

Prime the agent with accumulated project knowledge. Run at the start of a session
to pick up where previous sessions left off.

## Instructions

### 1. Read shared state

Read these files (skip any that don't exist):

- `docs/PROJECT.org` — project context, architecture, key decisions
- `docs/MEMORY.org` — conventions, patterns, gotchas
- `docs/TODO.org` — current tasks and priorities
- `docs/RESEARCH.org` — only the last 3 top-level headings (recent investigations)

### 2. Read agent-private memory

- **Claude**: `.claude/MEMORY.md` (auto-memory index)
- **Gemini**: `.gemini/MEMORY.md`
- **Codex**: `.codex/MEMORY.md`
- **Pi**: `.pi/MEMORY.md`

### 3. Synthesize

Print a brief summary covering:

- **Active work**: open TODOs and recent research, prioritized
- **Key gotchas**: anything from MEMORY.org likely to bite this session
- **Stale items**: flag any TODOs or memory entries that look outdated

Use 3-4 short paragraphs. No bullet lists unless the user asks.

## Rules

- Read-only: do not modify any files.
- Do not dump raw file contents — summarize.
- If a file is missing, skip it silently.
