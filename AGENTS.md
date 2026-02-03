# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a containerized Emacs GUI environment on Alpine Linux, designed as a devcontainer for AI-assisted development. The container includes Claude Code CLI pre-configured in YOLO mode (`--dangerously-skip-permissions`).

## Project Defaults

**Port requirement:** When creating or scaffolding any project with a dev server (web apps, APIs, etc.), always use the `$PORT` environment variable. This defaults to 4000 but is set dynamically in spawn mode to avoid conflicts.

```bash
# In your dev server config, always use $PORT
npm run dev -- --port $PORT
python -m http.server $PORT
flask run --port $PORT
```

In spawn mode (`jolo --spawn N`), each worktree gets a unique port:
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
- `Containerfile` - Alpine-based image with Emacs PGTK, language servers, and dev tools
- `entrypoint.sh` - Container startup: display detection, GPG agent setup, tmux/emacs launch
- `start-emacs.sh` - Host-side launcher that sets up yadm worktree sandbox for Emacs config
- `jolo.py` - Devcontainer CLI for project-based development with git worktree support
- `e` - Smart Emacs launcher (GUI or terminal based on environment)

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

Linting: ruff, pre-commit

## Code Quality Best Practices

**Always use a linter with git pre-commit hooks** when working in a programming environment. This ensures code quality is verified before commits, catching issues early.

For Python projects, the container includes ruff and pre-commit. To set up:

```bash
# Initialize pre-commit hooks (run once per project)
pre-commit install
```

A `.pre-commit-config.yaml` file should be in the project root. Example configuration:

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.8.6
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
```

When scaffolding new projects, always include:
1. A `.pre-commit-config.yaml` with appropriate linters for the language
2. A `pyproject.toml` (Python) or equivalent config for linter rules
3. Run `pre-commit install` to activate the hooks

This is especially important in AI-assisted development where code may be generated quickly - the linter catches issues before they're committed.

## jolo.py - Devcontainer Launcher

Install: `ln -s $(pwd)/jolo.py ~/.local/bin/jolo`

```bash
# Basic usage
jolo                      # start devcontainer in current project
jolo --tree feature-x     # create worktree + devcontainer
jolo --create newproject  # scaffold new project
jolo --list               # show containers/worktrees
jolo --stop               # stop container

# AI prompt mode (starts agent in detached tmux)
jolo -p "add user auth"           # run AI with prompt
jolo --tree feat -p "add OAuth"   # worktree + prompt
jolo --create app -p "scaffold"   # new project + prompt
jolo --agent gemini -p "..."      # use different agent (default: claude)

# Spawn mode (multiple parallel agents)
jolo --spawn 5 -p "implement X"          # 5 random-named worktrees
jolo --spawn 3 --prefix auth -p "..."    # auth-1, auth-2, auth-3
# Agents round-robin through configured list (claude, gemini, codex)
# Each gets unique PORT (4000, 4001, 4002, ...)

# Other options
jolo --tree feat --from develop   # branch worktree from specific ref
jolo --attach                     # attach to running container
jolo -d                           # start detached (no tmux attach)
jolo --shell                      # exec zsh directly (no tmux)
jolo --run claude                 # exec command directly (no tmux)
jolo --run "npm test"             # run arbitrary command
jolo --init                       # initialize git + devcontainer in current dir
jolo --sync                       # regenerate .devcontainer from template
jolo --new                        # remove existing container before starting
jolo --sync --new                 # regenerate config and rebuild
jolo --prune                      # cleanup stopped containers/stale worktrees
jolo --destroy                    # nuclear: stop + rm all containers for project
jolo --list --all                 # show all containers globally
jolo --stop --all                 # stop all containers for project
jolo -v                           # verbose mode (print commands)
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
- Package dirs mounted readonly from host ~/.cache/emacs/:
  - elpaca/ (package manager repos/builds)
  - tree-sitter/ (grammar files)
- Cache dir (`.devcontainer/.emacs-cache/`) is fresh per-container
- Changes to config stay in project, don't affect host
