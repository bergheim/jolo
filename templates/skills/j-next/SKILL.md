---
name: j-next
description: Prioritize open TODO items by effort and impact, recommend what to work on next.
---

# /j-next

Recommend what to work on next from the open task list.

## Arguments

- `[focus]` — optional keyword(s) or short phrase to narrow scope (e.g.,
  `jolo skills`, `emacs`, `security`, `perf grafana`). When given, rank only
  TODOs that match the focus or are direct prerequisites for that focused work.

Without a focus argument, rank all open TODOs as before.

## Instructions

### 1. Gather context

- Read `docs/TODO.org` for all open `TODO` items
- Run `git log --oneline -n 10` to see recent momentum (what area was last worked on)
- If a focus argument is given, split it into useful keywords and match against
  TODO titles, TODO body text, tags, referenced branch names, and recent commit
  subjects.
- If the focus touches shared tooling or workflow (for example Emacs,
  org-mode, denote, devcontainers, agent behavior, host integration, or global
  perf services), also skim relevant stash note filenames in
  `/workspaces/stash/notes`.

### 2. Assess each open item

For each TODO, estimate:

- **Effort**: small (< 1 hour), medium (1-4 hours), large (4+ hours)
- **Impact**: how much it improves the project
- **Momentum**: is it in the same area as recent work (lower context-switch cost)

Base effort estimates on what you can see in the codebase — check if referenced branches, files, or partial work already exist.

If a focus argument was given, exclude unrelated TODOs from the ranked table
unless they block the focused work. Say "no open TODOs match this focus" when
that is true, then recommend the nearest useful prerequisite if one exists.

### 3. Present the list

Print a ranked table, ordered from least effort to most effort:

```
Effort   Item                                    Notes
──────   ─────────────────────────────────────   ─────────────────────
small    Fix X                                   Branch exists, 1 file
medium   Add Y support                           Needs research
large    Rework Z                                Touches 5+ files
```

After the table, recommend one item to start with and briefly explain why (effort/impact/momentum tradeoff).
If a focus argument was given, make the recommendation within that scope.

### 4. Offer to start

Ask if the user wants to begin working on the recommended item.

## Rules

- Read-only: do not modify any files
- Be honest about effort — don't underestimate to make items look appealing
- If a TODO references a branch, check if it still exists before claiming partial work
- If TODO.org is missing or empty, say so and suggest creating one
