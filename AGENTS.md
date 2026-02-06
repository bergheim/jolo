# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> **Note:** This is a META-PROJECT for building the AI development container environment.
> It is NOT meant for general development. For projects created with `jolo create`,
> see `templates/AGENTS.md` which gets copied to new projects.

## Project Overview

This repo builds and maintains the containerized Emacs GUI environment on Alpine Linux (musl-based), designed as a devcontainer for AI-assisted development. Alpine provides excellent package coverage and small image size. Browser automation uses Playwright with system Chromium. The container includes Claude Code CLI pre-configured in YOLO mode (`--dangerously-skip-permissions`).

**What this repo produces:**
- Container image (`emacs-gui`) with all dev tools pre-installed
- `jolo.py` CLI for launching devcontainers with git worktree support
- Templates for new projects (`templates/`)

## File Format Preferences

Prefer org-mode (`.org`) over markdown for project documentation, TODOs, and notes. This is an Emacs-centric project.

## Project Defaults

**Port requirement:** When creating or scaffolding any project with a dev server (web apps, APIs, etc.), always use the `$PORT` environment variable. This defaults to 4000 but is set dynamically in spawn mode to avoid conflicts.

```bash
# In your dev server config, always use $PORT
npm run dev -- --port $PORT
python -m http.server $PORT
flask run --port $PORT
```

In spawn mode (`jolo spawn N`), each worktree gets a unique port:
- worktree-1: PORT=4000
- worktree-2: PORT=4001
- worktree-3: PORT=4002
- etc.

Ports 4000-5000 are forwarded from the container to the host and accessible via the Tailscale network.

## Build Commands

```bash
# Build with default user (tsb)
podman build -t emacs-gui .

# Build matching your host user (recommended)
podman build --build-arg USERNAME=$(whoami) --build-arg USER_ID=$(id -u) --build-arg GROUP_ID=$(id -g) -t emacs-gui .
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
- `container/entrypoint.sh` - Container startup: display detection, GPG agent setup, tmux/emacs launch
- `container/e` - Smart Emacs launcher (GUI or terminal based on environment)
- `container/motd` - Message of the day shown on shell login
- `container/browser-check.js` - Browser automation CLI (Playwright + system Chromium)
- `start-emacs.sh` - Host-side launcher that sets up yadm worktree sandbox for Emacs config
- `jolo.py` - Devcontainer CLI for project-based development with git worktree support

**Sandbox mechanism (start-emacs.sh):**
The host script creates a yadm worktree at `~/.cache/aimacs-lyra` on branch `lyra-experiments`. This gives Claude a copy of the Emacs config to modify freely without affecting the real dotfiles. The `private.el` secrets file is deleted from the worktree.

**Environment:**
- `EMACS_CONTAINER=1` - Set inside container, can be used by Emacs config to skip loading certain packages
- `START_EMACS=true` - If set, entrypoint launches Emacs daemon; otherwise defaults to tmux
- `ANTHROPIC_API_KEY`, `OPENAI_API_KEY` - Passed through to container for AI tools
- `NPM_CONFIG_PREFIX`, `PNPM_HOME` - User-local package manager paths (no sudo needed)

**Networking:**
- Ports 4000-5000 are forwarded from the container to the host
- Use these for dev servers (web apps, APIs, etc.) - they're accessible from the Tailscale network
- Example: run `npm run dev -- --port 4000` and access from another machine via `http://<tailscale-ip>:4000`

## Installed Tools

Language servers: gopls, rust-analyzer, typescript-language-server, pyright, bash-language-server, yaml-language-server, dockerfile-language-server, ansible-language-server, py3-lsp-server

Runtimes: Go, Rust, Python, Node.js, Bun, pnpm, mise (version manager)

CLI: ripgrep, fd, eza, zoxide, jq, yq, gh, sqlite, cmake, tmux, neovim (aliased as `vi`)

AI tools: claude (Claude Code CLI), codex-cli (@openai/codex), gemini-cli (@google/gemini-cli)

