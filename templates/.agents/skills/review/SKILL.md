---
name: review
description: Run pragmatic tests first, then get a second-opinion code review from another AI agent (claude, gemini, or codex) using the current git diff. Use when you want a fresh, correctness-focused review without heavy setup.
---

# /review

Run pragmatic tests and then get a code review from a different AI agent for a fresh perspective.

## Arguments

- `[file...]` — (optional) specific files to review
- `--agent <name>` — (optional) force a specific reviewer: `claude`, `gemini`, or `codex`

If no files given, reviews the current diff (staged if any, otherwise unstaged).

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

Include test output and the diff. Use non-interactive / print mode for each agent:

```bash
# Claude
echo "$content" | claude -p "Review this diff for bugs, logic errors, regressions, and missed edge cases. Be terse - only flag real issues, not style nits. Tests: $TEST_OUTPUT"

# Gemini
echo "$content" | gemini -p "Review this diff for bugs, logic errors, regressions, and missed edge cases. Be terse - only flag real issues, not style nits. Tests: $TEST_OUTPUT"

# Codex (has a dedicated review subcommand)
codex review --uncommitted
```

For codex, prefer `codex review --uncommitted` when reviewing the working tree.
When reviewing specific files, pipe content like the other agents:
```bash
echo "$content" | codex exec "Review this diff for bugs, logic errors, regressions, and missed edge cases. Be terse - only flag real issues, not style nits. Tests: $TEST_OUTPUT"
```

### 5. Present the results

Print the reviewer's name and their feedback. Do not editorialize or filter the response.

## Rules

- Never review your own output — always use a different agent
- Keep the review prompt focused on correctness, not style
- Do not modify any files — this is read-only
