# Project Context

## What This Is

A meta-project that builds and maintains a containerized AI-assisted development environment on Alpine Linux. It produces:

- **Container image** (`emacs-gui`) — Alpine-based with Emacs, language servers, and dev tools
- **`jolo` CLI** (`jolo.py` + `_jolo/` package) — devcontainer launcher with git worktree support, AI prompt mode, and multi-agent spawn
- **Project templates** (`templates/`) — scaffolding for new projects

## Tech Stack

- **Language:** Python 3 (CLI), Shell (container scripts)
- **Container:** Alpine Linux, Podman (rootless), devcontainer spec
- **Testing:** pytest via `uv run pytest` (Alpine has no system pip)
- **Linting:** ruff (Python), shellcheck (shell), pre-commit hooks
- **Task runner:** just (`justfile`)
- **AI agents:** Claude Code, Gemini CLI, Codex CLI — all pre-installed in container

## Architecture

```
jolo.py                    # CLI entry point
_jolo/                     # Package modules
  cli.py                   # Argument parsing
  commands.py              # Subcommand implementations (up, create, tree, spawn, etc.)
  container.py             # Podman/devcontainer operations
  setup.py                 # Credential and config staging
  worktree.py              # Git worktree management
  templates.py             # Project scaffolding
  constants.py             # Shared constants, word lists

container/                 # Files baked into the container image
  entrypoint.sh            # Container startup (GPG, DBus, sleep)
  tmux-layout.sh           # Tmux session wrapper (tmuxinator)
  dev.yml                  # Tmuxinator config: 5-window layout
  motd                     # Message of the day script
  notify                   # Completion notification (ntfy.sh + bell + TTS)
  e                        # Smart Emacs launcher
  browser-check.js         # Playwright browser automation

Containerfile              # Alpine image definition
start-emacs.sh             # Host-side GUI Emacs launcher (sandbox)
templates/                 # Scaffolded into new projects by jolo create
```

## Key Patterns

- **Devcontainer spec compliance** — `.devcontainer/devcontainer.json` drives container config
- **Tmuxinator layout** — 5 windows: emacs, claude, gemini, codex, shell
- **Prompt mode** — `jolo up -p "..."` writes `.agent-prompt` file, tmux-layout.sh injects it into the agent command
- **Spawn mode** — `jolo spawn N` creates N worktrees with round-robin agents and sequential ports
- **Credential isolation** — AI credentials copied (not mounted) per-container, ephemeral
- **Port assignment** — random port in 4000-5000 per project, stored in devcontainer.json

## Testing

```bash
just test              # run all tests (~280 tests)
just test-k "pattern"  # run tests matching keyword
just test-v            # verbose
```

## Conventions

- Org-mode (`.org`) for documentation, not markdown
- Comments explain *why*, never *what*
- No backward-compatibility shims — just change it
- Linear git history (rebase + merge commits for multi-commit branches)
