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
- `.devcontainer/` - VS Code DevContainers configuration

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
