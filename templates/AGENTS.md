# AGENTS.md

Guidelines for AI coding assistants working on this project.

Generated: <YYYY-MM-DD>

## Communication

Assume the user is an experienced developer. Skip basic explanations, don't over-qualify statements, and don't pad responses with filler ("great question!", "certainly!").

Disagree when you have evidence. If the user's approach has a flaw or you see a better alternative, say so directly with your reasoning — don't just go along with it. Pushback leads to better discussions and a better product. A wrong agreement costs more than a brief debate.

## Project Memory

### Structured files

| File | Purpose |
|------|---------|
| `docs/PROJECT.org` | Project context, architecture, key decisions |
| `docs/TODO.org` | Actionable work items |

**Before any implementation:** If `docs/PROJECT.org` doesn't exist, do not start coding. First discuss with the user: what is this project, who is it for, what are the key constraints and architectural decisions? Write the answers to `docs/PROJECT.org` before proceeding.

### Denote notes (`docs/notes/`)

Per-topic knowledge notes following denote's filename convention. Each note is a
single topic in its own file. Notes are write-once: to add to a topic, create a
new note and reference the original.

**Filename format:** `YYYYMMDDTHHMMSS--title-slug__kind_topic1_topic2.org`

This rule also applies to newly-created custom `.org` files elsewhere under
`docs/`. Do not create ad hoc names like
`docs/SOME_ARCHITECTURE_SUGGESTION.org`; use a denote-style filename instead.
The exceptions are established structured files with fixed names such as
`docs/PROJECT.org` and `docs/TODO.org`.

**Note kinds** (fixed vocabulary, always the first keyword):
`memory`, `research`, `decision`, `gotcha`, `convention`, `incident`

**Creating notes via emacsclient:**

```bash
emacsclient -e '(bergheim/agent-denote-create "docs/notes" "Title here" (quote ("kind" "topic1" "topic2")) "Body text.")'
```

**Finding notes:**

```bash
# All notes with keyword "emacs"
emacsclient -e '(bergheim/agent-denote-find "docs/notes" (quote ("emacs")))'

# List 10 most recent
emacsclient -e '(bergheim/agent-denote-list "docs/notes")'
```

**Linking notes:**

```bash
# Add links from one note to related notes (idempotent, appends "Related notes" section)
emacsclient -e '(bergheim/agent-denote-link "/abs/path/to/source.org" (quote ("/abs/path/to/target1.org" "/abs/path/to/target2.org")))'
```

Link when there is a real semantic relationship (one note explains, caused, or
depends on another). Do not link just because notes share a keyword.

**On session start:**
1. Read `docs/PROJECT.org` and `docs/TODO.org`
2. Scan note filenames: `(bergheim/agent-denote-list "docs/notes")`
3. Read full content of notes relevant to current task

**On discoveries:** Create a new denote note with the appropriate kind and topics.
Link to existing related notes.

### Stash notes (`/workspaces/stash/notes/`)

Cross-project knowledge belongs in stash notes. If a discovery would still be
useful in an unrelated project or for host-level workflow, save it in
`/workspaces/stash/notes` instead of only in `docs/notes/`.

Use this heuristic:
- Would I want this loaded at session start in an unrelated project?

If yes, it belongs in stash. If the note depends on this repo's files, paths,
branches, or local architecture, it is project-specific and belongs in
`docs/notes/`.

It is fine to write both:
- a local incident note in `docs/notes/`
- a separate generalized note in `/workspaces/stash/notes/`

When working on shared tooling, devcontainer workflow, Emacs, org-mode, denote,
agent behavior, or other cross-project infrastructure, also scan stash note
filenames and read relevant stash notes before acting:

```bash
emacsclient -e '(bergheim/agent-denote-list "/workspaces/stash/notes" 15)'
```

### Personal memory

Agent-specific files (not shared):
- Claude: `.claude/MEMORY.md`
- Gemini: `.gemini/MEMORY.md`
- Codex: `.codex/MEMORY.md`
- Pi: `.pi/MEMORY.md`

Use personal memory for workflow preferences and agent-specific learnings.
Use denote notes for anything another agent would benefit from knowing.

Shared, non-reproducible resources across projects go in the stash: host `~/stash` is mounted at `/workspaces/stash` in devcontainers.

