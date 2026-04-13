# AGENTS.md

Guidelines for AI coding assistants working on this project.

Generated: <YYYY-MM-DD>

## Communication

Assume the user is an experienced developer. Skip basic explanations, don't over-qualify statements, and don't pad responses with filler ("great question!", "certainly!").

Disagree when you have evidence. If the user's approach has a flaw or you see a better alternative, say so directly with your reasoning — don't just go along with it. Pushback leads to better discussions and a better product. A wrong agreement costs more than a brief debate.

## Project Memory

Shared knowledge lives in org-mode files under `docs/` that all agents read and write:

| File | Purpose | Content |
|------|---------|---------|
| `docs/PROJECT.org` | Project context | Why it exists, who it's for, architecture, key decisions |
| `docs/MEMORY.org` | Shared memory | Conventions, patterns, gotchas — tag with keywords |
| `docs/TODO.org` | Work items | Actionable items: `TODO`/`DONE` headings |
| `docs/RESEARCH.org` | Findings and investigations | Root causes, solutions, technical discoveries |

**Before any implementation:** If `docs/PROJECT.org` doesn't exist, do not start coding. First discuss with the user: what is this project, who is it for, what are the key constraints and architectural decisions? Write the answers to `docs/PROJECT.org` before proceeding.

**On session start:** Read `docs/PROJECT.org`, `docs/MEMORY.org` and `docs/TODO.org` to pick up where others left off.

**On discoveries:** Write conventions, patterns, and gotchas to `docs/MEMORY.org` with keyword tags (e.g., `:musl:auth:perf:`).

**Personal memory** goes to your agent-specific file (not shared):
- Claude: `.claude/MEMORY.md`
- Gemini: `.gemini/MEMORY.md`
- Codex: `.codex/MEMORY.md`
- Pi: `.pi/MEMORY.md`

Use personal memory for workflow preferences, mistake patterns, and agent-specific learnings. Use shared memory for anything another agent would benefit from knowing.

Shared, non-reproducible resources across projects go in the stash: host `~/stash` is mounted at `/workspaces/stash` in devcontainers.

`scratch/` is a gitignored directory for experiments, generated assets, and throwaway work. Do not treat its contents as project code.

## Screenshots

When the user says they took a screenshot, read the latest one:

```bash
ls -t /workspaces/stash/shot-*.png | head -1
```

Then use the Read tool on that file to view it.

## Task Tracking

`docs/TODO.org` is the active work log, not a reference document. Treat it as the single source of truth for what needs doing.

- **Before starting work**: check TODO.org for existing tasks — don't duplicate effort
- **When you complete a task**: mark it `DONE` immediately, not at the end of the session
- **When you discover new work**: add it as a `TODO` heading right away
- **When a task is no longer relevant**: mark it `CANCELLED` with a reason
- **Never delete body text** when closing a TODO — the original description, context, and notes are valuable history. The reason goes in the LOGBOOK, not as a replacement for the body.

### Editing org files with emacsclient

**Always use emacsclient for org state changes** — never manually edit TODO/DONE keywords with a text editor. Org-mode adds CLOSED timestamps, LOGBOOK entries, and state transition metadata automatically.

**Toggle TODO state (DONE, CANCELLED, etc.):**

```bash
emacsclient --eval '
(with-current-buffer (find-file-noselect "docs/TODO.org")
  (goto-char (point-min))
  (re-search-forward "TODO Heading text here")
  (beginning-of-line)
  (org-todo "DONE")
  (save-buffer))'
```

**Toggle with a reason note** (required for CANCELLED, optional for DONE):

```bash
emacsclient --eval '
(with-current-buffer (find-file-noselect "docs/TODO.org")
  (goto-char (point-min))
  (re-search-forward "TODO Heading text here")
  (beginning-of-line)
  (let ((org-log-note-purpose (quote state))
        (org-log-note-state "CANCELLED")
        (org-log-note-previous-state "TODO"))
    (org-todo "CANCELLED")
    (org-add-log-note)
    (insert "The reason this was cancelled")
    (org-store-log-note))
  (save-buffer))'
```

This produces proper org metadata:

```org
** CANCELLED The task heading
CLOSED: [2026-04-13 Mon 12:08]
:LOGBOOK:
- State "CANCELLED"  from "TODO"  [2026-04-13 Mon 12:08] \\
  The reason this was cancelled
:END:
   Original body text preserved here...
```

