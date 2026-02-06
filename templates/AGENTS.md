# AGENTS.md

Guidelines for AI coding assistants working on this project.

## Port Configuration

Dev servers must use `$PORT` (default 4000, set dynamically in spawn mode).

| Framework | Configuration |
|-----------|---------------|
| Vite | `vite --port $PORT` |
| Next.js | `next dev -p $PORT` |
| Flask | `flask run --port $PORT` |
| FastAPI | `uvicorn app:app --port $PORT` |
| Go | `http.ListenAndServe(":"+os.Getenv("PORT"), nil)` |

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
