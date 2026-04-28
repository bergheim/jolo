---
name: j-scaffold-web
description: Scaffold a new frontend web project with Vite, Tailwind CSS, and standard configuration. Supports React, Svelte, and Vue frameworks.
---

# /j-scaffold-web

Scaffold a new frontend web project with Vite and standard configuration.

## Arguments

- `name` (required): Project name
- `--framework`: `react` (default), `svelte`, or `vue`

## Instructions

1. Create the project using Vite:
   ```bash
   pnpm create vite <name> --template <framework>-ts
   ```

2. Change into the project directory and install dependencies:
   ```bash
   cd <name> && pnpm install
   ```

3. Add and configure Tailwind CSS:
   ```bash
   pnpm add -D tailwindcss postcss autoprefixer
   pnpm tailwindcss init -p
   ```

4. Configure the dev server to bind to `0.0.0.0` and use `$PORT`:
   ```ts
   server: {
     host: "0.0.0.0",
     port: Number(process.env.PORT ?? 4000),
   }
   ```

5. Set up Tailwind in the main CSS file with the standard directives.

6. Update `package.json` scripts:
   - `dev`: runs the dev server on `$PORT`
   - `build`: builds for production
   - `preview`: uses `0.0.0.0`

7. Create a basic folder structure:
   ```
   src/
     components/
     styles/
   ```
   Use `hooks/` for React, `lib/` for Svelte or Vue if needed.

8. Replace the starter screen with a minimal page that proves Tailwind is wired correctly.

9. If the project uses this repo's devcontainer conventions, ensure:
   - `just dev` is the default development entrypoint
   - browser verification uses `http://localhost:$PORT`
   - generated instructions prefer `pnpm` over `npm`

10. Initialize git if not already in a repo.

## Example Usage

```
/j-scaffold-web myapp
/j-scaffold-web dashboard --framework svelte
```
