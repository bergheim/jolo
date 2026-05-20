# Agent Operations

Recipes for agents working in the jolo meta-project. Read this on demand; keep
`AGENTS.md` for rules that matter every session.

## Org Helpers

Mark a TODO done:

```bash
emacsclient -e '(bergheim/agent-org-set-state "docs/TODO.org" "TODO Heading text here" "DONE")'
```

Mark done with a reason:

```bash
emacsclient -e '(bergheim/agent-org-set-state "docs/TODO.org" "TODO Heading text here" "DONE" "Resolved by commit abc1234.")'
```

Cancel with a reason:

```bash
emacsclient -e '(bergheim/agent-org-set-state "docs/TODO.org" "TODO Heading text here" "CANCELLED" "No longer relevant because X.")'
```

Add a log note:

```bash
emacsclient -e '(bergheim/agent-org-add-note "docs/TODO.org" "TODO Heading" "Made progress on X.")'
```

Ensure a stable ID:

```bash
emacsclient -e '(bergheim/agent-org-ensure-id "docs/TODO.org" "TODO Heading")'
emacsclient -e '(plist-get (bergheim/agent-org-ensure-id "docs/TODO.org" "TODO Heading") :id)'
```

Transition by ID:

```bash
emacsclient -e '(bergheim/agent-org-set-state-by-id "docs/TODO.org" "abc-def-123" "DONE")'
```

Track time on transition:

```bash
emacsclient -e '(bergheim/agent-org-set-state "docs/TODO.org" "TODO Heading" "INPROGRESS" nil t t)'
```

Manage the `autonomous` tag:

```bash
emacsclient -e '(bergheim/agent-org-add-tag "docs/TODO.org" "TODO Heading" "autonomous")'
emacsclient -e '(bergheim/agent-org-remove-tag "docs/TODO.org" "TODO Heading" "autonomous")'
```

States: `TODO`, `NEXT`, `INPROGRESS`, `WAITING`, `BLOCKED`, `DONE`,
`CANCELLED`.

## Denote Helpers

Create a project note:

```bash
emacsclient -e '(bergheim/agent-denote-create "docs/notes" "Title here" (quote ("kind" "topic1" "topic2")) "Body text.")'
```

Find project notes:

```bash
emacsclient -e '(bergheim/agent-denote-find "docs/notes" (quote ("emacs")))'
emacsclient -e '(bergheim/agent-denote-find "docs/notes" (quote ("gotcha")) "evil")'
emacsclient -e '(bergheim/agent-denote-list "docs/notes")'
```

Link notes:

```bash
emacsclient -e '(bergheim/agent-denote-link "/abs/path/to/source.org" (quote ("/abs/path/to/target1.org" "/abs/path/to/target2.org")))'
```

Scan stash notes:

```bash
emacsclient -e '(bergheim/agent-denote-list "/workspaces/stash/notes" 15)'
```

## Git and Worktrees

Detect checkout type:

```bash
test -f .git && echo "worktree" || echo "main repo"
```

Merge from a worktree:

```bash
MAIN=$(git worktree list | awk '/\[main\]/{print $1}')
git rebase main
git -C "$MAIN" merge "$(git branch --show-current)"
```

Sequential branch landing:

```bash
git checkout feature-branch
git rebase main
git checkout main
git merge feature-branch
git merge --no-ff feature-branch
```

## Build and Test

```bash
just test
just test-k "pattern"
just test-v
podman build -t jolo .
podman build --build-arg USERNAME=$(whoami) --build-arg USER_ID=$(id -u) --build-arg GROUP_ID=$(id -g) -t jolo .
```

Pre-commit setup for new projects:

```bash
pre-commit install
pre-commit run --all-files
```

Basic hook set:

```yaml
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v5.0.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-added-large-files
```

Language-specific hook choices:

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

## jolo CLI

```bash
jolo up
jolo up -d
jolo up --shell
jolo up --run "pnpm test"
jolo up --recreate
jolo a --recreate
jolo down
jolo down --all
jolo list
jolo list --all
jolo attach
jolo create newproject
jolo init
jolo tree feature-x
jolo tree feat --from develop
jolo spawn 5 -p "implement X"
jolo spawn 3 --prefix auth -p "..."
jolo prune
jolo destroy
```

Prompt mode:

```bash
jolo up -p "add user auth"
jolo tree feat -p "add OAuth"
jolo create app -p "scaffold"
jolo up --agent gemini -p "..."
```

Mount and copy options:

```bash
jolo up --mount ~/data:data
jolo up --mount ~/data:data:ro
jolo up --mount ~/data:/mnt/data
jolo up --copy ~/config.json
jolo up --copy ~/config.json:app/
```

Autonomous dispatch:

```bash
jolo autonomous
jolo autonomous --dry-run
jolo autonomous --agents claude,codex
```

## Podman Gate

Host-side activation:

```sh
jolo allow podman <project>
cd <project> && jolo up --recreate
jolo deny podman <project>
jolo allow podman <project>
jolo allowed
```

When allowed inside a container:

```sh
podman ps
podman exec <peer> <cmd>
podman logs --tail 50 <peer>
```

## Browser Automation

Use `playwright-cli` for stateful flows and `browser-check` for quick one-shot
audits.

```bash
browser-check http://localhost:$PORT --describe --console --errors
browser-check http://localhost:$PORT --screenshot --output scratch/verify.png
browser-check http://localhost:$PORT --screenshot --full-page --output scratch/full.png
browser-check http://localhost:$PORT --aria
browser-check http://localhost:$PORT --aria --interactive --json
browser-check http://localhost:$PORT --pdf --output scratch/page.pdf
```

```bash
playwright-cli open http://localhost:$PORT
playwright-cli snapshot
playwright-cli click e1
playwright-cli fill e2 "hello"
playwright-cli screenshot
playwright-cli close
```

For advanced flows, write a small Node.js Playwright script.

## Local Models

`LLAMA_HOST` points to a llama-swap OpenAI-compatible router.

```bash
curl -s "$LLAMA_HOST/v1/models" | jq '.data[].id'
curl -s "$LLAMA_HOST/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{"model":"gemma4","messages":[{"role":"user","content":"..."}]}'
curl -s "$LLAMA_HOST/v1/embeddings" \
  -H "Content-Type: application/json" \
  -d '{"model":"bge-m3","input":"..."}'
```

Use `/v1/*` endpoints so llama-swap loads the requested model.

## Cross-Agent Reviews

Unset API keys so peer CLIs use their own auth:

```bash
echo "$diff" | env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY claude -p "Review this..."
```

Lean Codex text review:

```bash
OUT=$(mktemp)
printf '%s\n' "$PROMPT_PREFIX" "$DIFF_OR_PLAN" | env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY codex exec \
  -s read-only \
  -c model_reasoning_effort=low \
  --ephemeral \
  -o "$OUT" - > /dev/null 2>&1
cat "$OUT"
rm -f "$OUT"
```

Prompt directive:

```text
Review only the text shown. Do not read other files, run commands, or search the codebase. Respond under 300 words with findings and severity.
```

Use `codex review --uncommitted` only when repository exploration is desired.
