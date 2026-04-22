"""Pydantic schema validation for perf-rig.toml v1."""

import pytest
from pydantic import ValidationError
from schema import SCHEMA_VERSION, PerfRig, RunRequest


def _minimal_rig(**over):
    base = {
        "schema_version": SCHEMA_VERSION,
        "project": {"name": "demo"},
        "target": {"mode": "external_url", "url": "http://demo:8080"},
        "routes": [
            {
                "route_id": "r1",
                "path": "/get",
                "rate_per_sec": 5,
                "duration": "5s",
                "preallocated_vus": 5,
                "max_vus": 10,
            }
        ],
    }
    base.update(over)
    return base


def test_minimal_rig_validates():
    rig = PerfRig.model_validate(_minimal_rig())
    assert rig.project.name == "demo"
    assert rig.target.mode == "external_url"
    assert len(rig.routes) == 1


def test_schema_version_must_match():
    with pytest.raises(Exception, match="unsupported schema_version=99"):
        PerfRig.model_validate(_minimal_rig(schema_version=99))


def test_project_name_must_be_slug():
    bad = _minimal_rig()
    bad["project"]["name"] = "BAD NAME"
    with pytest.raises(Exception, match="String should match pattern"):
        PerfRig.model_validate(bad)


def test_route_path_must_start_with_slash():
    bad = _minimal_rig()
    bad["routes"][0]["path"] = "no-leading-slash"
    with pytest.raises(Exception, match="String should match pattern"):
        PerfRig.model_validate(bad)


def test_duplicate_route_ids_rejected():
    bad = _minimal_rig()
    bad["routes"].append({**bad["routes"][0]})  # same route_id
    with pytest.raises(Exception, match="duplicate route_id"):
        PerfRig.model_validate(bad)


def test_unknown_target_mode_rejected():
    bad = _minimal_rig()
    bad["target"] = {"mode": "wormhole", "url": "ws://void"}
    with pytest.raises(ValidationError):
        PerfRig.model_validate(bad)


def test_ephemeral_target_shape_accepted():
    rig = PerfRig.model_validate(
        _minimal_rig(
            target={
                "mode": "ephemeral_container",
                "containerfile": "perf/Containerfile",
                "start_cmd": "uvicorn app:app --port $PORT",
                "ready_url": "/health",
            }
        )
    )
    assert rig.target.mode == "ephemeral_container"


def test_regression_threshold_lookup_defaults():
    rig = PerfRig.model_validate(_minimal_rig())
    rt = rig.regression_for("r1")
    assert rt.p99_ms is None  # no threshold set, defaults None


def test_regression_threshold_lookup_explicit():
    rig = PerfRig.model_validate(_minimal_rig(regression={"r1": {"p99_ms": 200, "p95_ms": 150}}))
    rt = rig.regression_for("r1")
    assert rt.p99_ms == 200
    assert rt.p95_ms == 150


def test_validity_defaults_present():
    rig = PerfRig.model_validate(_minimal_rig())
    assert rig.validity.max_dropped_iterations == 0
    assert rig.validity.max_failure_rate == 0.01


def test_run_request_run_id_optional():
    req = RunRequest(rig_path="/x.toml", sha="abcdef0")
    assert req.run_id is None
    assert req.testbed == "hub-bare"
    assert req.dirty is False


def test_run_request_short_sha_rejected():
    with pytest.raises(ValidationError):
        RunRequest(rig_path="/x.toml", sha="abc")  # < 7 chars
