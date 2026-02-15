# AGENTS.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> **Note:** This is a META-PROJECT for building the AI development container environment.
> It is NOT meant for general development. For projects created with `jolo create`,
> see `templates/AGENTS.md` which gets copied to new projects.

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

## Backward Compatibility

This project is in heavy development. Do NOT worry about backward compatibility — just make the change directly. No aliases, shims, deprecation warnings, or re-exports for old names.

## Comments

Only comment *why*, never *what*. Do not add comments that restate the code. Do not add comments that narrate the conversation or explain context that is obvious from reading the code. `printf '\a'` does not need a comment explaining what a terminal bell is, or if it works through tmux (which was in  the agent conversation). If a comment is needed at all, keep it to a few words — not a sentence.

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

All tasks, plans, and TODOs go in `TODO.org` (org-mode format). Use standard org TODO states (`TODO`, `DONE`) and org structure (headings, checklists, properties). Always check `TODO.org` for existing tasks before starting work, and update it as tasks are completed or new ones are identified.

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

For bigger tasks, use TDD and commit frequently on the branch as you make progress.

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

**Worktree awareness:** If `.git` is a file (not a directory), you are in a worktree — you cannot checkout `main` here. Find the main tree and merge there:

```bash
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

## Running

```bash
# Using the wrapper script (handles Wayland, env vars, volume mounts)
./start-emacs.sh

# Or via VS Code DevContainers
# Open in VS Code and use "Reopen in Container"
```

## Architecture

**Key files:**
- `Containerfile` - Alpine-based image with Emacs, language servers, and dev tools
- `container/entrypoint.sh` - Container startup: GPG agent setup, DBus, keeps container alive
- `container/tmux-layout.sh` - Tmux session wrapper: starts tmuxinator layout, handles reattach and prompt mode
- `container/dev.yml` - Tmuxinator config: 6-window layout (emacs, claude, gemini, codex, pi, shell)
- `container/e` - Smart Emacs launcher (GUI or terminal based on environment)
- `container/motd` - Message of the day shown on shell login
- `container/browser-check.js` - Browser automation CLI (Playwright + system Chromium)
- `start-emacs.sh` - Host-side launcher that sets up yadm worktree sandbox for Emacs config
- `jolo.py` + `_jolo/` - Devcontainer CLI split into a package: `constants.py`, `cli.py`, `templates.py`, `container.py`, `setup.py`, `worktree.py`, `commands.py`

**Sandbox mechanism (start-emacs.sh):**
The host script creates a yadm worktree at `~/.cache/aimacs-lyra` on branch `lyra-experiments`. This gives Claude a copy of the Emacs config to modify freely without affecting the real dotfiles. The `private.el` secrets file is deleted from the worktree.

**Environment:**
- `EMACS_CONTAINER=1` - Set inside container, can be used by Emacs config to skip loading certain packages
- `START_EMACS=true` - If set, entrypoint launches Emacs daemon; otherwise tmuxinator creates 6-window layout (emacs, claude, gemini, codex, pi, shell)
- `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` - Passed through to container for AI tools
- `PNPM_HOME` - pnpm global package path (no sudo needed)

## Notifications

Completion notifications use `ntfy.sh` with a default topic of `jolo`.
Use `test` only for ad-hoc/manual test pings (e.g., `NTFY_TOPIC=test`).

**Networking:**
- Each project gets a random port in 4000-5000 assigned at creation time, forwarded from container to host
- Use `$PORT` for dev servers - it's set in the container environment and accessible via Tailscale
- Example: run `npm run dev -- --port $PORT` and access from another machine via `http://<tailscale-ip>:$PORT`

## Installed Tools

Language servers: gopls, rust-analyzer, typescript-language-server, pyright, bash-language-server, yaml-language-server, dockerfile-language-server, ansible-language-server, py3-lsp-server

Runtimes: Go, Rust, Python, Ruby, Node.js, Bun, pnpm, mise (version manager)

CLI: ripgrep, fd, eza, zoxide, jq, yq, gh, sqlite, cmake, tmux, tmuxinator, neovim (aliased as `vi`/`vim`), air (Go live-reload)

AI tools: claude (Claude Code CLI), codex-cli (@openai/codex), gemini-cli (@google/gemini-cli), pi (@mariozechner/pi-coding-agent)

Spell-checking: aspell, hunspell, enchant2

Linting: pre-commit, ruff (Python), golangci-lint (Go), shellcheck (shell), hadolint (Dockerfile), yamllint (YAML), ansible-lint (Ansible)

Browser automation: browser-check (uses Playwright with system Chromium)

## Browser Automation Tool Guide

Use `browser-check` for browser automation. It provides ARIA snapshots with 93% less context than raw HTML.

### Task → Tool

| Task | Command |
|------|---------|
| **Interactive Flow** | **Playwright MCP** (pre-configured) |
| Check what's on page | `browser-check URL --describe` |
| Take screenshot | `browser-check URL --screenshot` |
| Full page screenshot | `browser-check URL --screenshot --full-page` |
| Generate PDF | `browser-check URL --pdf` |
| Get ARIA tree | `browser-check URL --aria` |
| Interactive elements only | `browser-check URL --aria --interactive` |
| Capture console logs | `browser-check URL --console` |
| Capture JS errors | `browser-check URL --errors` |
| JSON output for scripts | `browser-check URL --json --console --errors` |

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

- **Stateless**: `browser-check` commands launch fresh browser (no persistent sessions). Use Playwright MCP for stateful sessions.
- For complex multi-step flows where MCP is not sufficient, write a Node.js script using Playwright directly.

## Code Quality Best Practices

**Always set up pre-commit hooks** when scaffolding or working on a project. This catches issues before commits. The specific hooks depend on the project type.

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
jolo attach               # pick a running container and attach to it
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
jolo up --sync                    # regenerate .devcontainer from template
jolo up --sync --new               # regenerate config and rebuild
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
```

**Security model:**
- **No X11 access** — jolo containers have no X11 socket mount and no `DISPLAY` variable. This prevents X11 keylogging, screenshot capture, and input injection by anything running in the container. GUI Emacs is only available via `start-emacs.sh` (the sandbox path that intentionally grants display access).
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
