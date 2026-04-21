# AGENTS.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> **Note:** This is a META-PROJECT for building the AI development container environment.
> It is NOT meant for general development. For projects created with `jolo create`,
> see `templates/AGENTS.md` which gets copied to new projects.

## Communication

Assume the user is an experienced developer. Skip basic explanations, don't over-qualify statements, and don't pad responses with filler ("great question!", "certainly!"). Never use the phrase "smoke test" — just say "test" or "verify".

Disagree when you have evidence. If the user's approach has a flaw or you see a better alternative, say so directly with your reasoning — don't just go along with it. Pushback leads to better discussions and a better product. A wrong agreement costs more than a brief debate.

## Screenshots

When the user says they took a screenshot, read the latest one:

```bash
ls -t /workspaces/stash/shot-*.png | head -1
```

Then use the Read tool on that file to view it.

## Scratch Directories

`scratch/` and `reference/` are gitignored scratch spaces. Use `scratch/` for experiments, generated assets (logos, mockups), and throwaway work. These directories are not part of the project and should be ignored during reviews, searches, and status checks.

## Cloned Repos

If a repo cloned with `jolo clone` includes its own agent instruction files (AGENTS/CLAUDE),
those instructions apply only within that repo. They do not override this meta-project’s
instructions.

## Planning Before Acting

**NEVER start implementing non-trivial changes without presenting a plan first.** If a task involves modifying more than a couple of lines, changing architecture, touching multiple files, or could have unintended side effects — stop and discuss the approach before writing any code. Do not assume approval. Do not "just fix it." Present the plan, wait for explicit approval, then execute.

**Trivial changes are allowed without a plan.** Examples: add a TODO, fix a typo, or change a couple of lines in a single file with no behavioral impact. If you're unsure whether it's trivial, treat it as non-trivial and plan.

This applies even when the problem is obvious. Diagnosing a problem is not the same as having permission to fix it.
Non-destructive commands (reads/searches) do not require approval.

## Minimalism

Keep the codebase small. Fewer lines, fewer features, fewer moving parts. Do not add commands, helpers, or abstractions that provide marginal value over existing tools. If `podman logs` already works, we don't need `jolo logs`. Prefer deleting code to adding it.

Do not add defensive checks that duplicate what called functions already handle. If `find_git_root()` raises on failure, the caller does not need to check for a git repo first. Trust internal code — only validate at system boundaries (user input, external APIs). Let functions fail naturally with their own errors.

## Backward Compatibility

This project is in heavy development. Do NOT worry about backward compatibility — just make the change directly. No aliases, shims, deprecation warnings, or re-exports for old names.

## Comments

Keep comments to a minimum. Only comment *why*, never *what*. Do not add comments that restate the code. Do not add comments that narrate the conversation or explain context that is obvious from reading the code. `printf '\a'` does not need a comment explaining what a terminal bell is, or if it works through tmux (which was in  the agent conversation). If a comment is needed at all, keep it to a few words — not a sentence.

## Project Overview

This repo builds and maintains the containerized Emacs GUI environment on Alpine Linux (musl-based), designed as a devcontainer for AI-assisted development. Alpine provides excellent package coverage and small image size. Browser automation uses Playwright with system Chromium. The container includes Claude Code CLI pre-configured in YOLO mode (`--dangerously-skip-permissions`).

You are encouraged to suggest state-of-the-art CLI tools that could improve development of this environment. We control the full stack in `Containerfile`, so proposals can be evaluated and baked into the image directly. Assume required tools exist in this repo’s container image; do not add fallbacks or checks for missing tools.

**What this repo produces:**
- Container image (`emacs-gui`) with all dev tools pre-installed
- `jolo.py` + `_jolo/` package — CLI for launching devcontainers with git worktree support
- Templates for new projects (`templates/`)

## File Format Preferences

Prefer org-mode (`.org`) over markdown for project documentation, TODOs, and notes. This is an Emacs-centric project.

## Task Tracking

`docs/TODO.org` is the active work log, not a reference document. Treat it as the single source of truth for what needs doing.

