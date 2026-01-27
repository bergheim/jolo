# /db-reset

Reset the local development database to a clean state.

## Arguments

- `--seed`: Run seed data after migrations (default: true)
- `--no-seed`: Skip seeding
- `--env`: Environment file to use (default: `.env` or `.env.local`)

## Instructions

1. **Detect the database type** by checking for:
   - `prisma/schema.prisma` -> Prisma (PostgreSQL/MySQL/SQLite)
   - `drizzle.config.ts` -> Drizzle
   - `alembic.ini` or `migrations/` with Python -> Alembic (SQLAlchemy)
   - `diesel.toml` -> Diesel (Rust)
   - `db/migrate/` -> Rails-style migrations
   - `*.db` or `*.sqlite` files -> SQLite
   - `docker-compose.yml` with postgres/mysql service -> Docker-based DB

2. **Confirm with the user** before proceeding (this is destructive):
   - Show which database will be reset
   - Show the connection string (redact password)

3. **Reset based on detected type:**

**Prisma:**
```bash
pnpm prisma migrate reset --force
# or if --no-seed: pnpm prisma migrate reset --force --skip-seed
```

**Drizzle:**
```bash
pnpm drizzle-kit drop
pnpm drizzle-kit migrate
pnpm tsx db/seed.ts  # if seed file exists and --seed
```

**Alembic:**
```bash
alembic downgrade base
alembic upgrade head
python -m db.seed  # if exists and --seed
```

**SQLite (direct):**
```bash
rm -f <database-file>
# Re-run migrations based on what's available
```

**Docker-based:**
```bash
docker compose down -v  # Remove volumes
docker compose up -d db
# Wait for healthy, then run migrations
```

4. **Run seeds** (unless `--no-seed`):
   - Look for `seed.ts`, `seed.py`, `db/seeds.rb`, `prisma/seed.ts`, etc.
   - Execute the appropriate seed command

5. **Report:**
   - Database reset complete
   - Number of migrations applied
   - Seed status

## Example Usage

```
/db-reset
/db-reset --no-seed
/db-reset --env .env.test
```
