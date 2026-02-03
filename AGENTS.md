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

Linting: pre-commit, ruff (Python), golangci-lint (Go), shellcheck (shell), hadolint (Dockerfile), yamllint (YAML), ansible-lint (Ansible)

Browser automation: playwright, agent-browser, webctl

## Browser Automation Tool Guide

Three browser tools are available, each with different strengths. Choose based on your task.

### Quick Reference: Task to Tool

| Task | Best Tool | Why |
|------|-----------|-----|
| Take a screenshot | Playwright | Native screenshot support, reliable |
| Click a button/link | agent-browser | ARIA snapshot finds elements reliably |
| Fill out a form | agent-browser | Handles multi-step interactions well |
| Verify page content exists | WebCtl | Filtered output, fast verification |
| Extract specific text | WebCtl | Precise ARIA selectors |
| Debug visual layout | Playwright | Screenshots show actual rendering |
| Navigate complex SPA | agent-browser | Waits for dynamic content automatically |
| Scrape data from table | WebCtl | Structured output from ARIA tree |
| Test responsive design | Playwright | Viewport control + screenshots |
| Limited context window | agent-browser | 93% less context than raw HTML |
| Login flow automation | agent-browser | Stateful session, handles redirects |
| PDF generation | Playwright | Native PDF export |

### Playwright CLI

**Best for:** Screenshots, PDFs, visual testing, viewport manipulation, low-level control.

Playwright provides full browser automation with pixel-perfect screenshots. Use when you need visual output or precise control over browser state.

```bash
# Take a screenshot
npx playwright screenshot https://example.com screenshot.png

# Screenshot with specific viewport
npx playwright screenshot --viewport-size=1280,720 https://example.com output.png

# Full page screenshot (captures scrollable content)
npx playwright screenshot --full-page https://example.com full.png

# Generate PDF
npx playwright pdf https://example.com output.pdf

# Wait for specific element before screenshot
npx playwright screenshot --wait-for-selector=".loaded" https://example.com output.png

# Execute JavaScript and capture result
npx playwright evaluate "document.title" https://example.com
```

**When to choose Playwright:**
- Need visual proof of page state (screenshots)
- Debugging CSS/layout issues
- Generating PDFs from web pages
- Need to test specific viewport sizes
- Require JavaScript evaluation
- Building test artifacts for CI

### agent-browser (Vercel)

**Best for:** Interactive automation, form filling, clicking, navigation - especially when context window is limited.

agent-browser uses ARIA snapshots instead of raw HTML, reducing context by ~93%. It understands the page semantically and handles dynamic content well.

```bash
# Navigate and describe page
agent-browser navigate "https://example.com" --describe

# Click an element (by visible text or ARIA label)
agent-browser click "Sign In"

# Fill a form field
agent-browser fill "Email" "user@example.com"

# Type into focused element
agent-browser type "search query"

# Press keyboard keys
agent-browser press "Enter"

# Get page snapshot (ARIA tree - compact representation)
agent-browser snapshot

# Scroll the page
agent-browser scroll down
agent-browser scroll to "Footer"

# Wait for element
agent-browser wait "Success message"

# Chain commands for complex flows
agent-browser navigate "https://app.example.com/login" && \
agent-browser fill "Username" "admin" && \
agent-browser fill "Password" "secret" && \
agent-browser click "Log In" && \
agent-browser wait "Dashboard"
```

**When to choose agent-browser:**
- Automating multi-step workflows (login, checkout, etc.)
- Working with SPAs/dynamic content
- Context window is limited (ARIA snapshots are compact)
- Need to interact with elements by their accessible name
- Form filling and submission
- Don't need visual output, just need actions to succeed

### WebCtl

**Best for:** Reading page content, verifying specific elements exist, extracting structured data.

WebCtl provides filtered, structured output using ARIA selectors. Good for verification and data extraction without full automation overhead.

```bash
# Get page content (filtered, readable)
webctl get https://example.com

# Get specific element by ARIA selector
webctl get https://example.com --selector="button[name='Submit']"

# Get all links
webctl get https://example.com --selector="link"

# Get form inputs
webctl get https://example.com --selector="textbox"

# Get headings for page structure
webctl get https://example.com --selector="heading"

# Output as JSON for parsing
webctl get https://example.com --json

# Check if element exists (useful for assertions)
webctl get https://example.com --selector="alert" --exists
```

**When to choose WebCtl:**
- Verifying specific content exists on page
- Extracting text from known elements
- Getting page structure (headings, links, forms)
- Need machine-readable output (JSON)
- Quick content checks without full browser session
- Scraping accessible data from static pages

### Decision Flowchart

```
Need visual output (screenshot/PDF)?
  YES -> Playwright
  NO  -> Continue

Need to interact (click/fill/navigate)?
  YES -> Is context window limited?
         YES -> agent-browser (93% less context)
         NO  -> agent-browser (better element finding)
  NO  -> Continue

Need to verify/extract content?
  YES -> WebCtl (filtered, structured output)
  NO  -> Start with agent-browser snapshot to understand page
```

### Common Patterns

**Verify a deployment is live:**
```bash
webctl get https://myapp.com --selector="heading" --exists
```

**Take screenshot of logged-in state:**
```bash
agent-browser navigate "https://app.com/login" && \
agent-browser fill "Email" "$EMAIL" && \
agent-browser fill "Password" "$PASS" && \
agent-browser click "Sign In" && \
agent-browser wait "Dashboard"
# Then use playwright for screenshot of current state
npx playwright screenshot --save-storage=auth.json https://app.com/dashboard dash.png
```

**Extract all links from a page:**
```bash
webctl get https://docs.example.com --selector="link" --json | jq '.[].href'
```

**Fill and submit a contact form:**
```bash
agent-browser navigate "https://example.com/contact" && \
agent-browser fill "Name" "Test User" && \
agent-browser fill "Email" "test@example.com" && \
agent-browser fill "Message" "Hello, this is a test." && \
agent-browser click "Send Message" && \
agent-browser wait "Thank you"
```

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
