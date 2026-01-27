# /scaffold-web

Scaffold a new frontend web project with Vite and standard configuration.

## Arguments

- `name` (required): Project name
- `--framework`: `react` (default), `svelte`, or `vue`
- `--port`: Port number (default: 4001, must be 4000-5000)

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

4. Configure `vite.config.ts` to use the specified port:
   ```typescript
   server: {
     port: <port>,
     host: true  // Allow external connections
   }
   ```

5. Set up Tailwind in the CSS file with standard directives

6. Update `package.json` scripts:
   - `dev`: should use the configured port
   - Ensure `build` and `preview` scripts exist

7. Create a basic folder structure:
   ```
   src/
     components/
     hooks/ (React) or lib/ (Svelte/Vue)
     styles/
   ```

8. Update the main App component with a minimal "Hello World" that demonstrates Tailwind is working

9. Initialize git if not already in a repo

## Example Usage

```
/scaffold-web myapp
/scaffold-web dashboard --framework svelte --port 4002
```
