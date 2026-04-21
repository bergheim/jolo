---
name: j-review
description: Run pragmatic tests first, then get a second-opinion code review from another AI agent (claude, gemini, or codex) using the current git diff. Use when you want a fresh, correctness-focused review without heavy setup.
---

# /j-review

Run pragmatic tests and then get a code review from a different AI agent for a fresh perspective.

## Arguments

- `[file...]` — (optional) specific files to review
- `--agent <name>` — (optional) force a specific reviewer: `claude`, `gemini`, or `codex`

If no files are given, and we are on a branch different from main, review the complete branch. If we are on main, review the current diff (staged if any, otherwise unstaged).

## Instructions

### 1. Run tests first (pragmatic)

- Prefer a project test runner if present.
- Be pragmatic: avoid heavy installs or services just to test a small change.
- If tests are too heavy or unavailable, state what you did and why.

Suggested order:
- If `justfile` exists: `just test` or a targeted recipe.
- Else if `package.json` exists: `npm test` or `pnpm test` (use the repo norm).
- Else if `pyproject.toml` exists: `just test` or `uv run pytest` if already configured.
- Else if `go.mod` exists: `go test ./...`.
- Else: run nothing and explain.

Capture test output in a variable or temp file.

### 2. Determine what to review

- If file arguments provided: review those files
- If there are staged changes (`git diff --cached --stat`): review the staged diff
- If there are unstaged changes (`git diff --stat`): review the unstaged diff
- If no changes: ask the user what to review

Capture the diff or file contents into a variable.

### 3. Pick the reviewer

- If `--agent` specified, use that agent
- Otherwise, pick a different agent than yourself:
  - If you are Claude: use `gemini`
  - If you are Gemini: use `codex`
  - If you are Codex: use `claude`

Prefer the strongest available model for review if the CLI supports model selection.

### 4. Run the review

Include test output and the diff. Use non-interactive / print mode for each agent.

**Unset `ANTHROPIC_API_KEY` and `OPENAI_API_KEY`** when calling `claude` or `codex` so they use their own CLI auth instead of API-key mode.

**Keep the review lean.** Default `codex exec` is verbose — high reasoning, exploratory file reads via `sed`/`nl`/`rg`, and full test runs before writing a word. A 4-paragraph plan can produce 130KB of transcript and take 10 minutes. For a text-only review of piped content, scope it down.

Prompt directive (use for every agent):

> "Review only the text shown. Do not read other files. Do not run commands, tests, or searches. Be terse — flag real issues, not style nits. Under 300 words."

Invocations:

```bash
PROMPT="Review only the text shown. Do not read other files. Do not run commands, tests, or searches. Be terse — flag real issues, not style nits. Under 300 words. Tests: $TEST_OUTPUT"

# Codex — read-only sandbox, low reasoning, capture final message only
OUT=$(mktemp)
printf '%s\n\n%s\n' "$PROMPT" "$content" | env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY codex exec \
  -s read-only -c model_reasoning_effort=low --ephemeral -o "$OUT" - > /dev/null 2>&1
cat "$OUT"; rm -f "$OUT"

# Claude
echo "$content" | env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY claude -p "$PROMPT"

# Gemini
echo "$content" | gemini -p "$PROMPT"
```

Use `codex review --uncommitted` (dedicated subcommand) **only** when you genuinely want codex to explore the whole working tree as part of the review. For a text-only "here's a diff, what's wrong" — use the lean `codex exec` invocation above. It keeps time and output size bounded.

### 5. Present the results

Print the reviewer's name and their feedback. Do not editorialize or filter the response.

## Rules

- Never review your own output — always use a different agent
- Keep the review prompt focused on correctness, not style
- Do not modify any files — this is read-only