- **Before starting work**: check TODO.org for existing tasks — don't duplicate effort
- **When you complete a task**: mark it `DONE` immediately, not at the end of the session
- **When you discover new work**: add it as a `TODO` heading right away
- **When a task is no longer relevant**: mark it `CANCELLED` with a reason
- **Never delete body text** when closing a TODO — the original description, context, and notes are valuable history. The reason goes in the LOGBOOK, not as a replacement for the body.

### Editing org files with emacsclient

**Always use `bergheim/agent-org-set-state` for org state changes** — never manually
edit TODO/DONE keywords with a text editor. Org-mode adds CLOSED timestamps, LOGBOOK
entries, and state transition metadata automatically. The helper handles buffer
staleness, note capture, and save in one call.

**Mark a TODO as DONE:**

```bash
emacsclient -e '(bergheim/agent-org-set-state "docs/TODO.org" "TODO Heading text here" "DONE")'
```

**Mark as DONE with a reason note:**

```bash
emacsclient -e '(bergheim/agent-org-set-state "docs/TODO.org" "TODO Heading text here" "DONE" "Resolved by commit abc1234.")'
```

**Cancel a TODO with a reason:**

```bash
emacsclient -e '(bergheim/agent-org-set-state "docs/TODO.org" "TODO Heading text here" "CANCELLED" "No longer relevant because X.")'
```

This produces proper org metadata:

```org
** CANCELLED The task heading
CLOSED: [2026-04-13 Mon 12:08]
:LOGBOOK:
- State "CANCELLED"  from "TODO"  [2026-04-13 Mon 12:08] \\
  No longer relevant because X.
:END:
   Original body text preserved here...
```

Available states: `TODO`, `NEXT`, `INPROGRESS`, `WAITING`, `BLOCKED`, `DONE`, `CANCELLED`.

`BLOCKED` means "stalled on an external dependency" (vendor response, upstream
bug, cert renewal, etc.). Use `WAITING` for "waiting on a person" and `BLOCKED`
for "waiting on a system." When `:clock t` is passed to `set-state`, transitions
to `BLOCKED` close an active clock — this is a project policy choice, not an
org-mode semantic.

### Additional org helpers

All of these share the same ambiguity-safe heading lookup — if the regex matches
multiple headings, the helper errors and lists the line numbers so you can
disambiguate.

**Add a log note without changing state:**

```bash
emacsclient -e '(bergheim/agent-org-add-note "docs/TODO.org" "TODO Heading" "Made progress on X.")'
```

**Ensure a stable `:ID:` property (returns the id):**

```bash
emacsclient -e '(bergheim/agent-org-ensure-id "docs/TODO.org" "TODO Heading")'
```

**Transition by `:ID:` (immune to heading renames and duplicate headings):**

```bash
emacsclient -e '(bergheim/agent-org-set-state-by-id "docs/TODO.org" "abc-def-123" "DONE")'
```

**Track time on a transition (clock in on INPROGRESS, clock out on DONE/BLOCKED/CANCELLED):**

```bash
# Signature: set-state FILE HEADING-RE STATE &optional NOTE ENSURE-SESSION-ID CLOCK
emacsclient -e '(bergheim/agent-org-set-state "docs/TODO.org" "TODO Heading" "INPROGRESS" nil t t)'
```

The 5th arg (`ensure-session-id`) auto-adds `:SESSION_ID:` on INPROGRESS so logs
and notifications can correlate back to the TODO. The 6th arg (`clock`) drives
`org-clock-in`/`org-clock-out`.

**Tag management:**

```bash
# Add :autonomous: tag (idempotent)
emacsclient -e '(bergheim/agent-org-add-tag "docs/TODO.org" "TODO Heading" "autonomous")'

# Remove a tag (idempotent)
emacsclient -e '(bergheim/agent-org-remove-tag "docs/TODO.org" "TODO Heading" "autonomous")'
```

## Project Memory

### Structured files

| File | Purpose |
|------|---------|
| `docs/PROJECT.org` | Project context, architecture, key decisions |
| `docs/TODO.org` | Actionable work items |
| `docs/MEMORY.org` | Legacy shared conventions (being replaced by denote notes) |
| `docs/RESEARCH.org` | Legacy investigations (being replaced by denote notes) |

