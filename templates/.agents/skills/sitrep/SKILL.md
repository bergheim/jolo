---
name: sitrep
description: Generate a short natural-language status update focused on the most recent changes and current priorities.
---

# /sitrep

Produce a concise, human-readable status update that gets the user back up to speed quickly.

## Arguments

- `[scope]` — optional hint like `project`, `work`, `recent`, or `priorities`

## Instructions

### 1. Gather current context (read-only)

- Recent commits: `git log --oneline -n 5`
- High-level repo status (optional): `git status -sb`
- Current priorities: top TODOs in `TODO.org` (use `rg -n "^\*+ TODO" TODO.org` and take the first 5-8 items)

### 2. Write the sitrep

- Use 2 short paragraphs.
- Focus on the most recent changes and current priorities.
- Avoid listing commands or raw outputs; summarize in natural language.
- Keep it brief and direct.

## Rules

- Read-only: do not modify any files.
- No bullet lists unless the user explicitly asks.
- If data is missing, say so briefly and continue.