`scratch/` is a gitignored directory for experiments, generated assets, and throwaway work. Do not treat its contents as project code.

## Screenshots

When the user says they took a screenshot, read the latest one:

```bash
ls -t /workspaces/stash/shot-*.png | head -1
```

Then use the Read tool on that file to view it.

## Task Tracking

`docs/TODO.org` is the active work log, not a reference document. Treat it as the single source of truth for what needs doing.

- **Before starting work**: check TODO.org for existing tasks — don't duplicate effort
- **When you complete a task**: mark it `DONE` immediately, not at the end of the session
- **When you discover new work**: add it as a `TODO` heading right away
- **When a task is no longer relevant**: mark it `CANCELLED` with a reason
- **Never delete body text** when closing a TODO — the original description, context, and notes are valuable history. The reason goes in the LOGBOOK, not as a replacement for the body.

### Autonomous TODO conventions (`:autonomous:` tag)

`jolo autonomous` dispatches TODO items tagged `:autonomous:` to a fresh
agent without user interaction. Tagging the wrong thing dispatches risky
work into a context where there's no human to course-correct. So:

**Eligibility — a TODO is `:autonomous:` only if all of these hold:**

- **Bounded** — the agent can verify "done" itself (tests pass, files
  compile, etc.). No "looks good?" judgment calls.
- **In-container** — no host-side steps. No Emacs-host, systemd, host
  package installs, sudo on host, `tailscale set …`. Everything
  happens inside the dispatched container.
- **Non-destructive** — no force-push, no `rm -rf` outside `scratch/`,
  reversible by `git reset` + branch delete. If a step is hard to undo
  it disqualifies the item.
- **No external prompts** — no plugin auth dances, GitHub UI clicks,
  trust dialogs, MFA, browser logins. The agent runs to completion or
  errors out.
- **No decisions pending** — body that says "decide X first" or
  "consider whether Y" disqualifies until the decision is made.
- **Fits one branch.**
- **Body is a self-contained prompt** for the dispatched agent. If
  reading the heading + body doesn't tell a fresh agent what to do,
  it's not ready.

**Tagging workflow:**

- Tag only via the helper, never via text-edit:
  ```bash
  emacsclient -e '(bergheim/agent-org-add-tag "docs/TODO.org" "TODO Heading regex" "autonomous")'
  ```
- **Per-item agreement required.** No bulk retagging. When a TODO
  looks eligible, raise it with the user, get explicit OK, then tag.
- Removing the tag uses `bergheim/agent-org-remove-tag` with the same
  ergonomics.

If a dispatched run errors, the agent should mark the heading
`BLOCKED` (waiting on a system) or `WAITING` (waiting on a person)
with a reason note, never silently abandon.

### Editing org files with emacsclient

**Always use `bergheim/agent-org-set-state` for org state changes** — never manually
edit TODO/DONE keywords with a text editor. Org-mode adds CLOSED timestamps, LOGBOOK
entries, and state transition metadata automatically. The helper handles buffer
staleness, note capture, and save in one call.

**Mark a TODO as DONE:**

```bash
emacsclient -e '(bergheim/agent-org-set-state "docs/TODO.org" "TODO Heading text here" "DONE")'
```

**Mark as DONE with a reason note:**

```bash
emacsclient -e '(bergheim/agent-org-set-state "docs/TODO.org" "TODO Heading text here" "DONE" "Resolved by commit abc1234.")'
```

**Cancel a TODO with a reason:**

```bash
emacsclient -e '(bergheim/agent-org-set-state "docs/TODO.org" "TODO Heading text here" "CANCELLED" "No longer relevant because X.")'
```

This produces proper org metadata:

```org
** CANCELLED The task heading
CLOSED: [2026-04-13 Mon 12:08]
:LOGBOOK:
- State "CANCELLED"  from "TODO"  [2026-04-13 Mon 12:08] \\
  No longer relevant because X.
:END:
   Original body text preserved here...
```

Available states: `TODO`, `NEXT`, `INPROGRESS`, `WAITING`, `BLOCKED`, `DONE`, `CANCELLED`.