### Denote notes (`docs/notes/`)

Per-topic knowledge notes following denote's filename convention. Each note is a
single topic in its own file — no monolithic dumps. Notes are write-once: to add
to a topic, create a new note and reference the original.

**Filename format:** `YYYYMMDDTHHMMSS--title-slug__kind_topic1_topic2.org`

**Note kinds** (fixed vocabulary, always the first keyword):
`memory`, `research`, `decision`, `gotcha`, `convention`, `incident`

**Topic keywords** (free-form, project-specific):
`emacs`, `org`, `jolo`, `musl`, `evil`, `agent`, `skills`, `denote`, etc.

**Creating notes via emacsclient:**

```bash
emacsclient -e '(bergheim/agent-denote-create "docs/notes" "Title here" (quote ("kind" "topic1" "topic2")) "Body text.")'
```

**Finding notes:**

```bash
# All notes with keyword "emacs"
emacsclient -e '(bergheim/agent-denote-find "docs/notes" (quote ("emacs")))'

# Notes matching keyword + title pattern
emacsclient -e '(bergheim/agent-denote-find "docs/notes" (quote ("gotcha")) "evil")'

# List 10 most recent
emacsclient -e '(bergheim/agent-denote-list "docs/notes")'
```

**Linking notes:**

```bash
# Add links from one note to related notes (idempotent, appends "Related notes" section)
emacsclient -e '(bergheim/agent-denote-link "/abs/path/to/source.org" (quote ("/abs/path/to/target1.org" "/abs/path/to/target2.org")))'
```

Link when there is a real semantic relationship (one note explains, caused, or
depends on another). Do not link just because notes share a keyword.

**On session start:**
1. Read `docs/PROJECT.org` and `docs/TODO.org`
2. Scan note filenames: `(bergheim/agent-denote-list "docs/notes")`
3. Read full content of notes relevant to current task

**On discoveries:** Create a new denote note with the appropriate kind and topics.
Link to existing related notes. Do not append to existing notes or to `MEMORY.org`.

### Stash notes (`/workspaces/stash/notes/`)

Cross-project knowledge belongs in stash notes. If a discovery would still be
useful in an unrelated project or for host-level workflow, save it in
`/workspaces/stash/notes` instead of only in `docs/notes/`.

Use this heuristic:
- Would I want this loaded at session start in an unrelated project?

If yes, it belongs in stash. If the note depends on this repo's files, paths,
branches, or local architecture, it is project-specific and belongs in
`docs/notes/`.

It is fine to write both:
- a local incident note in `docs/notes/`
- a separate generalized note in `/workspaces/stash/notes/`

When working on shared tooling, devcontainer workflow, Emacs, org-mode, denote,
agent behavior, or other cross-project infrastructure, also scan stash note
filenames and read relevant stash notes before acting:

```bash
emacsclient -e '(bergheim/agent-denote-list "/workspaces/stash/notes" 15)'
```

### Personal memory

Agent-specific files (not shared):
- Claude: `.claude/MEMORY.md`
- Gemini: `.gemini/MEMORY.md`
- Codex: `.codex/MEMORY.md`
- Pi: `.pi/MEMORY.md`

Use personal memory for workflow preferences and agent-specific learnings.
Use denote notes for anything another agent would benefit from knowing.

## Emacs

Emacs runs as a daemon in the container. Use `emacsclient --eval '(expr)'` to query state, check modes, read variables, or run diagnostics — never ask the user to run `M-x` or `M-:` manually.

The real Emacs config lives on the host (`~/.config/emacs/`). The container copy at `.devcontainer/.emacs-config/` is not the source of truth. When config changes are needed, provide the snippet for the user to apply on the host.

## Project Defaults

**Port requirement:** When creating or scaffolding any project with a dev server (web apps, APIs, etc.), always use the `$PORT` environment variable. Each project gets a random port in the 4000-5000 range assigned at creation time.

