---
name: j-next
description: Prioritize open TODO items by effort and impact, recommend what to work on next. Optional sentence narrows scope (e.g. "big tasks", "gym screen").
disable-model-invocation: true
---

# /j-next

Recommend what to work on next. Fast: git + `docs/TODO.org` headings. A note
is read only when a ranked TODO already cites it.

## Arguments

`/j-next [sentence]`

The sentence is optional and interpreted, not tokenized. Examples: `gym screen`,
`big tasks`, `trust, not chrome`, `perf hub`. Without one, rank all open items.

## Instructions

Do not call advisor. Do not read `docs/PROJECT.org`. Do not scan `docs/notes`
or stash notes. Do not list every open TODO's body.

### 1. Gather

```bash
emacsclient -e '(bergheim/agent-org-list-todos "docs/TODO.org" (list "TODO" "NEXT" "INPROGRESS" "WAITING" "SOMEDAY"))'
git log --oneline -n 10
git worktree list
```

`list-todos` returns `(:path "/tmp/agent-org-todos-….json" :count N)`. Read
that file. Each entry has `line`, `state`, `heading`, `tags`, `notes` (denote
ids linked from that entry), and `autonomous`.

Partition on `state`: **actionable** is `TODO`, `NEXT`, `INPROGRESS`; **parked**
is `WAITING` / `BLOCKED` (list after the table, do not rank). Skip `SOMEDAY` in
the table.

If a sentence was given, interpret it (effort, area, audience) and drop
unrelated actionable items unless they block the focused work. Keyword-splitting
is wrong: `big tasks` means large-effort items, not headings that contain
"big". Say "no open TODOs match this focus" when that is true, then recommend
the nearest useful prerequisite if one exists.

### 2. Rank

From headings first. Read **at most three bodies** (use `line`): the
`INPROGRESS` item if any, then whatever the sentence points at, then the likely
recommendation. Read a cited note only for those same items, and only via
`notes` (resolve `docs/notes/<id>--*.org`) — not a folder scan.

Estimate effort (small < 1h, medium 1–4h, large 4h+), impact, and momentum
against the last 10 commits. If a heading names a branch, check that branch
exists before calling it partial work. An `INPROGRESS` item is usually the
strongest candidate; finishing started work beats opening a new front, unless
what remains is a multi-session project and a small item on the same surface
is clearly better — say so.

### 3. Present

Table is **top 8**, INPROGRESS first, then least effort to most:

```
Effort   Auto   Item                                    Notes
──────   ────   ─────────────────────────────────────   ─────────────────────
small    ✓      Fix X                                   Branch exists, 1 file
medium          Add Y support                           Needs research
large           Rework Z                                Touches 5+ files
```

`autonomous` marks `jolo autonomous` eligibility. After the table, one line
per parked item and what it is waiting on. Then recommend one item and why.
If a sentence was given, recommend within that scope.

### 4. Offer to start

Ask if the user wants to begin. Mention `jolo autonomous` only when the
recommended item is autonomous-eligible.

## Rules

- Read-only: do not modify any files
- Be honest about effort
- Never rank `WAITING` / `BLOCKED` / `SOMEDAY` as startable
- If `TODO.org` is missing or empty, say so and suggest creating one
