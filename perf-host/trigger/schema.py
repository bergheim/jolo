"""Pydantic schema for perf-rig.toml v1.

Source of truth for the project<->hub contract. Generated JSON Schema
is published at /api/schema for editor completion.
"""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

SCHEMA_VERSION = 1


class Project(BaseModel):
    name: str = Field(min_length=1, max_length=64, pattern=r"^[a-z0-9][a-z0-9_-]*$")
    language: str | None = None  # for default profile capture mechanism


class TargetExternal(BaseModel):
    mode: Literal["external_url"]
    url: str  # base URL k6 hits; route paths are appended


class TargetEphemeral(BaseModel):
    mode: Literal["ephemeral_container"]
    containerfile: str
    start_cmd: str
    ready_url: str = "/"
    # NOTE: not implemented in MVP. Schema reserves the shape so
    # projects can opt in later without breaking.


Target = TargetExternal | TargetEphemeral


class Route(BaseModel):
    """One route = one k6 scenario. Multiplexing routes inside one
    scenario is forbidden (see gotcha 20260420T113000)."""

    route_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_]*$")
    path: str = Field(pattern=r"^/")
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"] = "GET"
    rate_per_sec: int = Field(gt=0, le=10_000)
    duration: str = Field(pattern=r"^\d+[smh]$")
    warmup: str = Field(default="3s", pattern=r"^\d+[smh]$")
    preallocated_vus: int = Field(default=10, gt=0, le=1000)
    max_vus: int = Field(default=50, gt=0, le=1000)


class ValidityThresholds(BaseModel):
    """Run-counts-or-it-doesn't gates. Enforced before regression
    detection sees the run."""

    max_dropped_iterations: int = 0
    max_failure_rate: float = Field(default=0.01, ge=0.0, le=1.0)


class RegressionThresholds(BaseModel):
    """Per-route latency budgets. Bencher will eventually own
    these, but k6 thresholds enforce them today as a hard fail."""

    p99_ms: int | None = None
    p95_ms: int | None = None


class PerfRig(BaseModel):
    schema_version: int = Field(default=SCHEMA_VERSION)
    project: Project
    target: Target = Field(discriminator="mode")
    routes: list[Route] = Field(min_length=1)
    validity: ValidityThresholds = ValidityThresholds()
    regression: dict[str, RegressionThresholds] = {}  # keyed by route_id

    @field_validator("schema_version")
    @classmethod
    def check_schema_version(cls, v: int) -> int:
        if v != SCHEMA_VERSION:
            raise ValueError(f"unsupported schema_version={v}; this hub speaks v{SCHEMA_VERSION}")
        return v

    @field_validator("routes")
    @classmethod
    def unique_route_ids(cls, v: list[Route]) -> list[Route]:
        ids = [r.route_id for r in v]
        if len(set(ids)) != len(ids):
            raise ValueError(f"duplicate route_id in routes: {ids}")
        return v

    def regression_for(self, route_id: str) -> RegressionThresholds:
        return self.regression.get(route_id, RegressionThresholds())


class RunRequest(BaseModel):
    """POST /api/run body."""

    rig_path: str  # absolute path inside the trigger container
    sha: str = Field(min_length=7, max_length=64)
    branch: str = "main"
    dirty: bool = False
    testbed: str = "hub-bare"
    run_id: str | None = None  # generated if absent
