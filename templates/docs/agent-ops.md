# Agent Operations

Recipes for generated jolo projects. Read this on demand; keep `AGENTS.md` for
rules that matter every session.

## Org Helpers

```bash
emacsclient -e '(bergheim/agent-org-set-state "docs/TODO.org" "TODO Heading text here" "DONE")'
emacsclient -e '(bergheim/agent-org-set-state "docs/TODO.org" "TODO Heading text here" "DONE" "Resolved by commit abc1234.")'
emacsclient -e '(bergheim/agent-org-set-state "docs/TODO.org" "TODO Heading text here" "CANCELLED" "No longer relevant because X.")'
emacsclient -e '(bergheim/agent-org-add-note "docs/TODO.org" "TODO Heading" "Made progress on X.")'
emacsclient -e '(bergheim/agent-org-ensure-id "docs/TODO.org" "TODO Heading")'
emacsclient -e '(bergheim/agent-org-set-state-by-id "docs/TODO.org" "abc-def-123" "DONE")'
emacsclient -e '(bergheim/agent-org-set-state "docs/TODO.org" "TODO Heading" "INPROGRESS" nil t t)'
emacsclient -e '(bergheim/agent-org-add-tag "docs/TODO.org" "TODO Heading" "autonomous")'
emacsclient -e '(bergheim/agent-org-remove-tag "docs/TODO.org" "TODO Heading" "autonomous")'
```

States: `TODO`, `NEXT`, `INPROGRESS`, `WAITING`, `BLOCKED`, `DONE`,
`CANCELLED`.

## Denote Helpers

```bash
emacsclient -e '(bergheim/agent-denote-create "docs/notes" "Title here" (quote ("kind" "topic1" "topic2")) "Body text.")'
emacsclient -e '(bergheim/agent-denote-find "docs/notes" (quote ("emacs")))'
emacsclient -e '(bergheim/agent-denote-list "docs/notes")'
emacsclient -e '(bergheim/agent-denote-link "/abs/path/to/source.org" (quote ("/abs/path/to/target1.org" "/abs/path/to/target2.org")))'
emacsclient -e '(bergheim/agent-denote-list "/workspaces/stash/notes" 15)'
```

## Ports and Dev Server

Use `$PORT` in every server command and URL.

```bash
echo "$PORT"
vite --host 0.0.0.0 --port "$PORT"
next dev -H 0.0.0.0 -p "$PORT"
flask run --host 0.0.0.0 --port "$PORT"
uvicorn app:app --host 0.0.0.0 --port "$PORT"
```

Clients connect to localhost:

```bash
curl "http://localhost:$PORT/healthz"
browser-check "http://localhost:$PORT" --describe --console --errors
playwright-cli open "http://localhost:$PORT"
```

## just Recipes

```bash
just --list
just dev
just dev-restart
just run
just test
just test-watch
just add <dependency>
just perf
just wt
```

`dev.log` is a tee of the dev server output.

## Browser Automation

Use `browser-check` for one-shot checks:

```bash
browser-check "http://localhost:$PORT" --describe --console --errors
browser-check "http://localhost:$PORT" --screenshot --output scratch/verify.png
browser-check "http://localhost:$PORT" --screenshot --full-page --output scratch/full.png
browser-check "http://localhost:$PORT" --aria
browser-check "http://localhost:$PORT" --aria --interactive --json
browser-check "http://localhost:$PORT" --pdf --output scratch/page.pdf
```

Use `playwright-cli` for stateful flows:

```bash
playwright-cli open "http://localhost:$PORT"
playwright-cli -s=default snapshot
playwright-cli -s=default click e12
playwright-cli -s=default fill e20 "hello"
playwright-cli -s=default screenshot --filename scratch/after-click.png
playwright-cli -s=default close
```

Verification reports should include URL, exact command, success/failure evidence,
and artifact path when generated.

## Accessibility

```bash
just a11y
just a11y --include-notices "http://localhost:$PORT/some-page"
browser-check "http://localhost:$PORT" --aria
browser-check "http://localhost:$PORT" --aria --interactive
```

WCAG 2.2 AA is the minimum target.

## Notify and Share

Set the route used by completion notifications:

```bash
notify set-path /dashboard
notify set-path /article/123
notify set-path /
```

Share artifacts through the host stash:

```bash
share foo.png
share .
share /path/to/file
```

## Image Tooling

Preferred formats: AVIF > WebP > PNG/JPEG.

```bash
vips copy input.png output.avif[Q=30]
cwebp -q 80 input.png -o output.webp
vipsthumbnail input.jpg -s 800x -o output.avif[Q=30]
```

Use vips/avifenc/cwebp; do not add ImageMagick or Pillow unless the project
requires them.

## Podman Gate

Host-side activation:

```sh
jolo allow podman <project>
cd <project> && jolo up --recreate
jolo deny podman <project>
jolo allow podman <project>
jolo allowed
```

Inside the container when allowed:

```sh
podman ps
podman exec other-project ls /workspaces
podman logs --tail 50 other-project
```

## Performance

`just perf` posts `perf-rig.toml` to the host-side perf hub. The target URL in
`perf-rig.toml` must be externally reachable; keep it symbolic with
`${DEV_HOST}` and `${PORT}`.

`PERF_HOST` flows from the host shell into devcontainers. Override
`PERF_TESTBED` when a worktree or CI runner needs a distinct baseline.

## Local Models

`LLAMA_HOST` points to a llama-swap OpenAI-compatible router.

```bash
curl -s "$LLAMA_HOST/v1/models" | jq '.data[].id'
curl -s "$LLAMA_HOST/v1/chat/completions" \
  -H "Content-Type: application/json" \
  -d '{"model":"gemma4","messages":[{"role":"user","content":"..."}]}'
curl -s "$LLAMA_HOST/v1/completions" \
  -H "Content-Type: application/json" \
  -d '{"model":"gemma4","prompt":"..."}'
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
