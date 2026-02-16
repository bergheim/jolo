# TypeScript BETH Stack Scaffold

## Context

TODO.org item: "Generated projects should include a stub HTTP service with hot reload (including browser reload)." Currently `jolo create myproject --lang typescript` produces a bare Bun project with no web framework, no HTTP server, and no browser-visible page. AI agents can't verify web work because there's nothing to curl or screenshot.

The goal: `jolo create myproject --lang typescript` produces a working BETH stack app (Bun + Elysia + Tailwind + HTMX) with SSR, hot reload, a health endpoint, and a browser-accessible page — all on `$PORT`.

## Stack decisions

| Layer | Tool | Why |
|-------|------|-----|
| Runtime | Bun | Already installed, fast, all-in-one |
| Framework | Elysia | Bun-native AOT, best type safety (Eden), built-in TypeBox validation, 1-line OpenAPI. Already used in scaffold-api skill. |
| SSR | @elysiajs/html (@kitajs/html) | JSX templates server-rendered, no client-side framework |
| Interactivity | HTMX (npm, vendored) | 14KB, served from public/, no CDN dependency |
| Styling | Tailwind v4 (@tailwindcss/cli) | Local build via `just css`, no CDN. Dev uses `--watch`. |
| Validation | TypeBox (Elysia built-in) | No extra dep needed. Standard Schema support for Zod swap later. |

## What gets scaffolded

After `jolo create myapp --lang typescript`:

```
myapp/
├── src/
│   ├── index.tsx              # Elysia server: routes, plugins, listen on $PORT
│   ├── styles.css             # Tailwind entry: @import "tailwindcss"
│   ├── pages/
│   │   └── home.tsx           # Home page with HTMX demo button
│   ├── components/
│   │   └── layout.tsx         # HTML shell: <head>, local CSS/JS, <body>
│   └── example.test.ts        # Tests: health endpoint, hello API
├── public/                    # Static files (served by @elysiajs/static)
│   └── .gitkeep               # styles.css + htmx.min.js built/copied here
├── justfile                   # dev, css, run, test, test-watch, browse, add
├── tsconfig.json              # strict + JSX config
├── .pre-commit-config.yaml    # biome + base hooks
└── ... (devcontainer, AGENTS.md, etc.)
```

Container init commands install deps:
```
bun init && rm -f index.ts && bun add elysia @elysiajs/html @elysiajs/static @kitajs/html htmx.org && bun add -d tailwindcss @tailwindcss/cli
```

Post-install init command copies HTMX to public/ and builds Tailwind CSS:
```
cp node_modules/htmx.org/dist/htmx.min.js public/ && bunx @tailwindcss/cli -i src/styles.css -o public/styles.css
```

`just dev` runs Tailwind `--watch` in background + `bun --hot src/index.tsx` → server at `http://0.0.0.0:$PORT` with hot reload. No network needed after initial `bun install`.

## Files to modify

### 1. New template files

**`templates/lang/typescript/src/index.tsx`**
Elysia entry point: html plugin, static plugin, home page route, `/health` JSON endpoint, `/api/hello` endpoint with query param validation via `Elysia.t`. **Exports `app` for testability. Wraps `app.listen()` in `if (import.meta.main)` guard** so test imports don't bind a real port. Listens on `0.0.0.0:$PORT`.

**`templates/lang/typescript/src/styles.css`**
Tailwind v4 entry point: just `@import "tailwindcss"`. Built to `public/styles.css` by `just css`.

**`templates/lang/typescript/src/pages/home.tsx`**
JSX page component. Renders heading, description, HTMX demo button that calls `/api/hello` and renders response into a `<pre>` tag. Uses Tailwind utility classes.

**`templates/lang/typescript/src/components/layout.tsx`**
JSX layout wrapper. `<html>`, `<head>` with local `/styles.css` + `/htmx.min.js` from `public/`, `<body>` wrapping children. No CDN references.

**`templates/lang/typescript/public/.gitkeep`**
Empty file so `public/` dir is committed. `htmx.min.js` and `styles.css` are generated (gitignored).

