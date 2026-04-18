---
name: j:note-stash
description: Use when the user explicitly wants to save a cross-project lesson, incident, convention, or gotcha to the shared stash denote notes.
---

# /j:note-stash

Write a shared denote note to `/workspaces/stash/notes` for knowledge that
should survive across repos and host-level workflow.

## Instructions

### 1. Require trailing input

Expected usage:

```text
/j:note-stash firebase incident in open webui tool verification
```

If the user does not provide freeform trailing text, stop and ask what should
be noted.

### 2. Check scope before writing

Use stash only when the note would still be useful in an unrelated project.

Ask yourself:
- Would I want this loaded at session start in an unrelated project?

If the answer is no, do not write a stash note. Say that it is project-local
and belongs in `docs/notes/` instead.

If the knowledge is both local and general, write only the stash note requested
here and explicitly say that a project-local note should also be written. Do
not silently create both.

### 3. Check for duplicates

Before writing, scan existing stash notes:

```bash
emacsclient -e '(bergheim/agent-denote-find "/workspaces/stash/notes")'
```

If a stash note already covers the same lesson, do not create a near-duplicate.
Only create a new note when there is genuinely new information or a clearly
different angle.

### 4. Create the note

Use the existing denote helper:

```bash
emacsclient -e '(bergheim/agent-denote-create "/workspaces/stash/notes" "Title here" (quote ("kind" "topic1" "topic2")) "Body text.")'
```

Choose the right kind (first keyword):
- `memory` — reusable pattern or how something works
- `research` — investigation with cross-project value
- `decision` — architectural or workflow choice with rationale
- `gotcha` — trap likely to bite again elsewhere
- `convention` — repeatable rule or workflow agreement
- `incident` — failure, cause, and fix worth remembering elsewhere

### 5. Structure the body

Keep the note concise. Include:
- Summary
- Why this belongs in stash
- General lesson
- Local origin, if relevant

Prefer generalized wording. If repo-specific paths, branches, or local
architecture are central to the note, it probably should not be stash-only.

## Rules

- Write exactly one stash note unless the user asks for more.
- Do not append to existing notes; create a new note when warranted.
- Do not silently write a project-local note too.
- Favor general lessons over session transcripts.
- Keep titles specific: `Emacs daemon wedged by org note prompt`, not
  `Note about Emacs`.