```bash
# In your dev server config, always use $PORT
npm run dev -- --port $PORT
python -m http.server $PORT
flask run --port $PORT
```

Port assignment:
- `jolo create` / `jolo init` assigns a random port in 4000-5000, written to devcontainer.json
- The port is stable for the project lifetime (stored in config, not re-randomized)
- `jolo up` checks port availability before launching; errors if taken
- In spawn mode (`jolo spawn N`), each worktree gets base_port + offset (4000, 4001, ...)
- Ports 4000-5000 are forwarded from the container to the host and accessible via the Tailscale network

## Git Workflow

Keep a rebased, linear history. Work on feature branches, rebase onto `main` before merging, and use merge commits when combining multi-commit branches (to preserve the logical grouping). For single-commit branches, fast-forward merge is fine.

**Never merge branches into each other.** If you have multiple feature branches to land, merge them to main one at a time, rebasing each onto the updated main before merging. Do not create a "combined" branch by merging feature branches together — this produces a tangled commit graph that is hard to read and bisect.

```bash
# WRONG: merging branches into each other
git checkout feat-a && git merge feat-b && git merge feat-c  # tangled history

# RIGHT: merge to main sequentially
git checkout main && git merge --no-ff feat-a
git checkout feat-b && git rebase main
git checkout main && git merge --no-ff feat-b
# repeat for each branch
```

For bigger tasks, use TDD and commit frequently on the branch as you make progress.
**Default workflow: commit and push unless the user explicitly says not to.** If a remote exists, push after each meaningful commit so progress is visible and recoverable.

**Branch naming:**
- `feat/<slug>`
- `fix/<slug>`
- `docs/<slug>`
- `chore/<slug>`
- `refactor/<slug>`
- `test/<slug>`

**Worktree naming:**
- `wt/<prefix>/<slug>` (example: `wt/feat/auth`, `wt/docs/readme`)

```bash
git checkout feature-branch
git rebase main
git checkout main
git merge feature-branch          # fast-forward for single commit
git merge --no-ff feature-branch  # merge commit for multi-commit branches
```

**Worktree awareness:** Check `.git` at session start — if it's a file (not a directory), you are in a worktree. All worktrees live under `/workspaces/`. You cannot checkout `main` here. Find the main tree and merge there:

```bash
# Detect: file = worktree, directory = main repo
test -f .git && echo "worktree" || echo "main repo"

# Merge from a worktree
MAIN=$(git worktree list | awk '/\[main\]/{print $1}')
git rebase main && git -C "$MAIN" merge $(git branch --show-current)
```

## Build Commands

```bash
# Build with default user (tsb)
podman build -t emacs-gui .

# Build matching your host user (recommended)
podman build --build-arg USERNAME=$(whoami) --build-arg USER_ID=$(id -u) --build-arg GROUP_ID=$(id -g) -t emacs-gui .
```

## Testing

System Python on Alpine has no pytest and pip is blocked (externally-managed-environment). Use `uv` to run tests:

```bash
just test              # run all tests
just test-k "pattern"  # run tests matching keyword
just test-v            # verbose output
```

Test behavior, not scaffolding. Don't write tests for obvious error paths that just exercise guards you shouldn't have added in the first place. One test for the happy path is worth more than five tests for defensive branches.

## Running

```bash
jolo up    # start devcontainer with tmux layout
jolo up -d # start detached
```

## Architecture

**Key files:**
- `Containerfile` - Alpine-based image with Emacs, language servers, and dev tools
- `container/entrypoint.sh` - Container startup: GPG agent setup, DBus, keeps container alive
- `container/tmux-layout.sh` - Tmux session wrapper: starts tmuxinator layout, handles reattach and prompt mode
- `container/dev.yml` - Tmuxinator config: 7-window layout (emacs, claude, codex, gemini, pi, dev, shell)
- `container/e` - Smart Emacs launcher (GUI or terminal based on environment)
- `container/motd` - Message of the day shown on shell login
- `container/browser-check.js` - Browser automation CLI (Playwright + system Chromium)
- `container/notify` - Push notification on agent completion (ntfy)
- `container/db` - On-demand PostgreSQL (init/start/stop/status/log)
- `jolo.py` + `_jolo/` - Devcontainer CLI split into a package: `constants.py`, `cli.py`, `templates.py`, `container.py`, `setup.py`, `worktree.py`, `commands.py`