Available states: `TODO`, `INPROGRESS`, `NEXT`, `WAITING`, `DONE`, `CANCELLED`.

## Emacs

Emacs runs as a daemon in the container. Use `emacsclient --eval '(expr)'` to query state, check modes, read variables, or run diagnostics — never ask the user to run `M-x` or `M-:` manually.

## Port Configuration

**The port is `$PORT`. It is NOT 4000.** Always use `$PORT` in every command,
URL, and tool invocation. Never hardcode a port number. Run `echo $PORT` if
you need the current value.

**The dev server is ALWAYS running.** Assume `just dev` is running on `$PORT`
with `--reload`. It auto-reloads on file changes. NEVER start a temporary
server on another port for screenshots or testing — just use the running dev
server directly: `browser-check http://localhost:$PORT/page --screenshot`.

**Always bind to `0.0.0.0`**, not `localhost` or `127.0.0.1`. Container networking requires it — `localhost` inside the container is not reachable from outside.

**Servers** (bind to `0.0.0.0`):

| Framework | Configuration |
|-----------|---------------|
| Vite | `vite --host 0.0.0.0 --port $PORT` |
| Next.js | `next dev -H 0.0.0.0 -p $PORT` |
| Flask | `flask run --host 0.0.0.0 --port $PORT` |
| FastAPI | `uvicorn app:app --host 0.0.0.0 --port $PORT` |
| Go | `http.ListenAndServe(":"+os.Getenv("PORT"), nil)` |

**Clients** (connect to `localhost`):

| Tool | Command |
|------|---------|
| browser-check | `browser-check http://localhost:$PORT ...` |
| curl | `curl http://localhost:$PORT/healthz` |
| playwright-cli | `playwright-cli open http://localhost:$PORT` |

## Notifications

Push notifications fire automatically when you finish a response (via hooks).
For web projects, the notification includes an "Open app" button linking to the
dev server URL. By default it points to `/`.

When working on a specific page or route, set the notification path so the
button links there instead:

```bash
notify set-path /dashboard
notify set-path /article/123
notify set-path /          # reset to root
```

This persists across responses until changed. Set it whenever you start working
on a specific route so the user can tap the notification and land on the right
page.

## Development Workflow

Use `just` recipes for common tasks. **Always use `just dev`** — it auto-reloads on file changes. Only use `just run` for one-off executions (e.g., scripts, CLI tools).

| Recipe | Purpose |
|--------|---------|
| `just dev` | Run with auto-reload (use this for development) |
| `just run` | Run once without watching |
| `just test` | Run tests |
| `just test-watch` | Run tests on file change |
| `just add X` | Add a dependency |

**Dev server log:** `just dev` runs automatically in a tmux window and logs all output (stdout + stderr) to `dev.log` at the project root. Read this file to check server output, errors, and request logs without needing access to the dev server's tmux pane.

## Frontend Verification

After making visible UI changes (markup, styles, component layout), verify before committing:

```bash
browser-check http://127.0.0.1:$PORT --screenshot --errors --output scratch/verify.png
```

Read the screenshot to confirm the result looks correct, and check the error output for JS exceptions. Don't commit frontend changes without verifying visually.

## Image Tooling

**Format preference:** AVIF > WebP > PNG/JPEG. AVIF has the best compression and 95%+ browser support. Use WebP as fallback for older browsers. PNG only for lossless needs (logos, icons with transparency).

**Tools available:**
- `vips`/`vipsthumbnail` — preferred for conversion, resizing, thumbnails (supports AVIF, WebP, JPEG, PNG)
- `avifenc`/`avifdec` — standalone AVIF encoding/decoding
- `cwebp`/`dwebp` — standalone WebP encoding/decoding

Do not add ImageMagick or Pillow unless the project explicitly requires them.

```bash
# Convert to AVIF (quality 30 = good balance)
vips copy input.png output.avif[Q=30]

# Convert to WebP
cwebp -q 80 input.png -o output.webp

# Resize and convert in one step
vipsthumbnail input.jpg -s 800x -o output.avif[Q=30]
```

## Accessibility & Semantic HTML

All web output must follow universal design principles. This is not optional polish — it is a baseline requirement.

### Structure

