# AGENTS.md

Guidelines for AI coding assistants working on this project.

## Port Configuration

Dev servers must use ports 4000-5000 (forwarded from container to host).

```bash
# Use $PORT env var, default to 4000
PORT="${PORT:-4000}"
```

| Framework | Configuration |
|-----------|---------------|
| Vite | `vite --port $PORT` |
| Next.js | `next dev -p $PORT` |
| Flask | `flask run --port $PORT` |
| FastAPI | `uvicorn app:app --port $PORT` |
| Go | `http.ListenAndServe(":"+os.Getenv("PORT"), nil)` |

## Linter Configuration

### Linters by File Type

| File Type | Linter | Pre-commit Repo |
|-----------|--------|-----------------|
| Python | ruff | `https://github.com/astral-sh/ruff-pre-commit` |
| Go | golangci-lint | `https://github.com/golangci-lint/golangci-lint` |
| JS/TS | biome | `https://github.com/biomejs/pre-commit` |
| Shell | shellcheck | `https://github.com/shellcheck-py/shellcheck-py` |
| Dockerfile | hadolint | `https://github.com/hadolint/hadolint` |
| YAML | yamllint | `https://github.com/adrienverge/yamllint` |
| Markdown | markdownlint | `https://github.com/igorshubovych/markdownlint-cli` |
| Spelling | codespell | `https://github.com/codespell-project/codespell` |

### Pre-commit Hook Examples

**Python project:**
```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.8.0
    hooks:
      - id: ruff
        args: [--fix]
      - id: ruff-format
```

**Go project:**
```yaml
repos:
  - repo: https://github.com/golangci-lint/golangci-lint
    rev: v1.62.0
    hooks:
      - id: golangci-lint
```

**JS/TS project:**
```yaml
repos:
  - repo: https://github.com/biomejs/pre-commit
    rev: v0.6.0
    hooks:
      - id: biome-check
        additional_dependencies: ["@biomejs/biome@1.9.0"]
```

## Decision Heuristics

**Every project gets:**
- Basic hygiene hooks (trailing-whitespace, end-of-file-fixer, check-added-large-files)

**Code projects add:**
- Language-specific linter from table above
- Formatter if separate from linter

**Documentation/prose projects add:**
- markdownlint for Markdown files
- codespell for typo detection

## Browser Automation

Use `browser-check` for all browser tasks. It provides ARIA snapshots with 93% less context than raw HTML. Each command launches a fresh browser (stateless).

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

**Quick patterns:**
```bash
# Check if dev server is up
browser-check http://localhost:$PORT --describe --console --errors

# Screenshot with custom output
browser-check https://example.com --screenshot --output shot.png

# Get page structure for LLM
browser-check https://example.com --aria --interactive --json

# Debug JavaScript errors
browser-check http://localhost:$PORT --errors --console
```

**Limitations:** Stateless (no persistent sessions), no interaction (can't click/fill). For multi-step flows, write a Node.js script using Playwright directly.

## Project Setup Checklist

1. Initialize git: `git init`
2. Create `.pre-commit-config.yaml` with appropriate hooks
3. Install hooks: `pre-commit install`
4. Configure dev server to use `$PORT` (default 4000)
5. Add `.gitignore` for language/framework
