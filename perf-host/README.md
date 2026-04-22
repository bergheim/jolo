# perf-host

One global host-side performance hub. Projects POST k6 metrics + Speedscope
profiles here; everything is queryable per project / route / commit.

Design notes:
- `/workspaces/stash/notes/20260421T123714--jolo-scaffolds-projects-into-one-global-perf-hub__decision_jolo_perf_scaffold_host-service.org`
- `/workspaces/stash/notes/20260421T140500--host-side-perf-observability-stack-design-2026__research_perf_observability_host-service.org`

## Layout

```
perf-host/
  Containerfile          # trigger image (FastAPI + k6)
  docker-compose.yml     # caddy, victoriametrics, grafana, trigger
  Caddyfile              # path-based routing
  trigger/main.py        # /health and /run stub for now
  grafana/provisioning/  # VM datasource auto-wired
  speedscope/            # drop the static viewer bundle here
  data/                  # gitignored: vm/ grafana/ profiles/
```

## Bring up

Works with either engine — `docker compose` or `podman compose`:

```sh
cd /workspaces/stash/perf-host
podman compose up -d --build       # or: docker compose up -d --build
```

Caddy listens on host port `8888`. Tailscale-only — no auth wired beyond
network reachability.

## Verify

```sh
curl -sS http://berghome.ts.glvortex.net:8888/                    # banner
curl -sS http://berghome.ts.glvortex.net:8888/api/health          # trigger + k6 version
curl -sS http://berghome.ts.glvortex.net:8888/vm/api/v1/status/buildinfo
curl -sS http://berghome.ts.glvortex.net:8888/grafana/api/health
```

Browse `http://berghome.ts.glvortex.net:8888/profiles/` for the directory listing of captured
Speedscope profiles. `http://berghome.ts.glvortex.net:8888/viewer/` serves the Speedscope
static bundle once you drop one into `speedscope/`.

## Speedscope bundle

Bundled (v1.25.0) — served at `/viewer/`. Speedscope no longer ships
release zips on GitHub; the `speedscope/` dir is the contents of
`node_modules/speedscope/dist/release/` from the npm package. To bump
the version:

```sh
cd /tmp && mkdir s && cd s
bun add speedscope@latest    # or: pnpm add / npm i
rm -rf /workspaces/stash/perf-host/speedscope/*
cp -r node_modules/speedscope/dist/release/. /workspaces/stash/perf-host/speedscope/
```

Schema is stable since 0.6.0.

## Grafana

Default login `admin` / `admin` — change on first login or leave it,
Tailscale-only. Datasource and the k6 Prometheus dashboard are
auto-provisioned.

## Tests

Schema + script generation are unit-tested. From the host:

```sh
cd /workspaces/stash/perf-host
uv sync
uv run pytest tests/
```

22 tests run in <1s. No container or running services required.

## Next steps

- Replace `/run` stub with the real k6 spawn (build script from
  `perf-rig.toml`, set `K6_PROMETHEUS_RW_EXTRA_LABELS`, enforce timeouts).
- Add `/profile` endpoint that curls `?profile=1` and writes
  `data/profiles/<project>/<sha>/<route>.speedscope.json`.
- Wire Bencher as the commit-aware regression store (see decision note).
- Project-side: scaffold `perf-rig.toml` + `just perf` from `jolo create`.
