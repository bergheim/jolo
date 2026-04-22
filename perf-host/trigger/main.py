import json
import os
import sqlite3
import subprocess
import threading
import tomllib
import uuid
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlencode

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from k6_script import generate as generate_k6
from ledger import Ledger
from schema import SCHEMA_VERSION, PerfRig, RunRequest

VM_URL = os.environ.get("VM_URL", "http://victoriametrics:8428")
PROFILE_DIR = Path(os.environ.get("PROFILE_DIR", "/srv/profiles"))
LEDGER_PATH = Path(os.environ.get("LEDGER_PATH", "/srv/profiles/ledger.sqlite"))
GRAFANA_BASE = os.environ.get("GRAFANA_BASE", "http://berghome.ts.glvortex.net:8888/grafana")
RIG_DIR = Path("/app/rigs")

app = FastAPI(title="perf-host trigger")
ledger = Ledger(LEDGER_PATH)

# Single-flight: only one k6 run at a time. Concurrent runs corrupt each
# other's numbers — proven empirically (3 parallel demos all dropped
# iterations from CPU contention). Codex flagged this in the design pass.
# Reject with 429 instead of queueing — clients can retry. Holding the lock
# is bounded by `timeout_s` in run() so a wedged run can't block forever.
_run_lock = threading.Lock()


def _k6_version() -> str:
    out = subprocess.run(["k6", "version"], capture_output=True, text=True, timeout=5)
    return out.stdout.strip().splitlines()[0] if out.returncode == 0 else "unknown"


def _grafana_url_for(run_id: str) -> str:
    # k6 dashboard 19665 filters by `testid` (k6's standard label).
    # We tag every k6 run with testid=<run_id>, so this links to that run.
    q = urlencode(
        {
            "var-testid": run_id,
            "from": "now-15m",
            "to": "now",
        }
    )
    return f"{GRAFANA_BASE}/d/k6-prom/k6-prometheus?{q}"


@app.get("/health")
def health():
    return {
        "ok": True,
        "k6": _k6_version(),
        "vm_url": VM_URL,
        "profile_dir": str(PROFILE_DIR),
        "profile_dir_exists": PROFILE_DIR.is_dir(),
        "ledger_path": str(LEDGER_PATH),
        "schema_version": SCHEMA_VERSION,
        "run_in_progress": _run_lock.locked(),
    }


@app.get("/schema")
def schema():
    return PerfRig.model_json_schema()


@app.post("/debug/render")
def debug_render(req: RunRequest):
    """Return the k6 script that WOULD be run, without running it."""
    rig_path = Path(req.rig_path)
    if not rig_path.is_file():
        raise HTTPException(status_code=400, detail=f"rig not found: {rig_path}")
    rig = PerfRig.model_validate(tomllib.loads(rig_path.read_text()))
    run_id = req.run_id or "DEBUG"
    run_tags = {
        "project": rig.project.name,
        "sha": req.sha,
        "branch": req.branch,
        "testbed": req.testbed,
        "run_id": run_id,
        "testid": run_id,  # k6/Grafana dashboard 19665 filters by `testid`.
    }
    return {
        "run_tags": run_tags,
        "k6_script": generate_k6(rig, run_tags=run_tags),
    }


@app.get("/runs")
def list_runs(limit: int = 50):
    return {"runs": ledger.recent(limit=limit)}


@app.get("/projects")
def list_projects():
    return {"projects": ledger.projects()}


@app.get("/runs/{run_id}")
def get_run(run_id: str):
    row = ledger.get(run_id)
    if not row:
        raise HTTPException(status_code=404, detail="run not found")
    return row


@app.post("/run")
def run(req: RunRequest):
    if not _run_lock.acquire(blocking=False):
        raise HTTPException(
            status_code=429,
            detail="another run is in progress; retry after it finishes",
        )
    try:
        return _run_locked(req)
    finally:
        _run_lock.release()


