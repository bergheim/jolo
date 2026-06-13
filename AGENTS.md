# AGENTS.md

Rules for agents working in the jolo meta-project. Keep this file short: it is
loaded into every session. Recipes and command catalogs live in
`docs/agent-ops.md`.

This repository builds the jolo AI devcontainer environment. It is not a normal
app project. Generated projects use `templates/AGENTS.md`.

## Session Start

- Read `docs/PROJECT.org` and `docs/TODO.org`.
- Scan recent note filenames with
  `emacsclient -e '(bergheim/agent-denote-list "docs/notes" 15)'`.
- For shared tooling, devcontainers, Emacs, org, denote, or agent behavior, also
  scan `/workspaces/stash/notes`.
- Read only notes relevant to the task.
- Check `.git`: file means worktree, directory means main checkout.
- Ignore `scratch/` and `reference/` in reviews, searches, and status summaries.
- Nested cloned repos may carry their own agent files; those apply only inside
  that cloned repo.

## Communication

- Assume an experienced developer. Be direct, skip basic explanations, and avoid
  filler.
- Never use the phrase "smoke test"; say "test" or "verify".
- Disagree when evidence supports it; explain the reasoning.
- If the user says they took a screenshot, read the newest
  `/workspaces/stash/shot-*.png`.

## Planning

Never implement non-trivial changes without first presenting a plan and getting
explicit approval. Non-trivial means more than a couple of lines, multiple files,
architecture, behavior, or likely side effects. Read/search commands are fine.

Trivial typo/TODO/comment edits may proceed without a plan. If unsure, plan.

## Project Priorities

- Keep the codebase small. Prefer deleting code to adding wrappers.
- Trust internal helpers to raise their own errors; validate only at system
  boundaries.
- Do not add backward-compatibility shims, migrations, aliases, deprecations,
  stale-layout detection, or fallback code unless explicitly requested.
- Custom commands belong in justfiles with comments so `just --list` is the menu.
- Pick generated names with `fzf` when no name is supplied and `/dev/tty` is
  usable; otherwise fail cleanly.
- Comments explain why, not what. Keep them rare and short.

## Files and Docs

- Prefer org-mode for project docs, TODOs, and notes.
- New custom `.org` files under `docs/` must use denote filenames:
  `YYYYMMDDTHHMMSS--title-slug__kind_topic.org`.
- Fixed files such as `docs/PROJECT.org`, `docs/TODO.org`, `docs/MEMORY.org`,
  and `docs/RESEARCH.org` are exceptions.
- Cross-project discoveries go in `/workspaces/stash/notes`; repo-specific
  discoveries go in `docs/notes`.
- Install/deploy/config docs (compose, dotfiles, service defs, homelab) are
  host-level → `/workspaces/stash/notes`, as a literate cookbook: one org note
  with `:tangle <path> :mkdirp yes` src blocks, not a folder of loose files.
- Heuristic: Would I want this loaded at session start in an unrelated project?
  If yes, use stash.
- Denote notes are write-once. Create a new note for additions.

## Task Tracking

`docs/TODO.org` is the active work log and source of truth.

- Before starting work, check for an existing TODO.
- When starting a tracked task, mark it `INPROGRESS` with the org helper.
- Mark completed work `DONE` immediately, not at session end.
- Mark obsolete work `CANCELLED` with a reason.
- Preserve TODO body text when closing.
- Use `WAITING` for a person and `BLOCKED` for a system.

Use `bergheim/agent-org-set-state` for org state changes; never hand-edit TODO
keywords. Every `bergheim/agent-org-*` and `bergheim/agent-denote-*` helper
returns a plist. Re-read every path in `:wrote` before any later edit.

`:autonomous:` TODOs may only be tagged after per-item user agreement. Tag only
when all criteria hold:

- Bounded: the agent can verify "done" itself.
- In-container: no host Emacs, systemd, DNS, sudo, Tailscale, or other host step.
- Non-destructive: reversible by git reset plus branch deletion; no force-push.
- No external prompts: no auth dances, trust dialogs, MFA, or browser logins.
- Decision-free: no "decide first" or "consider whether" work remains.
- One branch: fits one branch / one `jolo tree -p` run.
- Self-contained: heading plus body is enough for a fresh agent.