**Environment:**
- `EMACS_CONTAINER=1` - Set inside container, can be used by Emacs config to skip loading certain packages
- `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` - Passed through to container for AI tools
- `PNPM_HOME` - pnpm global package path (no sudo needed)
- `PGHOST=/tmp` - PostgreSQL Unix socket directory
- `LLAMA_HOST` - llama-swap (llama.cpp, OpenAI-compat) endpoint

## Notifications

Completion notifications use `ntfy.sh` with a default topic of `jolo`.
Use `test` only for ad-hoc/manual test pings (e.g., `NTFY_TOPIC=test`).

**Networking:**
- Each project gets a random port in 4000-5000 assigned at creation time, forwarded from container to host
- Use `$PORT` for dev servers - it's set in the container environment and accessible via Tailscale
- Example: run `npm run dev -- --port $PORT` and access from another machine via `http://<tailscale-ip>:$PORT`

## Installed Tools

Language servers: gopls, rust-analyzer, typescript-language-server, pyright, bash-language-server, yaml-language-server, dockerfile-language-server, ansible-language-server, py3-lsp-server

Runtimes: Go, Rust, Python, Ruby, Elixir/Erlang, Node.js, Bun, pnpm, mise (version manager)

Database: PostgreSQL 18 + pgvector (on-demand via `db start` or `just db`, data in `.devcontainer/.pgdata/`)

CLI: ripgrep, fd, eza, zoxide, jq, yq, gh, sqlite, cmake, tmux, tmuxinator, neovim (aliased as `vi`/`vim`), air (Go live-reload), postgresql-client

AI tools: claude (Claude Code CLI), codex-cli (@openai/codex), gemini-cli (@google/gemini-cli), pi (@mariozechner/pi-coding-agent)

Spell-checking: aspell, hunspell, enchant2

Linting: pre-commit, ruff (Python), golangci-lint (Go), shellcheck (shell), hadolint (Dockerfile), yamllint (YAML), ansible-lint (Ansible)

Browser automation: browser-check (uses Playwright with system Chromium), pa11y (WCAG 2.2 AA accessibility auditing)

Image tooling: vips/vipsthumbnail, avifenc/avifdec (AVIF), cwebp/dwebp (WebP). Prefer AVIF > WebP > PNG/JPEG. Do not add ImageMagick or Pillow unless the project explicitly requires them.

## Browser Automation Tool Guide

Use `playwright-cli` for stateful browser automation with low token usage (artifacts written to `.playwright-cli/`). Use `browser-check` for quick stateless audits.

### Task → Tool

| Task | Command |
|------|---------|
| **Interactive Flow** | **Playwright CLI** (`playwright-cli`) |
| Check what's on page | `browser-check URL --describe` |
| Take screenshot | `browser-check URL --screenshot` |
| Full page screenshot | `browser-check URL --screenshot --full-page` |
| Generate PDF | `browser-check URL --pdf` |
| Get ARIA tree | `browser-check URL --aria` |
| Interactive elements only | `browser-check URL --aria --interactive` |
| Capture console logs | `browser-check URL --console` |
| Capture JS errors | `browser-check URL --errors` |
| JSON output for scripts | `browser-check URL --json --console --errors` |

### Playwright CLI

Stateful browser automation via local session artifacts on disk (`.playwright-cli/`).

```bash
# Open a session and inspect interactive refs
playwright-cli open https://example.com
playwright-cli snapshot

# Interact using refs from the snapshot
playwright-cli click e1
playwright-cli fill e2 "hello"

# Capture artifacts and close
playwright-cli screenshot
playwright-cli close
```

### browser-check

Stateless browser automation using Playwright with system Chromium. Each command launches a fresh browser.