**NOTE:** `templates/.gitignore` line 189 has a blanket `public/` ignore (Gatsby leftover). Must add `!public/` exception to un-ignore it for TypeScript projects, or remove the Gatsby `public/` entry entirely (it's under a Gatsby comment — no other language uses this pattern). **Decision: remove the Gatsby `public/` line** since our universal gitignore shouldn't ignore a common directory name. Add `public/*.css` and `public/*.js` ignores for generated assets instead.

### 2. Update existing template files

**`templates/lang/typescript/justfile`**
- Change `bun --hot src/index.ts` → `bun --hot src/index.tsx`
- Change `bun run src/index.ts` → `bun run src/index.tsx`
- Change `fd -e ts |` → `fd -e ts -e tsx |`
- Add `css` recipe: `bunx @tailwindcss/cli -i src/styles.css -o public/styles.css`
- Add `css-watch` recipe: same with `--watch`
- Update `dev` recipe: run `css-watch` backgrounded + `bun --hot src/index.tsx`
- Add `setup` recipe: `cp node_modules/htmx.org/dist/htmx.min.js public/ && just css`

**`templates/lang/typescript/example.test.ts`**
Replace trivial tests with Elysia endpoint tests using `app.handle(new Request(...))` pattern (no actual server needed). Test `/health` returns `{status: "ok"}` and `/api/hello?name=Test` returns correct greeting.

### 3. Update `_jolo/templates.py`

**`get_type_checker_config('typescript')`** — Add to tsconfig compilerOptions:
```json
"jsx": "react-jsx",
"jsxImportSource": "@kitajs/html"
```

**New function `get_scaffold_files(language)`** — Returns list of `(rel_path, content)` tuples for app source files. Keeps scaffold files separate from test framework config (avoids architecture leak):
```python
def get_scaffold_files(language):
    if language == "typescript":
        return [
            ("src/index.tsx", _read_template("lang/typescript/src/index.tsx")),
            ("src/styles.css", _read_template("lang/typescript/src/styles.css")),
            ("src/pages/home.tsx", _read_template("lang/typescript/src/pages/home.tsx")),
            ("src/components/layout.tsx", _read_template("lang/typescript/src/components/layout.tsx")),
            ("public/.gitkeep", ""),
        ]
    return []
```

**`get_project_init_commands('typescript')`** — Replace current commands:
```python
# Before: ["bun", "init"], ["mkdir", "-p", "src"], ["mv", "index.ts", "src/index.ts"]
# After:
commands.append(["bun", "init"])
commands.append(["rm", "-f", "index.ts"])
commands.append(["bun", "add", "elysia", "@elysiajs/html", "@elysiajs/static", "@kitajs/html", "htmx.org"])
commands.append(["bun", "add", "-d", "tailwindcss", "@tailwindcss/cli"])
commands.append(["cp", "node_modules/htmx.org/dist/htmx.min.js", "public/"])
commands.append(["bunx", "@tailwindcss/cli", "-i", "src/styles.css", "-o", "public/styles.css"])
```

**NOTE:** The last two commands (cp htmx, build CSS) run inside the container via `devcontainer exec` during `jolo create`. They depend on `bun add` having completed and scaffold files being written. Order in `get_project_init_commands()`: bun init → rm index.ts → bun add deps → bun add devDeps → cp htmx → build css.

### 4. Update `_jolo/commands.py`

**`run_create_mode()`** — After the existing example test file writing block (~line 925), add handling for scaffold files (calls `get_scaffold_files()`, not test config):
```python
for rel_path, content in get_scaffold_files(language):
    file_path = project_path / rel_path
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_text(replace_placeholders(content))
    verbose_print(f"Wrote: {rel_path}")
```

### 5. Update tests

**`tests/test_integration.py`**:
- `test_create_writes_test_framework_config_for_typescript` — Check for `elysia` import in example test instead of just `bun:test`
- `test_create_writes_type_checker_config_for_typescript` — Also check for `jsx` and `jsxImportSource` in tsconfig
- Add `test_create_writes_beth_source_files` — Verify src/index.tsx, src/pages/home.tsx, src/components/layout.tsx exist

**`tests/test_templates.py`**:
- Add test that `get_project_init_commands('typescript')` includes `bun add elysia`
- Add test that `get_scaffold_files('typescript')` returns expected file list
- Add test that `get_scaffold_files('python')` returns empty list (no scaffold yet)
- Add test that tsconfig includes JSX settings

## Verification

1. `just test` — all existing + new tests pass
2. `just lint` — no ruff violations
3. Manual smoke test (optional): `jolo create testapp --lang typescript -d`, then inside container: `just dev` should start Elysia on $PORT, `curl localhost:$PORT/health` returns `{"status":"ok"}`, `curl localhost:$PORT` returns HTML with HTMX

## Out of scope

- Other languages (Python/Go/Rust hot reload) — separate branches
- Database integration (Turso/Drizzle) — not needed for scaffold baseline
- Eden RPC client setup — backend-only scaffold for now