- Use semantic elements: `<main>`, `<nav>`, `<header>`, `<footer>`, `<section>`, `<article>`, `<aside>`
- One `<h1>` per page. Headings must follow hierarchy (`h1` → `h2` → `h3`) — never skip levels
- Add a skip-nav link as the first child of `<body>`: `<a href="#main" class="sr-only focus:not-sr-only">Skip to content</a>`
- Set `lang` attribute on `<html>` to the correct language (e.g., `lang="nb"` for Norwegian Bokmål)

### Forms & Interactive Elements

- Every `<input>` must have a visible `<label>` (or `aria-label` if the design hides it)
- Use `<button>` for actions, `<a>` for navigation — never `<div onclick>`
- All interactive elements must be keyboard-reachable and have visible focus styles
- Group related inputs with `<fieldset>` and `<legend>`

### Images & Media

- All `<img>` elements need `alt` text. Decorative images get `alt=""`
- Complex images (charts, diagrams) need extended descriptions
- Avoid text in images — use real text with CSS styling

### Color & Contrast

- Minimum 4.5:1 contrast ratio for normal text, 3:1 for large text (WCAG AA)
- Never convey information by color alone — add icons, patterns, or text labels

### Verification

Use `browser-check` to audit pages:

```bash
# Get ARIA tree to check landmark structure
browser-check http://localhost:$PORT --aria

# Check only interactive elements (buttons, links, inputs)
browser-check http://localhost:$PORT --aria --interactive
```

### Reference

