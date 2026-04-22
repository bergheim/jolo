"""k6 script generation."""

import json
import re

from k6_script import generate
from schema import PerfRig


def _rig(routes=None, regression=None):
    return PerfRig.model_validate(
        {
            "schema_version": 1,
            "project": {"name": "demo"},
            "target": {"mode": "external_url", "url": "http://demo:8080"},
            "routes": routes
            or [
                {
                    "route_id": "get_root",
                    "path": "/get",
                    "rate_per_sec": 10,
                    "duration": "5s",
                    "preallocated_vus": 5,
                    "max_vus": 10,
                },
                {
                    "route_id": "delay",
                    "path": "/delay/0.1",
                    "rate_per_sec": 5,
                    "duration": "5s",
                    "preallocated_vus": 3,
                    "max_vus": 6,
                },
            ],
            "regression": regression or {},
        }
    )


def _options(script: str) -> dict:
    """Extract the options object from `export const options = {...};`."""
    m = re.search(r"export const options = (\{.*?\});", script, re.DOTALL)
    assert m, "options block not found"
    return json.loads(m.group(1))


def test_one_scenario_per_route():
    script = generate(_rig())
    opt = _options(script)
    assert set(opt["scenarios"].keys()) == {"get_root", "delay"}


def test_scenario_uses_constant_arrival_rate():
    opt = _options(generate(_rig()))
    for sc in opt["scenarios"].values():
        assert sc["executor"] == "constant-arrival-rate"
        assert sc["timeUnit"] == "1s"


def test_run_tags_merged_into_every_scenario():
    """The fix that mattered: run-level tags must be in scenario tags
    because options.tags / --tag / EXTRA_LABELS don't propagate via
    experimental-prometheus-rw on k6 0.55."""
    run_tags = {"project": "demo", "sha": "abc1234", "testid": "t1"}
    opt = _options(generate(_rig(), run_tags=run_tags))
    for route_id, sc in opt["scenarios"].items():
        assert sc["tags"]["route_id"] == route_id
        for k, v in run_tags.items():
            assert sc["tags"][k] == v, f"missing {k}={v} on scenario {route_id}"


def test_options_tags_also_set():
    """Belt-and-suspenders: options.tags is set even though it doesn't
    propagate to all metrics — for non-http metrics it does."""
    run_tags = {"project": "demo", "sha": "abc1234"}
    opt = _options(generate(_rig(), run_tags=run_tags))
    assert opt["tags"]["project"] == "demo"


def test_no_validity_thresholds_in_k6():
    """Validity gates (dropped_iterations, failure rate) are enforced by
    the trigger from --summary-export, NOT k6 thresholds. Adding them as
    k6 thresholds caused false fails on metrics that aren't always
    emitted."""
    script = generate(_rig())
    assert "dropped_iterations" not in script
    # No http_req_failed thresholds either:
    assert "http_req_failed" not in script


def test_regression_thresholds_appear_in_k6():
    rig = _rig(regression={"get_root": {"p99_ms": 200}})
    opt = _options(generate(rig))
    sel = "http_req_duration{scenario:get_root}"
    assert sel in opt["thresholds"]
    assert opt["thresholds"][sel] == ["p(99)<200"]


def test_p95_and_p99_threshold_combine():
    rig = _rig(regression={"get_root": {"p99_ms": 200, "p95_ms": 150}})
    opt = _options(generate(rig))
    sel = "http_req_duration{scenario:get_root}"
    assert "p(99)<200" in opt["thresholds"][sel]
    assert "p(95)<150" in opt["thresholds"][sel]


def test_route_id_on_per_request_tags():
    """Per-request tags carry route_id even on non-scenario metrics
    (defensive — the http.get() tag is a redundant carrier)."""
    script = generate(_rig())
    assert "tags: { route_id: 'get_root' }" in script
    assert "tags: { route_id: 'delay' }" in script


def test_method_default_get():
    script = generate(_rig())
    assert "http.get(`${__ENV.BASE_URL}/get`" in script


def test_explicit_post_method():
    rig = _rig(
        routes=[
            {
                "route_id": "post_x",
                "path": "/post",
                "method": "POST",
                "rate_per_sec": 5,
                "duration": "5s",
                "preallocated_vus": 5,
                "max_vus": 10,
            }
        ]
    )
    script = generate(rig)
    assert "http.post(`${__ENV.BASE_URL}/post`" in script