Add/remove the tag only with `bergheim/agent-org-add-tag` /
`bergheim/agent-org-remove-tag`.

Helper examples are in `docs/agent-ops.md`.

## Git

- Default workflow: create a feature branch, commit meaningful progress, and
  push if a remote exists unless the user says not to.
- Branch names: `feat/<slug>`, `fix/<slug>`, `docs/<slug>`, `chore/<slug>`,
  `refactor/<slug>`, `test/<slug>`.
- Keep history rebased and linear.
- Merge feature branches into `main`, not into each other.
- Use merge commits for multi-commit branches; fast-forward single-commit
  branches.
- Never use `git reset --hard`, `git checkout --`, or `git commit --no-verify`
  unless explicitly requested.
- In a worktree, do not checkout `main`; find the main tree with
  `git worktree list`.

## Commands

| Task | Command |
|------|---------|
| List recipes | `just --list` |
| Run all tests | `just test` |
| Run matching tests | `just test-k PATTERN` |
| Verbose tests | `just test-v` |
| Build image | `podman build -t jolo .` |
| Launch project | `jolo up` |
| Launch detached | `jolo up -d` |
| Create worktree container | `jolo tree <slug>` |
| Dispatch autonomous TODOs | `jolo autonomous --dry-run` first |

System Python is externally managed on Alpine; use `uv` or the just recipes for
Python tests.

## Project Shape

Key files:

- `Containerfile` builds the Alpine image.
- `container/entrypoint.sh` starts container services.
- `container/dev.yml` defines the tmux layout.
- `container/browser-check.js` is the browser audit CLI.
- `container/agent-helpers.el` provides org/denote helpers.
- `jolo.py` and `_jolo/` implement the CLI.
- `templates/` is copied into generated projects.

Environment and tooling expectations:

- Use `$PORT` for every dev server; never hardcode 4000.
- Assume tools baked into the image exist; do not add fallback checks for them.
- Browser automation uses Playwright with system Chromium.
- Node package management is pnpm. Do not introduce npm/npx flows.
- Image tooling preference: AVIF > WebP > PNG/JPEG; use vips/avifenc/cwebp.
- Emacs runs as a daemon. Use `emacsclient --eval`; never ask the user to run
  interactive Emacs commands.
- Host Emacs config lives at `~/.config/emacs`; `.devcontainer/.emacs-config/`
  is only a container copy.

## Verification

- For code changes, run the narrowest meaningful test first, then broader tests
  when the risk justifies it.
- For CLI/template changes, run focused unit tests plus `just test` when feasible.
- For visible web changes, verify with browser tooling and inspect the screenshot.
- For accessibility-sensitive web work, run the project a11y recipe when present.
- Report commands run and any tests you could not run.

## Security and Host Boundaries

- Containers have no X11; Wayland is conditional and isolated.
- Host-only operations stay host-only. If a task requires host sudo, Tailscale,
  DNS, systemd, or trust dialogs, explain the manual step instead of trying to
  tunnel around it, and record the host-side procedure in
  `/workspaces/stash/notes` via `bergheim/agent-denote-*` — it does not persist
  in container state.
- `jolo expose` (host-side) publishes one project's `$PORT` publicly via host
  Caddy; deny-by-default, one project at a time, only while it runs. A container
  cannot expose itself.
- Cross-container Podman access is off by default and must be enabled from the
  host. Treat `Cannot connect to Podman ... no such file or directory` as the
  off state.

## More Recipes

Read `docs/agent-ops.md` only when needed for:

- Exact org/denote `emacsclient` forms.
- Stash cookbook (literate `:tangle`) note format.
- Browser-check and Playwright command catalogs.
- jolo command catalog, host-side `jolo expose`, and podman gate operations.
- Local llama-swap curl examples.
- Cross-agent review snippets.
- Share/notify/perf operational details.
