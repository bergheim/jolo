---
name: j-resume
description: Resume a session — read the paste-back handoff note to recall what we last worked on, falling back to a git+TODO status when none exists. Add the `full` keyword to also deep-scan project notes and memory.
---

# /j-resume

Get back up to speed at the start of a session. The start-of-session complement
to `/j-save` (which writes durable knowledge and, with its `resume` keyword, the
handoff note this skill reads). Read-only: never modify any files.

## Arguments

`/j-resume [full] [focus]`

- `full` — optional leading keyword. When present, after the light read also
  deep-scan denote/stash notes, private memory, and PROJECT.org for the broader
  picture (step 2). Without it, do the light read only.
- `[focus]` — optional keyword(s) or short phrase to narrow the load (e.g.
  `voice`, `jolo skills`, `perf grafana`, `security`, `emacs`). Bias note
  selection and the summary toward that topic. Anything after a leading `full`
  is treated as focus.

Without arguments, do the light read and summarize the whole picture.

## Instructions

### 1. Light read — "what we last worked on" (always)

Read `scratch/resume-session.md` if it exists. This is the handoff note from the
last session (written by `/j-save resume`): branch/commit context, what changed
and why, re-verify commands, parked items, and don'ts.

**Freshness check.** Compare the note's header date against recent history
(`git log --oneline -n 5`, current branch). If the repo has clearly moved on
since the note was written (different branch, many newer commits, the note's
"uncommitted" state no longer matches), say so — treat the note as a lead, not
ground truth, and lean on live git/TODO state instead.

**If `scratch/resume-session.md` does not exist** (mid-session, or it was never
written), fall back to a quick status from live state:

- Recent commits: `git log --oneline -n 5`
- Repo status: `git status -sb`
- Current priorities: top TODOs (`rg -n "^\*+ (TODO|NEXT|INPROGRESS)" docs/TODO.org | head -8`)

Either way, the headline output is **what we last worked on and what's next** —
short, natural-language, no raw file dumps.

### 2. Full state scan (only if `full` keyword given)

Skip this entire step unless `full` was passed. Otherwise, after the light read,
prime the broader project context:

**Structured state** — read these (skip any that don't exist):

- `docs/PROJECT.org` — project context, architecture, key decisions
- `docs/TODO.org` — current tasks and priorities
- Legacy (being replaced by denote notes): `docs/MEMORY.org`,
  `docs/RESEARCH.org` (only last 3 top-level headings)

**Denote notes** — if `docs/notes/` exists, scan filenames for context:

```bash
emacsclient -e '(bergheim/agent-denote-list "docs/notes" 15)'
```

This returns the 15 most recent notes with titles and keywords. Read the full
content of notes relevant to this session (gotchas, conventions, recent
decisions). Skip clearly unrelated notes.

If the session touches shared tooling or workflow (Emacs, org-mode, denote,
devcontainers, agent behavior, host integration), also scan stash notes:

```bash
emacsclient -e '(bergheim/agent-denote-list "/workspaces/stash/notes" 15)'
```

If the helper isn't available, fall back to listing filenames:

```bash
ls -t docs/notes/*.org 2>/dev/null | head -15
```

Denote filenames encode metadata: `YYYYMMDDTHHMMSS--title-slug__kind_topic.org`

**If a focus argument was given**, split it into keywords and prefer notes whose
title or keywords match — read their full bodies even if outside the 15 most
recent. Use filename greps as helpers:

```bash
ls docs/notes/*__*_<keyword>*.org 2>/dev/null   # keyword match
ls docs/notes/*<keyword>*.org 2>/dev/null        # title-slug match
```

For multi-word focus like `perf grafana`, search each significant word and the
slug form (`perf-grafana`). De-prioritize notes that clearly don't touch the
focus — skim titles only.

**Agent-private memory:**

- **Claude**: `.claude/MEMORY.md` (auto-memory index)
- **Gemini**: `.gemini/MEMORY.md`
- **Codex**: `.codex/MEMORY.md`
- **Pi**: `.pi/MEMORY.md`

### 3. Synthesize

Print a brief summary. For a light read, lead with what we last worked on and
the immediate next step. For `full`, also cover:

- **Active work**: open TODOs and recent decisions/research from notes
- **Key gotchas**: any gotcha or convention notes likely to bite this session
- **Stale items**: flag any TODOs or notes that look outdated

If a focus argument was given, scope the summary to that topic: list matching
TODOs first, surface the gotchas most likely to bite *this* kind of work, and
say "no open TODOs match this focus" if that's the case. Don't pad with
unrelated items.

Use 3-4 short paragraphs. No bullet lists unless the user asks.

## Rules

- **Read-only**: do not modify any files. Writing state is `/j-save`'s job.
- Do not dump raw file contents — summarize.
- If a file is missing, skip it silently.
- Treat the handoff note as a lead, not gospel — verify against live git/TODO
  state when they disagree.
- Prefer denote notes over legacy MEMORY.org/RESEARCH.org when both exist.