`BLOCKED` means "stalled on an external dependency" (vendor response, upstream
bug, cert renewal, etc.). Use `WAITING` for "waiting on a person" and `BLOCKED`
for "waiting on a system." When `:clock t` is passed to `set-state`, transitions
to `BLOCKED` close an active clock — this is a project policy choice, not an
org-mode semantic.

### Additional org helpers

All of these share the same ambiguity-safe heading lookup — if the regex matches
multiple headings, the helper errors and lists the line numbers so you can
disambiguate.

**Add a log note without changing state:**

```bash
emacsclient -e '(bergheim/agent-org-add-note "docs/TODO.org" "TODO Heading" "Made progress on X.")'
```

**Ensure a stable `:ID:` property:**

```bash
# Full plist response (default):
emacsclient -e '(bergheim/agent-org-ensure-id "docs/TODO.org" "TODO Heading")'
# When you only need the id string:
emacsclient -e '(plist-get (bergheim/agent-org-ensure-id "docs/TODO.org" "TODO Heading") :id)'
```

**Transition by `:ID:` (immune to heading renames and duplicate headings):**

```bash
emacsclient -e '(bergheim/agent-org-set-state-by-id "docs/TODO.org" "abc-def-123" "DONE")'
```

**Track time on a transition (clock in on INPROGRESS, clock out on DONE/BLOCKED/CANCELLED):**

```bash
# Signature: set-state FILE HEADING-RE STATE &optional NOTE ENSURE-SESSION-ID CLOCK
emacsclient -e '(bergheim/agent-org-set-state "docs/TODO.org" "TODO Heading" "INPROGRESS" nil t t)'
```

The 5th arg (`ensure-session-id`) auto-adds `:SESSION_ID:` on INPROGRESS so logs
and notifications can correlate back to the TODO. The 6th arg (`clock`) drives
`org-clock-in`/`org-clock-out`.

**Tag management:**

```bash
# Add :autonomous: tag (idempotent)
emacsclient -e '(bergheim/agent-org-add-tag "docs/TODO.org" "TODO Heading" "autonomous")'

# Remove a tag (idempotent)
emacsclient -e '(bergheim/agent-org-remove-tag "docs/TODO.org" "TODO Heading" "autonomous")'
```

### Helper return contract

Every `bergheim/agent-org-*` and `bergheim/agent-denote-*` helper returns
a plist. The canonical key is `:wrote` — a list of absolute file paths
the helper modified on disk, possibly empty when the operation was
idempotent (state already matched, tag already present, ID already
assigned, link already there).

**Always re-Read every path in `:wrote` before any subsequent Edit.**
The harness mtime-checks every Read→Edit pair; a helper's invisible
write between them makes the next Edit fail with "File has been
modified since read." Treat `:wrote` as ground truth — don't rely on
mtime, which has 1-second resolution on older filesystems and can race
within the same second.

Other plist keys are helper-specific (`:state`, `:state-from`,
`:heading`, `:id`, `:title`, `:path`, `:tags`, `:added`). Use
`(plist-get RESULT :key)` to extract.

## Emacs

Emacs runs as a daemon in the container. Use `emacsclient --eval '(expr)'` to query state, check modes, read variables, or run diagnostics — never ask the user to run `M-x` or `M-:` manually.

## Port Configuration

**The port is `$PORT`. It is NOT 4000.** Always use `$PORT` in every command,
URL, and tool invocation. Never hardcode a port number. Run `echo $PORT` if
you need the current value.

**The dev server is ALWAYS running.** Assume `just dev` is running on `$PORT`
with `--reload`. It auto-reloads on file changes. NEVER start a temporary
server on another port for screenshots or testing — just use the running dev
server directly: `browser-check http://localhost:$PORT/page --screenshot`.

**Always bind to `0.0.0.0`**, not `localhost` or `127.0.0.1`. Container networking requires it — `localhost` inside the container is not reachable from outside.

**Servers** (bind to `0.0.0.0`):

| Framework | Configuration |
|-----------|---------------|
| Vite | `vite --host 0.0.0.0 --port $PORT` |
| Next.js | `next dev -H 0.0.0.0 -p $PORT` |
| Flask | `flask run --host 0.0.0.0 --port $PORT` |
| FastAPI | `uvicorn app:app --host 0.0.0.0 --port $PORT` |
| Go | `http.ListenAndServe(":"+os.Getenv("PORT"), nil)` |

