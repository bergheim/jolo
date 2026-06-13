---
name: bootstrap
description: Get oriented on host-level, cross-project knowledge by reading the stash README map. Use when starting fresh in a container, or when you need the lay of the land for hardware, dotfiles/preferences, Emacs, Linux, or cross-project conventions that live outside the current repo.
---

# /bootstrap

`/workspaces/stash` is the cross-machine, host-level knowledge base shared across
every project and container. Its `README.org` is a hand-curated map into the
denote notes under `notes/`.

## Instructions

1. Read `/workspaces/stash/README.org`. It explains how to read and write notes
   (always via the `bergheim/agent-denote-*` emacsclient helpers), and links the
   key notes for hardware, environment/preferences, Emacs, Linux, and
   agent-workflow conventions.
2. Follow the links relevant to your task. For anything not linked, discover by
   keyword:

   ```bash
   emacsclient -e '(bergheim/agent-denote-find "/workspaces/stash/notes" (quote ("emacs")))'
   emacsclient -e '(bergheim/agent-denote-list "/workspaces/stash/notes" 20)'
   ```

3. Summarize what's relevant to the session in 2-3 short paragraphs.

## Rules

- Read-only orientation. Do not modify notes here.
- If `/workspaces/stash/README.org` is missing, fall back to scanning note
  filenames with `agent-denote-list` and report that the map is absent.