```bash
# Basic page inspection
browser-check https://example.com --describe

# Screenshot with custom output
browser-check https://example.com --screenshot --output shot.png
browser-check https://example.com --screenshot --full-page --output full.png

# PDF generation
browser-check https://example.com --pdf --output doc.pdf

# ARIA accessibility tree (93% less context than raw HTML)
browser-check https://example.com --aria
browser-check https://example.com --aria --interactive  # just buttons, links, inputs

# Debug a page - capture console and errors
browser-check https://localhost:4000 --console --errors

# JSON output for programmatic use
browser-check https://myapp.com --console --errors --aria --json

# Wait longer for slow pages
browser-check https://slow-site.com --wait 3000 --timeout 60000
```

### Common Patterns

**Check if dev server is up:**
```bash
browser-check http://localhost:4000 --describe --console --errors
```

**Debug JavaScript errors:**
```bash
browser-check https://myapp.com --errors --console
```

**Get page structure for LLM:**
```bash
browser-check https://example.com --aria --interactive --json
```

**Screenshot with error checking:**
```bash
browser-check https://myapp.com --screenshot --errors --output debug.png
```

### Limitations

- **Stateless**: `browser-check` commands launch fresh browser (no persistent sessions).
- For advanced flows beyond CLI commands, write a Node.js Playwright script.

## Code Quality Best Practices

**Always set up pre-commit hooks** when scaffolding or working on a project. This catches issues before commits. The specific hooks depend on the project type.

- **Never skip hooks**: NEVER use `git commit --no-verify`. Pre-commit hooks (ruff, format, tests, codespell) are the guardrails that keep code clean. If a hook blocks the commit, fix the underlying issue — add the word to the codespell allowlist, fix the lint error, fix the failing test. Skipping hooks to save time means shipping broken formatting, lint errors, and test failures that compound into a mess. No exceptions.

### When to add hooks (decision heuristics)

**Every project** gets basic hygiene hooks:
```yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v5.0.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-added-large-files
```

**Code projects** - add language-specific linters based on files present:

| Files | Linter | Hook repo |
|-------|--------|-----------|
| `*.py` | ruff | `https://github.com/astral-sh/ruff-pre-commit` |
| `*.go` | golangci-lint | `https://github.com/golangci/golangci-lint` |
| `*.rs` | clippy/rustfmt | `https://github.com/doublify/pre-commit-rust` |
| `*.ts/*.js` | biome | `https://github.com/biomejs/biome` |
| `*.sh` | shellcheck | `https://github.com/shellcheck-py/shellcheck-py` |
| `Dockerfile` | hadolint | `https://github.com/hadolint/hadolint` |
| `*.yaml/*.yml` | yamllint | `https://github.com/adrienverge/yamllint` |
| `playbook*.yml` | ansible-lint | `https://github.com/ansible/ansible-lint` |

**Prose projects** (docs, blogs, wikis) - add writing-focused tools:
```yaml
repos:
  - repo: https://github.com/igorshubovych/markdownlint-cli
    rev: v0.43.0
    hooks:
      - id: markdownlint-fix
  - repo: https://github.com/codespell-project/codespell
    rev: v2.3.0
    hooks:
      - id: codespell
```

**Mixed projects** - combine both code and prose hooks as needed.

### Setup

```bash
# Initialize hooks (run once per project)
pre-commit install

# Run on all files (useful after adding new hooks)
pre-commit run --all-files
```

When scaffolding new projects:
1. Detect project type from files or user intent
2. Create `.pre-commit-config.yaml` with appropriate hooks
3. Add language-specific config (`pyproject.toml`, `biome.json`, etc.) if needed
4. Run `pre-commit install`

This is especially important in AI-assisted development where code is generated quickly - linters catch issues before they're committed.

## jolo - Devcontainer Launcher

Install: `ln -s $(pwd)/jolo.py ~/.local/bin/jolo`