Spell-checking: aspell, hunspell, enchant2

Linting: pre-commit, ruff (Python), golangci-lint (Go), shellcheck (shell), hadolint (Dockerfile), yamllint (YAML), ansible-lint (Ansible)

Browser automation: browser-check (uses Playwright with system Chromium)

## Browser Automation Tool Guide

Use `browser-check` for browser automation. It provides ARIA snapshots with 93% less context than raw HTML.

### Task → Tool

| Task | Command |
|------|---------|
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

- **Stateless**: Each command launches fresh browser (no persistent sessions)
- **No interaction**: Cannot click buttons or fill forms (use Playwright API directly for that)
- For complex multi-step flows, write a Node.js script using Playwright directly

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

## jolo.py - Devcontainer Launcher

Install: `ln -s $(pwd)/jolo.py ~/.local/bin/jolo`

```bash
# Basic usage
jolo                      # start devcontainer in current project
jolo tree feature-x       # create worktree + devcontainer
jolo create newproject    # scaffold new project
jolo list                 # show containers/worktrees
jolo stop                 # stop container

# AI prompt mode (starts agent in detached tmux)
jolo -p "add user auth"           # run AI with prompt
jolo tree feat -p "add OAuth"     # worktree + prompt
jolo create app -p "scaffold"     # new project + prompt
jolo --agent gemini -p "..."      # use different agent (default: claude)

# Spawn mode (multiple parallel agents)
jolo spawn 5 -p "implement X"          # 5 random-named worktrees
jolo spawn 3 --prefix auth -p "..."    # auth-1, auth-2, auth-3
# Agents round-robin through configured list (claude, gemini, codex)
# Each gets unique PORT (4000, 4001, 4002, ...)

# Other options
jolo tree feat --from develop     # branch worktree from specific ref
jolo attach                       # attach to running container
jolo -d                           # start detached (no tmux attach)
jolo --shell                      # exec zsh directly (no tmux)
jolo --run claude                 # exec command directly (no tmux)
jolo --run "npm test"             # run arbitrary command
jolo init                         # initialize git + devcontainer in current dir
jolo sync                         # regenerate .devcontainer from template
jolo --new                        # remove existing container before starting
jolo sync --new                   # regenerate config and rebuild
jolo prune                        # cleanup stopped containers/stale worktrees
jolo destroy                      # nuclear: stop + rm all containers for project
jolo list --all                   # show all containers globally
jolo stop --all                   # stop all containers for project
jolo -v                           # verbose mode (print commands)

# Mount and copy options
jolo --mount ~/data:data          # mount ~/data to workspace/data (rw)
jolo --mount ~/data:data:ro       # mount ~/data to workspace/data (readonly)
jolo --mount ~/data:/mnt/data     # mount to absolute path
jolo --copy ~/config.json         # copy file to workspace root
jolo --copy ~/config.json:app/    # copy to workspace/app/config.json
```

**Security model:**
- AI credentials copied (not mounted) to `.devcontainer/` at launch:
  - Claude: `.claude-cache/` and `.claude.json`
  - Gemini: `.gemini-cache/`
- Container cannot write back to host credential directories
- Claude history/state is ephemeral per-project (no cross-project contamination)
- Emacs config copied, package dirs mounted readonly from ~/.cache/emacs/
- Shell history persisted per-project in `.devcontainer/.histfile`

**Emacs config isolation:**
- Config (~/.config/emacs) copied to `.devcontainer/.emacs-config/` - writable
- Package dirs mounted read-write from `~/.cache/emacs-container/` (NOT `~/.cache/emacs/`):
  - elpaca/ (package manager repos/builds)
  - tree-sitter/ (grammar files)
- Separate from host Emacs cache to avoid version/libc mismatches (host=Emacs 31/glibc, container=30.x/musl)
- First boot is slow (elpaca builds everything), subsequent boots reuse the shared cache
- Cache dir (`.devcontainer/.emacs-cache/`) is fresh per-container
- Changes to config stay in project, don't affect host
