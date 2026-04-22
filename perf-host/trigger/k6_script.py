"""Generate a k6 script from a PerfRig.

Trust boundary: the rig is declarative TOML; the script we emit is
trusted because *we* write it. Projects never inject k6 JS directly.
"""

import json

from schema import PerfRig

SCRIPT_TEMPLATE = """\
import http from 'k6/http';

export const options = {options};

{exec_funcs}
"""


def _scenario(
    route_id: str,
    rate: int,
    duration: str,
    pre: int,
    mx: int,
    extra_tags: dict[str, str],
) -> dict:
    return {
        "executor": "constant-arrival-rate",
        "rate": rate,
        "timeUnit": "1s",
        "duration": duration,
        "preAllocatedVUs": pre,
        "maxVUs": mx,
        "exec": route_id,
        "tags": {"route_id": route_id, **extra_tags},
    }


def _exec_func(route_id: str, method: str, path: str) -> str:
    method_call = method.lower()
    args = (
        f"`${{__ENV.BASE_URL}}{path}`, null, "
        if method != "GET"
        else f"`${{__ENV.BASE_URL}}{path}`, "
    )
    return (
        f"export function {route_id}() {{\n"
        f"  http.{method_call}({args}{{ tags: {{ route_id: '{route_id}' }} }});\n"
        f"}}\n"
    )


def generate(rig: PerfRig, run_tags: dict[str, str] | None = None) -> str:
    extra_tags = run_tags or {}
    scenarios = {
        r.route_id: _scenario(
            r.route_id,
            r.rate_per_sec,
            r.duration,
            r.preallocated_vus,
            r.max_vus,
            extra_tags,
        )
        for r in rig.routes
    }

    # NOTE: validity (dropped_iterations, failure rate) is enforced by the
    # trigger from the parsed --summary-export JSON, not by k6 thresholds.
    # k6 fails thresholds against not-yet-emitted metrics, which we hit on
    # the dropped_iterations counter. Regression budgets stay as k6
    # thresholds because they're per-route p99/p95 latencies.
    thresholds: dict[str, list[str]] = {}
    for r in rig.routes:
        sel = f"{{scenario:{r.route_id}}}"
        rt = rig.regression_for(r.route_id)
        if rt.p99_ms is not None:
            thresholds[f"http_req_duration{sel}"] = [f"p(99)<{rt.p99_ms}"]
        if rt.p95_ms is not None:
            thresholds.setdefault(f"http_req_duration{sel}", []).append(f"p(95)<{rt.p95_ms}")

    options = {
        "scenarios": scenarios,
        "thresholds": thresholds,
        "tags": run_tags or {},
        "summaryTrendStats": ["avg", "min", "med", "max", "p(95)", "p(99)"],
    }

    exec_funcs = "\n".join(_exec_func(r.route_id, r.method, r.path) for r in rig.routes)

    return SCRIPT_TEMPLATE.format(options=json.dumps(options, indent=2), exec_funcs=exec_funcs)