def _run_locked(req: RunRequest):
    rig_path = Path(req.rig_path)
    if not rig_path.is_file():
        raise HTTPException(status_code=400, detail=f"rig not found: {rig_path}")

    try:
        rig_data = tomllib.loads(rig_path.read_text())
        rig = PerfRig.model_validate(rig_data)
    except Exception as e:
        raise HTTPException(status_code=422, detail=f"invalid rig: {e}") from e

    if rig.target.mode != "external_url":
        raise HTTPException(
            status_code=501,
            detail="only target.mode=external_url is implemented in MVP",
        )

    run_id = req.run_id or uuid.uuid4().hex
    started_at = datetime.now(UTC).isoformat()
    grafana_url = _grafana_url_for(run_id)

    try:
        ledger.insert_started(
            {
                "run_id": run_id,
                "project": rig.project.name,
                "sha": req.sha,
                "branch": req.branch,
                "dirty": int(req.dirty),
                "testbed": req.testbed,
                "sut_mode": rig.target.mode,
                "sut_image_digest": None,
                "k6_version": _k6_version(),
                "rig_schema_version": rig.schema_version,
                "started_at": started_at,
                "ended_at": None,
                "validity_status": "running",
                "failure_reason": None,
                "grafana_url": grafana_url,
                "bencher_report_url": None,
                "profile_urls": None,
                "summary_json": None,
            }
        )
    except sqlite3.IntegrityError as e:
        raise HTTPException(status_code=409, detail=f"run_id already exists: {run_id}") from e

    run_tags = {
        "project": rig.project.name,
        "sha": req.sha,
        "branch": req.branch,
        "testbed": req.testbed,
        "run_id": run_id,
        "testid": run_id,  # k6/Grafana dashboard 19665 filters by `testid`.
    }

    script = generate_k6(rig, run_tags=run_tags)
    script_path = Path(f"/tmp/k6-{run_id}.js")
    summary_path = Path(f"/tmp/k6-summary-{run_id}.json")
    script_path.write_text(script)

    extra_labels = ",".join(f"{k}={v}" for k, v in run_tags.items())
    env = {
        **os.environ,
        "BASE_URL": rig.target.url,
        "K6_PROMETHEUS_RW_SERVER_URL": f"{VM_URL}/api/v1/write",
        "K6_PROMETHEUS_RW_TREND_STATS": "p(50),p(95),p(99),min,max,avg",
        "K6_PROMETHEUS_RW_PUSH_INTERVAL": "5s",
        "K6_PROMETHEUS_RW_EXTRA_LABELS": extra_labels,
    }

    tag_flags: list[str] = []
    for k, v in run_tags.items():
        tag_flags += ["--tag", f"{k}={v}"]

    # Persist the rendered script under /srv/profiles so we can curl-inspect it
    # via /profiles/<run_id>.k6.js when debugging label mismatches.
    inspect_path = PROFILE_DIR / f"{run_id}.k6.js"
    inspect_path.write_text(script)

    timeout_s = 600
    try:
        proc = subprocess.run(
            [
                "k6",
                "run",
                *tag_flags,
                "--out",
                "experimental-prometheus-rw",
                "--summary-export",
                str(summary_path),
                str(script_path),
            ],
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired as e:
        ledger.update_finished(
            run_id,
            ended_at=datetime.now(UTC).isoformat(),
            validity_status="fail",
            failure_reason=f"k6 timed out after {timeout_s}s",
        )
        raise HTTPException(status_code=504, detail="k6 timed out") from e

    ended_at = datetime.now(UTC).isoformat()
    validity, failure_reason, summary = _validate(proc, summary_path, rig)

    ledger.update_finished(
        run_id,
        ended_at=ended_at,
        validity_status=validity,
        failure_reason=failure_reason,
        summary_json=summary,
    )

    return {
        "run_id": run_id,
        "validity_status": validity,
        "failure_reason": failure_reason,
        "grafana_url": grafana_url,
        "ledger_url": f"/api/runs/{run_id}",
        "k6_exit": proc.returncode,
    }


def _validate(proc: subprocess.CompletedProcess, summary_path: Path, rig: PerfRig):
    """Decide validity from the parsed summary, not k6 exit code.

    k6 exit 99 means a *regression* threshold (p99 budget) was crossed —
    that's a regression result, not a validity failure. Validity is
    'did the rig itself produce trustworthy numbers' — dropped iterations,
    error rate, missing routes.
    """
    summary = {
        "k6_exit": proc.returncode,
        "stdout_tail": proc.stdout[-3000:],
        "stderr_tail": proc.stderr[-1000:],
    }
    if not summary_path.exists():
        return "fail", "k6 produced no summary export", summary
    try:
        s = json.loads(summary_path.read_text())
    except Exception as e:
        return "fail", f"summary parse error: {e}", summary

    metrics = s.get("metrics", {})
    summary["metrics_keys"] = sorted(metrics.keys())[:60]

    dropped = int(metrics.get("dropped_iterations", {}).get("count", 0) or 0)
    if dropped > rig.validity.max_dropped_iterations:
        return (
            "fail",
            f"dropped_iterations={dropped} exceeds max={rig.validity.max_dropped_iterations}",
            summary,
        )

    fail_rate = float(metrics.get("http_req_failed", {}).get("value", 0) or 0)
    if fail_rate > rig.validity.max_failure_rate:
        return (
            "fail",
            f"http_req_failed={fail_rate:.4f} exceeds max={rig.validity.max_failure_rate}",
            summary,
        )

    seen_scenarios = set()
    for k in metrics:
        # crude scan; per-scenario stats appear under sub-metrics in summary.
        if k.startswith("http_reqs"):
            seen_scenarios.add(k)
    summary["seen_metric_groups"] = sorted(seen_scenarios)[:30]

    return "pass", None, summary


@app.post("/run/demo")
def run_demo():
    """Convenience: fire the bundled demo rig with a fake SHA."""
    return run(
        RunRequest(
            rig_path=str(RIG_DIR / "demo.toml"),
            sha=uuid.uuid4().hex[:12],
            branch="demo",
            dirty=False,
            testbed="hub-bare",
        )
    )


@app.get("/", response_class=HTMLResponse)
def index():
    return (
        "<h1>perf-host trigger</h1>"
        "<ul>"
        "<li>POST /api/run &mdash; run a perf-rig.toml</li>"
        "<li>POST /api/run/demo &mdash; fire the bundled demo rig</li>"
        "<li>POST /api/debug/render &mdash; render a rig to k6 script without running</li>"
        "<li>GET /api/runs &mdash; recent ledger entries</li>"
        "<li>GET /api/runs/{run_id} &mdash; one ledger entry with summary</li>"
        "<li>GET /api/projects &mdash; one row per project with run counts</li>"
        "<li>GET /api/health &mdash; status (incl. run_in_progress)</li>"
        "<li>GET /api/schema &mdash; perf-rig.toml v1 JSON Schema</li>"
        "</ul>"
    )
