# Agent Operations

Recipes for agents working in the jolo meta-project. Read this on demand; keep
`AGENTS.md` for rules that matter every session.

Before assuming the helper list is complete, inspect the live Emacs daemon:

```bash
emacsclient -e '(apropos-internal "^bergheim/agent-")'
```

## Org Helpers

Daily forms (`set-state`, `add-note`, `add-tag`) are in `AGENTS.md`.

Public arglists:

- `bergheim/agent-org-set-state FILE HEADING-RE NEW-STATE &optional NOTE AGENT SESSION-ID`
- `bergheim/agent-org-set-state-by-id FILE ID NEW-STATE &optional NOTE AGENT SESSION-ID`
- `bergheim/agent-org-ensure-id FILE HEADING-RE`
- `bergheim/agent-org-add-note FILE HEADING-RE NOTE`
- `bergheim/agent-org-add-tag FILE HEADING-RE TAG`
- `bergheim/agent-org-remove-tag FILE HEADING-RE TAG`
- `bergheim/agent-org-add-todo FILE HEADING &optional BODY TAGS STATE`
- `bergheim/agent-org-list-todos ORG-FILE`
- `bergheim/agent-org-get-entry FILE LOCATOR &optional BY-ID`
- `bergheim/agent-org-autonomous-select ORG-FILE`
- `bergheim/agent-org-autonomous-mark-dispatched ORG-FILE POSITION TIMESTAMP`
- `bergheim/agent-worklog-recent &optional N`

Set state with a reason (logged as a note):

```bash
emacsclient -e '(bergheim/agent-org-set-state "docs/TODO.org" "TODO Heading text here" "DONE" "Resolved by commit abc1234.")'
emacsclient -e '(bergheim/agent-org-set-state "docs/TODO.org" "TODO Heading text here" "CANCELLED" "No longer relevant because X.")'
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

Record who is working (state transitions clock automatically; `agent-meta`
resolves the calling agent's model/effort and vendor session id — never
hand-type them). AGENT lands as a LOGBOOK session line plus `:LAST_AGENT:`:

```bash
emacsclient -e "(bergheim/agent-org-set-state \"docs/TODO.org\" \"TODO Heading\" \"INPROGRESS\" nil $(agent-meta --elisp))"
```

Backfill metadata on a legacy TODO file (idempotent; derives `:CREATED:`
from git history, `:ID:` timestamps, then the stash worklog, else stamps
the 1970 epoch marker meaning unknown; strips obsolete `:SESSION_ID:`):

```bash
org-backfill docs/TODO.org
```

Remove the `autonomous` tag:

```bash
emacsclient -e '(bergheim/agent-org-remove-tag "docs/TODO.org" "TODO Heading" "autonomous")'
```

Add a new top-level TODO. Optional args are body, tags, then state:

```bash
emacsclient -e '(bergheim/agent-org-add-todo "docs/TODO.org" "New task heading" "Body text." (quote ("topic")) "TODO")'
```

List TODO headings, or read one full entry without hand-parsing org text. Both
return JSON strings:

```bash
emacsclient -e '(bergheim/agent-org-list-todos "docs/TODO.org")'
emacsclient -e '(bergheim/agent-org-get-entry "docs/TODO.org" "TODO Heading")'
emacsclient -e '(bergheim/agent-org-get-entry "docs/TODO.org" "20260805T105637Z-0e76d6" t)'
```

Read recent cross-project worklog entries:

```bash
emacsclient -e '(bergheim/agent-worklog-recent 10)'
```

States: `TODO`, `PROJ`, `NEXT`, `INPROGRESS`, `WAITING`, `SOMEDAY`, `DONE`,
`CANCELLED`, `OBSOLETE`. There is no `BLOCKED` — use `WAITING`. A state not in
this list is rejected by `--apply-state` unless the file declares its own
`#+TODO:` header.

## Denote Helpers

Daily forms (`create`, `find`, `list`, stash scan) are in `AGENTS.md`.

Public arglists:

- `bergheim/agent-denote-create DIR TITLE KEYWORDS &optional BODY`
- `bergheim/agent-denote-find DIR &optional KEYWORDS TITLE-RE`
- `bergheim/agent-denote-read FILEPATH`
- `bergheim/agent-denote-list DIR &optional LIMIT`
- `bergheim/agent-denote-link SOURCE-PATH TARGET-PATHS`
- `bergheim/agent-denote-get-backlinks FILEPATH`

`agent-denote-list` is an index view and returns only `:id`, `:title`, and
`:keywords`. Use `agent-denote-find` when a file path is needed.

Filter a find by content query:

```bash
emacsclient -e '(bergheim/agent-denote-find "docs/notes" (quote ("gotcha")) "evil")'
```

Read a note by path:

```bash
emacsclient -e '(bergheim/agent-denote-read "/abs/path/to/note.org")'
```

