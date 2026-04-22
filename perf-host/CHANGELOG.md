# Changelog

## Unreleased

### Added
- Cross-project overview Grafana dashboard (`uid: perf-host-overview`).
  Filters by project / branch / testbed (multi + all). Panels: distinct
  test runs, distinct projects, total/failed reqs, p99 by project+route
  over time, RPS by project+route, recent-runs table.
- Bundled Speedscope viewer (v1.25.0) at `/viewer/`. Loaded from npm's
  `dist/release/`, not GitHub releases (which Speedscope no longer ships).
- `tests/` with 22 unit tests covering schema validation and k6 script
  generation. Run with `uv run pytest tests/` or `just test`.
- `pyproject.toml` with `dev` dependency group (pytest, ruff).
- `justfile` for common ops: `just up | down | nuke | demo | runs |
  projects | health | test | render | overview | last-run-dashboard`.
- `docs/bencher-integration.org` — full design plan for adding
  commit-aware regression detection.
- Single-flight lock on `/api/run` — concurrent runs corrupt each
  other's measurements. Returns `429` if a run is in progress.
- `/api/projects` endpoint with run counts and last-run pointer per
  project.
- `/api/debug/render` returns the k6 script that *would* run for a
  given rig, without executing.
- Run ledger persists script under `/srv/profiles/<run_id>.k6.js` for
  post-hoc inspection via `/profiles/`.
- `run_in_progress` field in `/api/health`.

### Fixed
- **k6 metric labels not propagating.** `K6_PROMETHEUS_RW_EXTRA_LABELS`
  env var, `--tag` CLI flags, and `options.tags` are all silently
  ignored by k6 0.55's `experimental-prometheus-rw` output for
  `k6_http_*` metrics. The only mechanism that lands custom labels on
  every metric is per-scenario `tags:` in the script. Generator now
  merges run-level tags (`project`, `sha`, `branch`, `testbed`,
  `run_id`, `testid`) into every scenario's tags block. Belt-and-
  suspenders also sets the other three mechanisms.
- **Dashboard 19665 panels were empty.** Every panel filters by
  `{testid=~"$testid"}`. We now tag every run with `testid=<run_id>` so
  the official k6 dashboard works out of the box.
- **Validity gate misfired.** Trigger was treating `k6 exit 99`
  (regression threshold crossed) as a validity failure. Validity is
  now decided from the parsed `--summary-export` JSON: dropped
  iterations and failure rate. Regression is owned by k6 thresholds
  (and eventually Bencher).
- **`dropped_iterations` k6 threshold caused false fails** when the
  metric had no samples. Removed from k6 thresholds; checked from
  the summary instead.
- **Caddy redirect loop on `/grafana/`.** `handle_path` was stripping
  the prefix before proxying; Grafana with `serve_from_sub_path=true`
  added it back. Replaced with named matcher `@grafana` and `handle`.
- **Duplicate `run_id` returned 500.** Now returns clean `409`.
- **`go-httpbin` command override broke entrypoint.** Dropped the
  override; default port 8080 is what we want.
- **Hostname inconsistency.** README + curl examples use the FQDN
  (`berghome.ts.glvortex.net:8888`) consistently — the short name
  only resolves inside the devcontainer.

### Changed
- Grafana dashboards now live in `grafana/dashboards/` (not inside
  `provisioning/`), provisioner config points there.

### Documented (in stash)
- `20260421T143229--perf-hub-design-decisions-after-codex-review-2026-04-21`
  — architecture decisions: Prom-rw vs OTel, VM vs ClickHouse, Bencher,
  SUT model, perf-rig.toml schema pitfalls, run ledger.
- `20260421T192336--k6-0.55-prom-rw-only-per-scenario-tags-propagate`
  — gotcha note on the k6 label propagation issue.
- `20260421T192408--podman-compose-build-cache-stale-copy-layer`
  — gotcha note on the podman build cache pitfall.

### Known issues
- Grafana admin password is `dev123` (changed from initial `admin`).
  Reset via `podman exec perf-host_grafana_1 grafana-cli admin reset-admin-password <new>`.
- `target.mode = "ephemeral_container"` is reserved in the schema but
  `_run_locked` rejects it with `501`. Implementation belongs in the
  Bencher integration session.

## 0.1.0 — 2026-04-21

Initial perf-host MVP. Caddy + VictoriaMetrics + Grafana + FastAPI
trigger + go-httpbin demo target. Auto-provisioned k6 Prometheus
dashboard. SQLite run ledger. Pydantic-validated `perf-rig.toml` v1
schema with `external_url` and `ephemeral_container` target modes.
