# AGENTS.md

Guidelines for AI coding assistants working on this project.

## Task Tracking

All tasks, plans, and TODOs go in `TODO.org` (org-mode format). Check it before starting work and update it as tasks are completed or new ones arise.

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

## Code Quality

Pre-commit hooks are already installed. They run automatically on `git commit`. If a commit fails, fix the issues and commit again.

To run manually: `pre-commit run --all-files`

## Browser Automation

Use `browser-check` for all browser tasks. Stateless — each command launches a fresh browser.

| Task | Command |
|------|---------|
| Check what's on page | `browser-check URL --describe` |
| Take screenshot | `browser-check URL --screenshot` |
| Full page screenshot | `browser-check URL --screenshot --full-page` |
| Generate PDF | `browser-check URL --pdf` |
| Get ARIA tree | `browser-check URL --aria` |
| Interactive elements only | `browser-check URL --aria --interactive` |
| Console logs | `browser-check URL --console` |
| JS errors | `browser-check URL --errors` |
| JSON output | `browser-check URL --json --console --errors` |

```bash
# Check if dev server is up
browser-check http://localhost:$PORT --describe --console --errors

# Screenshot
browser-check http://localhost:$PORT --screenshot --output shot.png

# Get page structure for LLM
browser-check http://localhost:$PORT --aria --interactive --json
```

For multi-step interactive flows (clicking, filling forms), write a Node.js script using Playwright directly.
