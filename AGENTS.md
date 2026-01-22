# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a containerized Emacs GUI environment on Alpine Linux, designed as a devcontainer for AI-assisted development. The container includes Claude Code CLI pre-configured in YOLO mode (`--dangerously-skip-permissions`).

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

**Networking:**
- Ports 4000-5000 are forwarded from the container to the host
- Use these for dev servers (web apps, APIs, etc.) - they're accessible from the Tailscale network
- Example: run `npm run dev -- --port 4000` and access from another machine via `http://<tailscale-ip>:4000`

## Installed Tools

Language servers: gopls, rust-analyzer, typescript-language-server, pyright, bash-language-server, yaml-language-server, dockerfile-language-server, ansible-language-server, py3-lsp-server

Runtimes: Go, Rust, Python, Node.js, Bun

CLI: ripgrep, fd, eza, zoxide, jq, yq, gh, sqlite, cmake, tmux, neovim

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

# Other options
jolo --tree feat --from develop   # branch worktree from specific ref
jolo --attach                     # attach to running container
jolo -d                           # start detached (no tmux attach)
jolo --sync --new                 # regenerate config and rebuild
jolo --prune                      # cleanup stopped containers/stale worktrees
jolo --destroy                    # nuclear: stop + rm all containers for project
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
