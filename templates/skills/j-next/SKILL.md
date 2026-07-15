---
name: j-next
description: Prioritize open TODO items by effort and impact, recommend what to work on next. Add the `full` keyword to also weigh project notes and stash context.
---

# /j-next

Recommend what to work on next from the open task list. By default this is fast:
it reads only git and `docs/TODO.org`. The `full` keyword additionally weighs
project notes and stash context to sharpen estimates and catch hidden blockers.

## Arguments

`/j-next [full] [focus]`

- `full` — optional leading keyword. When present, after the fast ranking also
  scan `docs/notes/` and (for shared-tooling focus) `/workspaces/stash/notes` to
  refine effort/impact and surface blockers the TODO list alone won't show
  (step 1b). Without it, rank from git + TODO only.
- `[focus]` — optional keyword(s) or short phrase to narrow scope (e.g.,
  `jolo skills`, `emacs`, `security`, `perf grafana`). When given, rank only
  TODOs that match the focus or are direct prerequisites for that focused work.
  Anything after a leading `full` is treated as focus.

Without arguments, rank all open items from git + TODO.

## Instructions

### 1. Gather context (always)

- Enumerate TODOs with the org helper, not by hand-parsing the file:

  ```bash
  emacsclient -e '(bergheim/agent-org-list-todos "docs/TODO.org")'
  ```

  It returns a JSON array; each entry has `position`, `state`, `heading`,
  `tags`, and `autonomous`. Partition on `state`: **actionable** is `TODO`,
  `NEXT`, `INPROGRESS`; **parked** is `BLOCKED` and `WAITING` (keep parked out
  of the ranking, but list them once afterward so the user sees what's parked
  and why); ignore `DONE`/`CANCELLED`. Only read `docs/TODO.org` directly when
  you need a specific item's body text for effort/blocker context.
- Run `git log --oneline -n 10` to see recent momentum (what area was last
  worked on). The wider window than j-save/j-resume's `-n 5` is deliberate:
  this read is for area detection, not a what-shipped recap.
- The `autonomous` field marks items that are agent-runnable unattended
  (`jolo autonomous`) — surface these in the `Auto` column of the table.
- If a focus argument is given, split it into useful keywords and match against
  TODO titles, TODO body text, tags, referenced branch names, and recent commit
  subjects.

### 1b. Enrich from notes (only if `full` given)

Skip this entire step unless `full` was passed. Otherwise:

- Scan `docs/notes/` for decision/research/gotcha notes that change an item's
  effort, impact, or reveal a blocker not recorded in the TODO. Read only the
  bodies of clearly relevant notes.
- If the focus (or the highest-ranked items) touch shared tooling or workflow
  (Emacs, org-mode, denote, devcontainers, agent behavior, host integration, or
  global perf services), also skim relevant stash note filenames in
  `/workspaces/stash/notes`.

```bash
emacsclient -e '(bergheim/agent-denote-list "docs/notes" 15)'
```

### 2. Assess each actionable item

For each item, estimate:

- **Effort**: small (< 1 hour), medium (1-4 hours), large (4+ hours)
- **Impact**: how much it improves the project
- **Momentum**: is it in the same area as recent work (lower context-switch cost)

Base effort estimates on what you can see in the codebase — check if referenced
branches, files, or partial work already exist. An `INPROGRESS` item is usually
the strongest candidate: finishing started work beats opening a new front.

If a focus argument was given, exclude unrelated items from the ranked table
unless they block the focused work. Say "no open TODOs match this focus" when
that is true, then recommend the nearest useful prerequisite if one exists.

### 3. Present the list

Print a ranked table, ordered from least effort to most effort. Mark
autonomous-eligible items in the `Auto` column:

```
Effort   Auto   Item                                    Notes
──────   ────   ─────────────────────────────────────   ─────────────────────
small    ✓      Fix X                                   Branch exists, 1 file
medium          Add Y support                           Needs research
large           Rework Z                                Touches 5+ files
```

If any `INPROGRESS` items exist, list them first regardless of effort.
After the table, list any `BLOCKED`/`WAITING` items in one line each with what
they're waiting on.

After the table, recommend one item to start with and briefly explain why
(effort/impact/momentum tradeoff). If a focus argument was given, make the
recommendation within that scope.

### 4. Offer to start

Ask if the user wants to begin working on the recommended item. If the
recommended item is autonomous-eligible, mention it can be dispatched
unattended via `jolo autonomous`.

## Rules

- Read-only: do not modify any files
- Be honest about effort — don't underestimate to make items look appealing
- If a TODO references a branch, check if it still exists before claiming partial work
- Never rank `BLOCKED`/`WAITING` items as startable
- If TODO.org is missing or empty, say so and suggest creating one