**Clients** (connect to `localhost`):

| Tool | Command |
|------|---------|
| browser-check | `browser-check http://localhost:$PORT ...` |
| curl | `curl http://localhost:$PORT/healthz` |
| playwright-cli | `playwright-cli open http://localhost:$PORT` |

## Notifications

Push notifications fire automatically when you finish a response (via hooks).
For web projects, the notification includes an "Open app" button linking to the
dev server URL. By default it points to `/`.

When working on a specific page or route, set the notification path so the
button links there instead:

```bash
notify set-path /dashboard
notify set-path /article/123
notify set-path /          # reset to root
```

This persists across responses until changed. Set it whenever you start working
on a specific route so the user can tap the notification and land on the right
page.

## Sharing files to the local laptop

`share <file-or-dir>` copies the target into the host stash and
prints a tailnet URL (also OSC52-clipboarded). Paste in your laptop
browser to view — images, PDFs, anything the browser can render.

```sh
share foo.png        # → http://<host>.<tailnet>:8080/<project>/foo.png
share .              # share the current dir; browser shows the index
share /path/to/file  # absolute paths work too
```

Host one-time setup:

```sh
sudo tailscale set --operator=$USER
tailscale serve --bg --http 8080 ~/stash/share
echo 'export SHARE_BASE_URL=http://<host>.<your-tailnet>:8080' >> ~/.zshrc
```

`SHARE_BASE_URL` flows from host `~/.zshrc` into containers via the
existing zshrc bind-mount, same pattern as `PERF_HOST` and `LLAMA_HOST`.
Without it, `share` still copies to stash and prints the local path.

## Development Workflow

Use `just` recipes for common tasks. **Always use `just dev`** — it auto-reloads on file changes. Only use `just run` for one-off executions (e.g., scripts, CLI tools).

| Recipe | Purpose |
|--------|---------|
| `just dev` | Run with auto-reload (use this for development) |
| `just run` | Run once without watching |
| `just test` | Run tests |
| `just test-watch` | Run tests on file change |
| `just add X` | Add a dependency |
| `just perf` | Submit `perf-rig.toml` to the host-side perf hub |
| `just wt` | Manage git worktrees (list/new/land/rm) — wraps the `wt` binary |

**Custom commands belong in the justfile.** `just --list` is the menu — it's how the user (and agents reading a project for the first time) discover what a project can do. When you add or wire up a command — a wrapper, a helper, a project-specific workflow, even a thin shim around a container-provided binary like `wt` or `share` — give it a justfile recipe with a `# comment` description so it appears in `just --list`. A binary that exists in `/usr/local/bin` but has no justfile entry is invisible: nobody knows to run it. Don't tell the user to "drop `just` and run the binary directly" — fix the justfile instead.

**fzf-pick by default for names of generated things.** When a command takes the name of something the tool generated — a worktree, project, container, branch, session, scaffolded artifact, anything from a known finite set the user can't be expected to remember exactly — it should fzf-pick when no name is supplied, `fzf` is on `PATH`, and stdin is a TTY. Fall through to a clean `error: name required` exit otherwise so non-interactive callers (CI, scripts) stay deterministic. Don't make people retype names they could pick from a list — they'll forget anyway, and the lookup roundtrip (`just wt ls` → squint → retype) is exactly the friction fzf eliminates. Apply this everywhere it fits: `wt land`/`wt rm`, project-name args in jolo subcommands, anything that takes a session/container id, etc.

**Dev server log:** `just dev` runs automatically in a tmux window and logs all output (stdout + stderr) to `dev.log` at the project root. Read this file to check server output, errors, and request logs without needing access to the dev server's tmux pane.

## Cross-container podman access

Off by default per project. When allowed, `podman` inside the
devcontainer is a remote client of the host's rootless podman daemon,
so you can reach sibling jolo containers:

```sh
podman ps                                  # all jolo containers on host
podman exec other-project ls /workspaces   # one-shot in a sibling
podman logs --tail 50 other-project        # tail another container's logs
```

