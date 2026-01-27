# /scaffold-api

Scaffold a new API project with standard configuration.

## Arguments

- `name` (required): Project name
- `--stack`: `fastapi` (default) or `elysia`
- `--port`: Port number (default: 4000, must be 4000-5000)

## Instructions

1. Create the project directory if it doesn't exist
2. Based on the stack:

**FastAPI (Python):**
- Initialize with `uv init` or create pyproject.toml
- Add dependencies: fastapi, uvicorn
- Create `src/main.py` with:
  - Health endpoint at `GET /health`
  - CORS middleware configured
  - Uvicorn configured to run on specified port
- Create `src/__init__.py`
- Add a `Makefile` with `dev`, `test`, `lint` targets
- Configure ruff for linting

**Elysia (Bun):**
- Initialize with `bun init`
- Add dependencies: `bun add elysia @elysiajs/cors`
- Create `src/index.ts` with:
  - Health endpoint at `GET /health`
  - CORS plugin configured
  - Listening on specified port
- Create tsconfig.json with Bun types
- Add scripts to package.json:
  - `dev`: `bun --watch src/index.ts`
  - `start`: `bun src/index.ts`
  - `lint`: `bun run biome check`
- Add biome for linting: `bun add -d @biomejs/biome && bun biome init`

3. Create a `.gitignore` appropriate for the stack
4. Create a minimal `README.md` with run instructions
5. Initialize git if not already in a repo

## Example Usage

```
/scaffold-api myservice
/scaffold-api myservice --stack elysia --port 4001
```