Follow [WCAG 2.2 AA](https://www.w3.org/WAI/WCAG22/quickref/?levels=aaa) as the minimum standard.

## Git Workflow

Keep a rebased, linear history. Work on feature branches, rebase onto `main` before merging, and use merge commits when combining multi-commit branches (to preserve the logical grouping). For single-commit branches, fast-forward merge is fine.

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

## Local Models (Ollama)

`OLLAMA_HOST` is set in the container environment, pointing to a self-hosted ollama instance with GPU. Use it for tasks where a free local model is good enough — drafting, summarization, embeddings, throwaway experiments — instead of burning API credits.

```bash
# Check available models
curl -s $OLLAMA_HOST/api/tags | jq '.models[].name'

# Generate (streaming)
curl -s $OLLAMA_HOST/api/generate -d '{"model":"gemma4:26b","prompt":"..."}'

# Chat (OpenAI-compatible endpoint)
curl -s $OLLAMA_HOST/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"gemma4:26b","messages":[{"role":"user","content":"..."}]}'

# Embeddings
curl -s $OLLAMA_HOST/api/embed -d '{"model":"bge-m3","input":"..."}'
```

Python/JS SDKs that support OpenAI-compatible APIs work with `$OLLAMA_HOST/v1` as the base URL. The `ollama` CLI is not installed — use HTTP calls or SDK clients.

## Cross-Agent Reviews

When shelling out to another agent CLI for a code review or second opinion, **unset `ANTHROPIC_API_KEY` and `OPENAI_API_KEY`** so the agent uses its own CLI auth instead of falling back to direct API-key mode.

```bash
# Correct — uses CLI auth
echo "$diff" | env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY claude -p "Review this..."
env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY codex review --uncommitted

# Wrong — may use API key billing instead of CLI auth
echo "$diff" | claude -p "Review this..."
```

This applies to `claude`, `codex`, and any agent that checks for API keys before falling back to OAuth/CLI credentials.

## Code Quality

Pre-commit hooks are already installed. They run automatically on `git commit`. If a commit fails, fix the issues and commit again.

- **Never skip hooks**: NEVER use `git commit --no-verify`. Pre-commit hooks (ruff, format, tests, codespell) are the guardrails that keep code clean. If a hook blocks the commit, fix the underlying issue — add the word to the codespell allowlist, fix the lint error, fix the failing test. Skipping hooks to save time means shipping broken formatting, lint errors, and test failures that compound into a mess. No exceptions.

To run manually: `pre-commit run --all-files`

## Coding Style

Prefer functional style: pure functions, composition, immutable data. Use mutation or classes only when they're genuinely simpler (e.g., stateful protocol handlers, GUI frameworks that require it).

**Types:** Always add type annotations — function signatures, return types, variables where the type isn't obvious. Use strict mode where available (mypy strict, TypeScript strict).

**Naming:** Short but clear. `auth_user()` over `process_user_authentication_request()`. Single-letter names are fine in small scopes (`i`, `x` in lambdas/loops), longer names for public APIs.

**File size:** Split when a file gets unwieldy (~300-500 lines). One module should have one clear responsibility, but don't split prematurely — three related functions in one file beats three single-function files.

**Error handling:** Follow the language's idioms. Rust → `Result`, Python → exceptions, Go → error returns. Don't fight the language.

**Comments:** Code should be self-documenting. Comments explain *why*, never *what*. Do not add comments that restate the code or narrate context from the conversation — if a comment is needed at all, keep it to a few words. No docstrings on functions where the name and types tell the whole story. When interleaving comments with code, you MUST use the comment syntax of that language (e.g., `#` for Python/shell, `//` for JS/Go/Rust, `--` for SQL/Lua). Never use markdown or other formatting in code comments.

**Testing:** Unit tests for pure logic, integration tests for workflows. Test the public contract, not implementation details. Avoid mocking unless you need to isolate from external systems (network, filesystem, databases).

**Dependencies:** Prefer stdlib when it does the job well. Use popular, well-maintained libraries when they save significant effort or handle complexity you shouldn't reimplement (HTTP clients, ORMs, auth). Always use vetted libraries for security-sensitive code — never roll your own crypto, auth, or sanitization.

**Avoid:**
- Deep inheritance hierarchies — prefer composition
- Over-engineering — no interfaces for single implementations, no DI containers, no config-driven everything
- Magic and implicit behavior — no decorators that hide control flow, no monkey-patching, no metaclass tricks
- Premature abstraction — three similar lines of code is better than a generic helper used once
- Defensive duplication — if a called function already validates or errors, don't re-check in the caller

**When uncertain:** Ask rather than guess. A quick question is cheaper than a wrong assumption baked into the code.

## Browser Automation

Use **Playwright CLI** for most tasks. It is stateful and writes snapshots/logs/artifacts to disk (`.playwright-cli/`) instead of streaming large payloads in chat. Use `browser-check` for quick, stateless audits.

### Tool Selection

Use this decision rule when both tools could work:

| Situation | Preferred Tool | Why |
|-----------|----------------|-----|
| Single URL health check, one screenshot, one-off console/error scan | `browser-check` | Faster, stateless, one command |
| Multi-step interaction (click/fill/navigate), auth/session reuse, repeated captures | `playwright-cli` | Stateful session, better for workflows |
| Debugging flow regressions | `playwright-cli` | Snapshots, traces, and session history |

| Task | Tool / Command |
|------|----------------|
| **Interactive Flow** | **Playwright CLI** (`playwright-cli`) |
| Check what's on page | `browser-check URL --describe` |
| Take screenshot | `browser-check URL --screenshot` |
| Full page screenshot | `browser-check URL --screenshot --full-page` |
| Generate PDF | `browser-check URL --pdf` |
| Get ARIA tree | `browser-check URL --aria` |
| Interactive elements only | `browser-check URL --aria --interactive` |
| Console logs | `browser-check URL --console` |
| JS errors | `browser-check URL --errors` |
| JSON output | `browser-check URL --json --console --errors` |

### Browser Automation Examples

```bash
# Stateful browser session (token-efficient)
playwright-cli open http://127.0.0.1:$PORT
playwright-cli -s=default snapshot
playwright-cli -s=default click e12
playwright-cli -s=default fill e20 "hello"
playwright-cli -s=default screenshot --filename scratch/after-click.png
playwright-cli -s=default close

# Check if dev server is up
browser-check http://127.0.0.1:$PORT --describe --console --errors

# Screenshot
browser-check http://127.0.0.1:$PORT --screenshot --output scratch/shot.png

# Get page structure for LLM
browser-check http://127.0.0.1:$PORT --aria --interactive --json
```

For multi-step interactive flows, prefer Playwright CLI sessions. The scaffold includes `.playwright/cli.config.json` configured for system Chromium on Alpine.

### Verification Standard

For browser verification tasks (for example: "is the site running?"), include all of the following in your report:

- URL and exact check time
- Command(s) used
- Evidence of success/failure (status code, page title, or key console/error lines)
- Artifact path when generated (save screenshots/PDFs to `scratch/`)

### Troubleshooting

- If `playwright-cli open` succeeds but `-s=<id>` commands fail, run `playwright-cli list` and use the listed session label (often `default`).
- If screenshots are blank or not the expected view, run `playwright-cli -s=<session> snapshot` first and confirm URL/title before capture.

Use the `browser-verify` skill when the request is to verify site availability, capture evidence, and report reproducible checks.