Activation runs a host-side socat proxy at the project's gate path;
toggling it (`allow`/`deny`) flips the capability **instantly without
container recreation**. The first allow on a project still needs one
`--recreate` to retrofit the always-mount; after that, future toggles
take effect on the next `podman …` call inside the running container.

```sh
# on the host, NOT inside any container:
jolo allow podman <project>           # creates gate dir + starts socat
cd <project> && jolo up --recreate    # one-time retrofit

# later toggling — no recreate needed:
jolo deny podman <project>            # stops socat (gate dir stays)
jolo allow podman <project>           # restarts socat

# what's running:
jolo allowed                          # list projects with podman state
```

The gate directory `~/.config/jolo/podman-runtime/<project>/` is
host-only — not bind-mounted into any devcontainer in a writable
location — and `jolo` itself only exists on the host. An agent inside
a container literally cannot read or write the gate path or invoke
the CLI; activation has to be a deliberate host-side act.

When not allowed: `podman` errors with `Cannot connect to Podman …
no such file or directory`. That's the "off" state, not a bug — fix
by allowing on the host.

Host requires `socat` (apk, pacman, etc.). `jolo allow` errors
cleanly with an install hint if missing.

## Performance

`just perf` posts the project's `perf-rig.toml` to the host-side perf hub. Set `PERF_HOST` on the host (e.g. in `~/.zshrc`) — the value flows into devcontainers through the mounted `.zshrc`, same as `LLAMA_HOST`. The hub runs k6 from the host and writes metrics to Grafana keyed by `project`, `route_id`, `sha`, `run_id`, `testbed`.

The k6 worker lives on the host, so the target URL inside `perf-rig.toml` must be externally reachable — `localhost:$PORT` resolves to the trigger container and won't reach this project. `perf-rig.toml` keeps the target URL symbolic (`http://${DEV_HOST}:${PORT}`); the `perf` recipe resolves `DEV_HOST` from the container env, falling back to `PERF_HOST`'s hostname when needed. Nothing to edit by hand.

`testbed` defaults to `dev-container-<sanitized-project-name>` — the project name lowercased, with non-alphanumerics replaced by `-`, and internal underscores preserved (e.g. `My_App` → `my_app`). Override with `PERF_TESTBED` if a worktree or CI runner needs a distinct baseline.

## Frontend Verification

After making visible UI changes (markup, styles, component layout), verify before committing:

```bash
browser-check http://127.0.0.1:$PORT --screenshot --errors --output scratch/verify.png
```

Read the screenshot to confirm the result looks correct, and check the error output for JS exceptions. Don't commit frontend changes without verifying visually.

## Image Tooling

**Format preference:** AVIF > WebP > PNG/JPEG. AVIF has the best compression and 95%+ browser support. Use WebP as fallback for older browsers. PNG only for lossless needs (logos, icons with transparency).

**Tools available:**
- `vips`/`vipsthumbnail` — preferred for conversion, resizing, thumbnails (supports AVIF, WebP, JPEG, PNG)
- `avifenc`/`avifdec` — standalone AVIF encoding/decoding
- `cwebp`/`dwebp` — standalone WebP encoding/decoding

Do not add ImageMagick or Pillow unless the project explicitly requires them.

```bash
# Convert to AVIF (quality 30 = good balance)
vips copy input.png output.avif[Q=30]

# Convert to WebP
cwebp -q 80 input.png -o output.webp

# Resize and convert in one step
vipsthumbnail input.jpg -s 800x -o output.avif[Q=30]
```

## Accessibility & Semantic HTML

All web output must follow universal design principles. This is not optional polish — it is a baseline requirement.

### Structure

- Use semantic elements: `<main>`, `<nav>`, `<header>`, `<footer>`, `<section>`, `<article>`, `<aside>`
- One `<h1>` per page. Headings must follow hierarchy (`h1` → `h2` → `h3`) — never skip levels
- Add a skip-nav link as the first child of `<body>`: `<a href="#main" class="sr-only focus:not-sr-only">Skip to content</a>`
- Set `lang` attribute on `<html>` to the correct language (e.g., `lang="nb"` for Norwegian Bokmål)

### Forms & Interactive Elements

