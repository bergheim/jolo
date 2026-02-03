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

Use this table - don't ask which tool to use.

| Task | Tool | Command |
|------|------|---------|
| Screenshot | playwright | `npx playwright screenshot URL file.png` |
| PDF | playwright | `npx playwright pdf URL file.pdf` |
| Check page content | agent-browser | `agent-browser navigate URL --describe` |
| Click/fill/interact | agent-browser | `agent-browser click "Text"` / `fill "Field" "value"` |
| Console logs | webctl | `webctl start && webctl console` |
| Network requests | webctl | `webctl network` |

**Quick patterns:**
```bash
# Screenshot
npx playwright screenshot https://example.com shot.png

# See what's on page
agent-browser navigate "https://example.com" --describe

# Fill form
agent-browser navigate "https://example.com/login" && \
agent-browser fill "Email" "user@example.com" && \
agent-browser fill "Password" "secret" && \
agent-browser click "Sign In"

# Debug JS errors
webctl start && webctl navigate "https://example.com" && webctl console
```

## Project Setup Checklist

1. Initialize git: `git init`
2. Create `.pre-commit-config.yaml` with appropriate hooks
3. Install hooks: `pre-commit install`
4. Configure dev server to use `$PORT` (default 4000)
5. Add `.gitignore` for language/framework