```bash
# Basic usage
jolo up                   # start devcontainer in current project
jolo create newproject    # scaffold new project
jolo tree feature-x       # create worktree + devcontainer
jolo list                 # show containers/worktrees
jolo attach               # pick a running container (sorted by MRU)
jolo down                 # stop container

# AI prompt mode (starts agent in detached tmux)
jolo up -p "add user auth"       # run AI with prompt
jolo tree feat -p "add OAuth"    # worktree + prompt
jolo create app -p "scaffold"    # new project + prompt
jolo up --agent gemini -p "..."  # use different agent (default: claude)

# Spawn mode (multiple parallel agents)
jolo spawn 5 -p "implement X"          # 5 random-named worktrees
jolo spawn 3 --prefix auth -p "..."    # auth-1, auth-2, auth-3
# Agents round-robin through configured list (claude, gemini, codex, pi)
# Each gets unique PORT (4000, 4001, 4002, ...)

# Other options
jolo tree feat --from develop     # branch worktree from specific ref
jolo up -d                        # start detached (no tmux attach)
jolo up --shell                   # exec zsh directly (no tmux)
jolo up --run claude              # exec command directly (no tmux)
jolo up --run "npm test"          # run arbitrary command
jolo init                         # initialize git + devcontainer in current dir
jolo up --recreate                # sync config from template and recreate container
jolo a --recreate                 # pick container, sync + recreate, reattach
jolo prune                        # cleanup stopped/orphan containers and worktrees
jolo destroy                      # nuclear: stop + rm all containers for project
jolo list --all                   # show all containers globally
jolo down --all                   # stop all containers for project
jolo up -v                        # verbose mode (print commands)

# Mount and copy options
jolo up --mount ~/data:data          # mount ~/data to workspace/data (rw)
jolo up --mount ~/data:data:ro       # mount ~/data to workspace/data (readonly)
jolo up --mount ~/data:/mnt/data     # mount to absolute path
jolo up --copy ~/config.json         # copy file to workspace root
jolo up --copy ~/config.json:app/    # copy to workspace/app/config.json

# Autonomous dispatch from TODO.org
jolo autonomous                       # scan docs/TODO.org, dispatch :autonomous: items
jolo autonomous --dry-run             # preview what would fire
jolo autonomous --agents claude,codex # round-robin across a specific agent list
# Requires host Emacs daemon to have loaded container/agent-helpers.el
# so the CLI's emacsclient calls can reach the selector/mark helpers.
# Host is responsible for scheduling (systemd timer, cron, ...).
```

**Security model:**
- **No X11 access** — jolo containers have no X11 socket mount and no `DISPLAY` variable. This prevents X11 keylogging, screenshot capture, and input injection. Wayland access is conditional — the socket is only mounted when `WAYLAND_DISPLAY` is set on the host. Wayland's per-surface isolation makes this safe (unlike X11).
- AI credentials copied (not mounted) to `.devcontainer/` at launch:
  - Claude credentials: `.credentials.json` mounted RW from host (token refreshes persist), `settings.json` copied to `.claude-cache/` (container-specific hooks), `statsig/` mounted RO from host, `.claude.json` copied (MCP injection)
  - Gemini: `.gemini-cache/` copied
  - Codex: `.codex-cache/` copied
  - Pi: `.pi-cache/` copied
- Claude history/state is ephemeral per-project (no cross-project contamination)
- GPG keyring (`pubring.kbx`, `trustdb.gpg`) mounted read-only; the agent socket is forwarded for signing. The `trustdb not writable` warning is expected and harmless.
- Emacs config copied, package dirs mounted readonly from ~/.cache/emacs/
- Shell history persisted per-project in `.devcontainer/.zsh-state/`

**Emacs config isolation:**
- Config (~/.config/emacs) copied to `.devcontainer/.emacs-config/` - writable
- Package dirs mounted read-write from `~/.cache/emacs-container/` (NOT `~/.cache/emacs/`):
  - elpaca/ (package manager repos/builds)
  - tree-sitter/ (grammar files)
- Separate from host Emacs cache to avoid version/libc mismatches (host=Emacs 31/glibc, container=30.x/musl)
- First boot is slow (elpaca builds everything), subsequent boots reuse the shared cache
- Cache dir (`.devcontainer/.emacs-cache/`) is fresh per-container
- Changes to config stay in project, don't affect host