- Every `<input>` must have a visible `<label>` (or `aria-label` if the design hides it)
- Use `<button>` for actions, `<a>` for navigation — never `<div onclick>`
- All interactive elements must be keyboard-reachable and have visible focus styles
- Group related inputs with `<fieldset>` and `<legend>`

### Images & Media

- All `<img>` elements need `alt` text. Decorative images get `alt=""`
- Complex images (charts, diagrams) need extended descriptions
- Avoid text in images — use real text with CSS styling

### Color & Contrast

- Minimum 4.5:1 contrast ratio for normal text, 3:1 for large text (WCAG AA)
- Never convey information by color alone — add icons, patterns, or text labels

### Verification

**After any UI change, run `just a11y` before marking work as done.** This runs pa11y (WCAG 2.2 AA) against the dev server and reports violations with exact selectors and rule references. Fix all errors — they represent real barriers for real people.

```bash
# Full accessibility audit
just a11y

# Audit a specific page
just a11y --include-notices http://localhost:$PORT/some-page

# Quick structural check via ARIA tree
browser-check http://localhost:$PORT --aria

# Check only interactive elements (buttons, links, inputs)
browser-check http://localhost:$PORT --aria --interactive
```

### Reference

Follow [WCAG 2.2 AA](https://www.w3.org/WAI/WCAG22/quickref/?levels=aaa) as the minimum standard.

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

**Worktree awareness:** Check `.git` at session start — if it's a file (not a directory), you are in a worktree. All worktrees live under `/workspaces/`. You cannot checkout `main` here. Find the main tree and merge there:

```bash
# Detect: file = worktree, directory = main repo
test -f .git && echo "worktree" || echo "main repo"

# Merge from a worktree
MAIN=$(git worktree list | awk '/\[main\]/{print $1}')
git rebase main && git -C "$MAIN" merge $(git branch --show-current)
```

## Local Models (llama.cpp via llama-swap)

`LLAMA_HOST` points to a self-hosted [llama-swap](https://github.com/mostlygeek/llama-swap) router fronting `llama.cpp` servers on GPU. Use it for tasks where a free local model is good enough — drafting, summarization, embeddings, throwaway experiments — instead of burning API credits.

llama-swap speaks the OpenAI-compatible API and auto-loads/unloads the model named in the request. Requesting an unknown alias returns an error listing valid ones.

```bash
# List model aliases configured on the router
curl -s $LLAMA_HOST/v1/models | jq '.data[].id'

# Chat (set model to any alias from /v1/models — triggers swap if needed)
curl -s $LLAMA_HOST/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"gemma4","messages":[{"role":"user","content":"..."}]}'

# Text completion
curl -s $LLAMA_HOST/v1/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"gemma4","prompt":"..."}'

# Embeddings (use an embedding-model alias, e.g. bge-m3)
curl -s $LLAMA_HOST/v1/embeddings \
  -H "Content-Type: application/json" \
  -d '{"model":"bge-m3","input":"..."}'

# Anthropic-compatible messages API (tool use supported)
curl -s $LLAMA_HOST/v1/messages \
  -H "Content-Type: application/json" \
  -H "anthropic-version: 2023-06-01" \
  -d '{"model":"gemma4","max_tokens":1024,"messages":[{"role":"user","content":"..."}]}'
```

Python/JS SDKs that target the OpenAI API work with `$LLAMA_HOST/v1` as the base URL — pass any string as the API key. The `ollama` CLI is not installed (and would not work: `/api/tags` and other Ollama-native endpoints return 404). Stick to `/v1/*`.

Native llama.cpp endpoints (`/completion`, `/embedding`, `/tokenize`, `/props`, `/slots`, `/health`) are available on the underlying server but bypass llama-swap's routing — prefer `/v1/*` so the correct model is loaded on demand.

## Cross-Agent Reviews

When shelling out to another agent CLI for a code review or second opinion, **unset `ANTHROPIC_API_KEY` and `OPENAI_API_KEY`** so the agent uses its own CLI auth instead of falling back to direct API-key mode.

```bash
# Correct — uses CLI auth
echo "$diff" | env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY claude -p "Review this..."

# Wrong — may use API key billing instead of CLI auth
echo "$diff" | claude -p "Review this..."
```

This applies to `claude`, `codex`, and any agent that checks for API keys before falling back to OAuth/CLI credentials.

### Keep reviews lean

Default codex behavior is verbose: high reasoning effort, exploratory `sed`/`nl`/`rg` on every adjacent file, full test runs before writing a word. A 4-paragraph plan can produce 130KB of transcript and take 10 minutes. For a text-only review where the reviewer should just read what you piped in:

```bash
# Lean codex review — read-only sandbox, low reasoning, capture only the
# final message. Suppresses the exploration transcript entirely.
OUT=$(mktemp)
printf '%s\n' "$PROMPT_PREFIX" "$DIFF_OR_PLAN" | env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY codex exec \
  -s read-only \
  -c model_reasoning_effort=low \
  --ephemeral \
  -o "$OUT" - > /dev/null 2>&1
cat "$OUT"
rm -f "$OUT"
```

In the prompt itself, add an explicit scope directive:

> "Review only the text shown. Do not read other files, do not run commands or tests, do not search the codebase. Respond in under 300 words with findings and severity."

Same idea for gemini (no reasoning flag, but the prompt directive still helps):

```bash
printf '%s\n' "$PROMPT_PREFIX" "$DIFF_OR_PLAN" | env -u ANTHROPIC_API_KEY -u OPENAI_API_KEY gemini -p "Review only what's shown. No file reads, no commands. Under 300 words."
```

Use `codex review --uncommitted` (the dedicated subcommand) only when you genuinely want codex to explore the repo as part of the review. For "here's a diff, what's wrong" — use the lean invocation above.

## Code Quality

Pre-commit hooks are already installed. They run automatically on `git commit`. If a commit fails, fix the issues and commit again.

- **Never skip hooks**: NEVER use `git commit --no-verify`. Pre-commit hooks (ruff, format, tests, codespell) are the guardrails that keep code clean. If a hook blocks the commit, fix the underlying issue — add the word to the codespell allowlist, fix the lint error, fix the failing test. Skipping hooks to save time means shipping broken formatting, lint errors, and test failures that compound into a mess. No exceptions.

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

Use **Playwright CLI** for most tasks. It is stateful and writes snapshots/logs/artifacts to disk (`.playwright-cli/`) instead of streaming large payloads in chat. Use `browser-check` for quick, stateless audits.

### Tool Selection

Use this decision rule when both tools could work:

| Situation | Preferred Tool | Why |
|-----------|----------------|-----|
| Single URL health check, one screenshot, one-off console/error scan | `browser-check` | Faster, stateless, one command |
| Multi-step interaction (click/fill/navigate), auth/session reuse, repeated captures | `playwright-cli` | Stateful session, better for workflows |
| Debugging flow regressions | `playwright-cli` | Snapshots, traces, and session history |

| Task | Tool / Command |
|------|----------------|
| **Interactive Flow** | **Playwright CLI** (`playwright-cli`) |
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
# Stateful browser session (token-efficient)
playwright-cli open http://127.0.0.1:$PORT
playwright-cli -s=default snapshot
playwright-cli -s=default click e12
playwright-cli -s=default fill e20 "hello"
playwright-cli -s=default screenshot --filename scratch/after-click.png
playwright-cli -s=default close

# Check if dev server is up
browser-check http://127.0.0.1:$PORT --describe --console --errors

# Screenshot
browser-check http://127.0.0.1:$PORT --screenshot --output scratch/shot.png

# Get page structure for LLM
browser-check http://127.0.0.1:$PORT --aria --interactive --json
```

For multi-step interactive flows, prefer Playwright CLI sessions. The scaffold includes `.playwright/cli.config.json` configured for system Chromium on Alpine.

### Verification Standard

For browser verification tasks (for example: "is the site running?"), include all of the following in your report:

- URL and exact check time
- Command(s) used
- Evidence of success/failure (status code, page title, or key console/error lines)
- Artifact path when generated (save screenshots/PDFs to `scratch/`)

### Troubleshooting

- If `playwright-cli open` succeeds but `-s=<id>` commands fail, run `playwright-cli list` and use the listed session label (often `default`).
- If screenshots are blank or not the expected view, run `playwright-cli -s=<session> snapshot` first and confirm URL/title before capture.

Use the `browser-verify` skill when the request is to verify site availability, capture evidence, and report reproducible checks.
