# AGENTS.md

Guidelines for AI coding assistants working on this project.

Generated: <YYYY-MM-DD>

Keep this file short: it is loaded into every session. Recipes and command
catalogs live in `docs/agent-ops.md`.

## Session Start

- Read `docs/PROJECT.org` and `docs/TODO.org`.
- If `docs/PROJECT.org` is missing, do not start implementation. First ask the
  user for the project purpose, audience, constraints, and key decisions; write
  them to `docs/PROJECT.org`.
- Scan recent note filenames with
  `emacsclient -e '(bergheim/agent-denote-list "docs/notes" 15)'`.
- Read only notes relevant to the task.
- For shared tooling, devcontainers, Emacs, org, denote, or agent behavior, also
  scan `/workspaces/stash/notes`.
- Check `.git`: file means worktree, directory means main checkout.
- Treat `scratch/` as gitignored throwaway space, not project code.

## Communication and Planning

- Assume the user is an experienced developer. Be direct and skip filler.
- Disagree when evidence supports it; explain the reasoning.
- If the user says they took a screenshot, read the newest
  `/workspaces/stash/shot-*.png`.
- Do not implement non-trivial changes without first presenting a plan and
  getting explicit approval. Read/search commands are fine.

## Project Memory

- `docs/PROJECT.org` holds stable project context and decisions.
- `docs/TODO.org` is the active work log.
- Repo-specific discoveries go in `docs/notes`.
- Cross-project discoveries go in `/workspaces/stash/notes`.
- Install/deploy/config docs (compose, dotfiles, service defs, homelab) are
  host-level → `/workspaces/stash/notes`, as a literate cookbook: one org note
  with `:tangle <path> :mkdirp yes` src blocks, not a folder of loose files.
- Heuristic: Would I want this loaded at session start in an unrelated project?
  If yes, use stash.
- Denote notes are write-once. Create a new note for additions.
- To link notes, always use `bergheim/agent-denote-link`; never hand-write
  `[[denote:ID]]` or a bare id (denote derives backlinks only from links its own
  API emits, so a typed id never registers).
- New custom `.org` files under `docs/` must use denote filenames:
  `YYYYMMDDTHHMMSS--title-slug__kind_topic.org`.
- Fixed files such as `docs/PROJECT.org` and `docs/TODO.org` are exceptions.
- Personal memories are agent-specific: `.claude/MEMORY.md`,
  `.gemini/MEMORY.md`, `.codex/MEMORY.md`, `.pi/MEMORY.md`.

## Task Tracking

`docs/TODO.org` is the source of truth.

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
- One branch: fits one branch.
- Self-contained: heading plus body is enough for a fresh agent.

Add/remove the tag only with `bergheim/agent-org-add-tag` /
`bergheim/agent-org-remove-tag`.

Helper examples are in `docs/agent-ops.md`.

## Development

- Use `just --list` as the command menu.
- Custom commands belong in the justfile with a `# comment` description.
- The dev server is expected to already be running via `just dev` with reload.
  Do not start temporary servers on other ports for screenshots or tests.
- Use `just dev-restart` after dependency/config changes or server crashes.
- `dev.log` is a tee of dev-server stdout/stderr; read it like a normal file.
- Use `$PORT` in every server command and URL. Do not hardcode 4000.
- Servers bind to `0.0.0.0` for container networking; browser/curl connect to
  `localhost:$PORT`.
- Node projects use pnpm. Do not introduce npm/npx flows.

| Task | Command |
|------|---------|
| List recipes | `just --list` |
| Run dev server | `just dev` |
| Restart dev server | `just dev-restart` |
| Run once | `just run` |
| Run tests | `just test` |
| Watch tests | `just test-watch` |
| Add dependency | `just add NAME` |
| Manage worktrees | `just wt` |
| Run performance probe | `just perf` |
| Launch Antigravity TUI | `agy` |

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

## Code Quality

- Pre-commit hooks are installed. If a hook blocks commit, fix the issue and
  retry; never skip hooks.
- Prefer small, direct code and established project patterns.
- Add type annotations and use strict mode where the language supports it.
- Add abstractions only when they remove real complexity.
- Validate at boundaries; do not duplicate internal checks.
- Comments explain why, not what. Keep them rare and short.
- Test behavior through public contracts, not implementation details.

## Frontend and Browser Work

- After visible UI changes, verify the running app in browser tooling and inspect
  the screenshot before committing.
- Run `just a11y` when present for UI/accessibility changes.
- Use semantic HTML, labels for inputs, keyboard-reachable controls, visible focus
  styles, useful alt text, and AA contrast.
- Use `browser-check` for quick one-shot checks and `playwright-cli` for
  multi-step flows.

## Host and Container Boundaries

- Shared, non-reproducible resources live in `/workspaces/stash`.
- `share <path>` publishes an artifact from stash when a browser-viewable URL is
  useful.
- Cross-container Podman access is off by default and must be enabled from the
  host. `Cannot connect to Podman ... no such file or directory` is the off state.
- Host-only operations stay host-only. If a task needs host sudo, Tailscale, DNS,
  systemd, or trust dialogs, explain the manual step, and record the host-side
  procedure in `/workspaces/stash/notes` via `bergheim/agent-denote-*` — it does
  not persist in container state.
- Emacs runs as a daemon. Use `emacsclient --eval`; never ask the user to run
  interactive Emacs commands.

## More Recipes

Read `docs/agent-ops.md` only when needed for:

- Exact org/denote `emacsclient` forms.
- Browser-check and Playwright command catalogs.
- Port, notify, share, image, perf, and podman operations.
- Local llama-swap curl examples.
- Cross-agent review snippets.
