# AGENTS.md

Guidelines for AI coding assistants working on this project.

Generated: <YYYY-MM-DD>

## Project Memory

Shared knowledge lives in org-mode files under `docs/` that all agents read and write:

| File | Purpose | Content |
|------|---------|---------|
| `docs/TODO.org` | Tasks and plans | Actionable items: `TODO`/`DONE` headings |
| `docs/RESEARCH.org` | Findings and investigations | Root causes, solutions, technical discoveries |

**On session start:** Read both files to pick up where others left off.

**On "save state":** Write what you learned this session — tasks to docs/TODO.org, findings to docs/RESEARCH.org, agent-private learnings to your own memory system. Tag entries with keywords (e.g., `:musl:auth:perf:`) for searchability.

Agent-private memory (workflow preferences, mistake patterns) goes to each agent's own system — not shared files.

Shared, non-reproducible resources across projects go in the stash: host `~/stash` is mounted at `/workspaces/stash` in devcontainers.

## Port Configuration

Dev servers must use `$PORT` (default 4000, set dynamically in spawn mode).

**Always bind to `0.0.0.0`**, not `localhost` or `127.0.0.1`. Container networking requires it — `localhost` inside the container is not reachable from outside.

| Framework | Configuration |
|-----------|---------------|
| Vite | `vite --host 0.0.0.0 --port $PORT` |
| Next.js | `next dev -H 0.0.0.0 -p $PORT` |
| Flask | `flask run --host 0.0.0.0 --port $PORT` |
| FastAPI | `uvicorn app:app --host 0.0.0.0 --port $PORT` |
| Go | `http.ListenAndServe(":"+os.Getenv("PORT"), nil)` |

## Development Workflow

Use `just` recipes for common tasks. **Always use `just dev`** — it auto-reloads on file changes. Only use `just run` for one-off executions (e.g., scripts, CLI tools).

| Recipe | Purpose |
|--------|---------|
| `just dev` | Run with auto-reload (use this for development) |
| `just run` | Run once without watching |
| `just test` | Run tests |
| `just test-watch` | Run tests on file change |
| `just add X` | Add a dependency |

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

**Worktree awareness:** Check `.git` at session start — if it's a file (not a directory), you are in a worktree. You cannot checkout `main` here. Find the main tree and merge there:

```bash
# Detect: file = worktree, directory = main repo
test -f .git && echo "worktree" || echo "main repo"

# Merge from a worktree
MAIN=$(git worktree list | awk '/\[main\]/{print $1}')
git rebase main && git -C "$MAIN" merge $(git branch --show-current)
```

## Code Quality

Pre-commit hooks are already installed. They run automatically on `git commit`. If a commit fails, fix the issues and commit again.

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

Use **Playwright MCP** for most tasks. It is stateful and allows full interaction (clicking, typing, etc.). Use `browser-check` for quick, stateless audits.

| Task | Tool / Command |
|------|----------------|
| **Interactive Flow** | **Playwright MCP** (pre-configured) |
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
# Check if dev server is up
browser-check http://localhost:$PORT --describe --console --errors

# Screenshot
browser-check http://localhost:$PORT --screenshot --output shot.png

# Get page structure for LLM
browser-check http://localhost:$PORT --aria --interactive --json
```

For multi-step interactive flows (clicking, filling forms), use the **Playwright MCP** tools (`navigate`, `fill`, `click`). MCP servers are automatically discovered from `templates/mcp/*.json` and injected into agent configurations during `jolo up`.