Link notes. This is the only sanctioned way to link — never hand-write
`[[denote:ID]]` or a bare identifier in body text. It calls denote's
`denote-format-link` for correct syntax, is idempotent (skips already-linked
targets), and appends a `* Related notes` section. Denote derives backlinks from
these forward links, so a hand-typed id silently fails to register and reverse
links are never written (write-once):

```bash
emacsclient -e '(bergheim/agent-denote-link "/abs/path/to/source.org" (quote ("/abs/path/to/target1.org" "/abs/path/to/target2.org")))'
```

Read backlinks by absolute note path:

```bash
emacsclient -e '(bergheim/agent-denote-get-backlinks "/abs/path/to/note.org")'
```

## Stash Cookbook Notes

Host-level setup (compose, dotfiles, services, homelab) goes in a single org
note under `/workspaces/stash/notes`, not a folder of loose files. Put each file
in a src block so `org-babel-tangle` regenerates it on demand:

```org
#+begin_src yaml :tangle ../svc/compose.yaml :mkdirp yes
services:
  app:
    image: ghcr.io/example/app:latest
#+end_src
```

- Keep `:tangle` paths relative to the note so they resolve under both
  `/workspaces/stash` and host `~/stash`.
- The note is the single source of truth; tangle regenerates the files.
- Verify once: tangle to a temp dir and diff against the intended output.

## Git and Worktrees

`just wt` is the only worktree interface. Do not read `/usr/local/bin/wt`
to reverse-engineer it — `just wt help` is the catalog.

```bash
just wt help
just wt new <name> [-p <prompt>] [--from <ref>]   # create + tmux window
just wt ls                                        # list windows
just wt sync [<name>]                             # rebase worktree on main's branch
just wt land [<name>] --rm                        # from main tree: rebase, merge, push, delete
just wt delete [<name>]                           # abandon unmerged work only
just wt prune                                     # stale refs
```

`wt land` (must run from the main tree, both trees clean):

- rebases `<name>` onto the main tree's current branch (usually `main`)
- 1 commit → `--ff-only`; several → `--no-ff`; 0 → already up to date
- pushes the target if `origin` exists
- `--rm` then runs `wt delete` (worktree + branch + tmux window)

`wt delete` / `wt rm` takes the worktree directory name under `.worktrees/`
(same name `wt new` used for the branch). It force-removes the worktree,
deletes that branch, and closes the tmux window. Uncommitted changes
prompt. Use only to abandon; landing already deletes via `--rm`.

Detect checkout type:

```bash
test -f .git && echo "worktree" || echo "main repo"
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

## Public Exposure (host-side)

`jolo expose` runs on the HOST, not in a container. It forwards one project's
`$PORT` to the public host Caddy via a foreground `socat` on loopback slot
`127.0.0.1:9999`. Deny-by-default, one project at a time, torn down on Ctrl-C.

```sh
jolo expose   # pick/current project -> public at pub.glvortex.net while running
```

`jolo publish` gives a project a stable public hostname with basic auth;
`jolo expose` is the ephemeral one-at-a-time alternative. Both are HOST-side.

```bash
jolo publish              # https://<name>.pub.glvortex.net, password shown once
jolo publish --rotate     # new password
jolo publish --no-auth    # open to the internet, requires typing YES
jolo unpublish
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

Phone-first checks. `--width` takes a comma-separated list (or repeats), runs
each width in its own context from one browser launch, and suffixes the output
when there is more than one. `--height` defaults to 844 and only applies with
`--width`. `--overflow` exits 1 if the page scrolls sideways, so it works in a
hook; elements inside an `overflow-x: auto|scroll` box are not flagged.

```bash
browser-check http://localhost:$PORT --overflow --width 320,390,430
browser-check http://localhost:$PORT --screenshot --width 320,390,430 --output scratch/p.png
# -> scratch/p-320.png, scratch/p-390.png, scratch/p-430.png (one width: verbatim)
```

`file://` URLs work, and are the normal way to check a static prototype before
it becomes a page:

```bash
browser-check file:///tmp/prototype.html --overflow --width 320
```

With `--json` the per-width results are in `viewports[]` (`width`, `height`,
`console`, `errors`, `screenshot`, `overflow`), not at the top level.

```bash
playwright-cli open http://localhost:$PORT
playwright-cli snapshot
playwright-cli click e1
playwright-cli fill e2 "hello"
playwright-cli screenshot
playwright-cli close
```

For advanced flows, write a small Node.js Playwright script.

## Fetching Assets

Both tools above render pages and cannot save an arbitrary file. `fetch-asset`
downloads one, refusing to leave anything at the destination unless the bytes
are what the extension claims:

```bash
fetch-asset https://example.org/drawing.png public/art/drawing.png
FETCH_ASSET_UA="myproject/2.0 (+mailto:me@example.org)" fetch-asset "$url" out.svg
```

Non-2xx, an empty body, or an HTML page landing at a binary extension all exit
non-zero and write nothing — the failure bare `curl` hides by saving a 403 page
as a `.png` that renders blank. Ships from `container/fetch-asset`.

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
