import ipaddress
import os
import subprocess
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pyroscope
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pyinstrument import Profiler
from pyinstrument.renderers.speedscope import SpeedscopeRenderer
from starlette.routing import Match


# Reject if any of these are set — request.client.host would reflect the
# proxy's loopback, not the real caller.
_PROXY_HEADERS = ("x-forwarded-for", "x-real-ip", "forwarded")
# Cap drain so a `?profile=1` on a giant streaming download can't blow
# memory. We lose profile coverage past this point on huge responses,
# which is the right trade for an opt-in dev tool.
_DRAIN_BYTE_CAP = 50 * 1024 * 1024


def profiling_enabled() -> bool:
    return os.environ.get("APP_PROFILE", "1") != "0"


# Tag samples with the commit currently checked out, refreshed cheaply.
# Lifespan-time read would freeze on the SHA at startup — uvicorn --reload
# only fires on file changes, not git commits, so any commit you make
# during a session would leave the tag stale and break trigger's
# pyroscope_url which filters by sha.
_sha_cache: tuple[str, float] = ("unknown", 0.0)


def _git_sha_cached() -> str:
    global _sha_cache
    sha, last = _sha_cache
    if time.monotonic() - last < 30:
        return sha
    try:
        out = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, timeout=2,
        )
        sha = out.stdout.strip()[:12] if out.returncode == 0 else "unknown"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        sha = "unknown"
    _sha_cache = (sha, time.monotonic())
    return sha


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    # PROJECT/PYROSCOPE_HOST come from the host .zshrc bind-mount. In
    # lifespan (not at import) so tests/scripts can `from app import app`
    # without pyroscope being reachable.
    if profiling_enabled():
        pyroscope.configure(
            application_name=os.environ["PROJECT"],
            server_address=os.environ["PYROSCOPE_HOST"],
            oncpu=False,
            tags={"env": "dev"},
        )
    yield
    if profiling_enabled():
        pyroscope.shutdown()


app = FastAPI(lifespan=lifespan)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


@app.middleware("http")
async def pyroscope_route_tag(request: Request, call_next):
    if not profiling_enabled():
        return await call_next(request)
    # Match the route pattern (e.g. /items/{id}) instead of the raw URL
    # so cardinality stays bounded — one tag value per route, not per id.
    pattern: str | None = None
    for route in request.app.routes:
        match, _ = route.matches(request.scope)
        if match == Match.FULL:
            pattern = getattr(route, "path", None) or getattr(route, "path_format", None)
            break
    tags: dict[str, str] = {"sha": _git_sha_cached()}
    if pattern:
        tags["route"] = pattern
    with pyroscope.tag_wrapper(tags):
        return await call_next(request)


def _is_loopback(request: Request) -> bool:
    if any(h in request.headers for h in _PROXY_HEADERS):
        return False
    host = request.client.host if request.client else None
    if not host:
        return False
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


@app.middleware("http")
async def profile_request(request: Request, call_next):
    if (
        not profiling_enabled()
        or request.query_params.get("profile") != "1"
        or not _is_loopback(request)
    ):
        return await call_next(request)

    profiler = Profiler(async_mode="enabled")
    profiler.start()
    try:
        upstream = await call_next(request)
        # Drain inside the profiler window so streaming routes (where the
        # actual work happens during iteration) are captured. Also runs
        # BackgroundTasks so cleanup the route attached actually fires.
        iterator = getattr(upstream, "body_iterator", None)
        if iterator is not None:
            drained = 0
            async for chunk in iterator:
                drained += len(chunk) if isinstance(chunk, (bytes, bytearray)) else 0
                if drained > _DRAIN_BYTE_CAP:
                    break
        background = getattr(upstream, "background", None)
        if background is not None:
            await background()
    finally:
        profiler.stop()

    if request.query_params.get("format") == "json":
        # SpeedscopeRenderer returns already-encoded JSON; hand it through
        # Response so JSONResponse doesn't double-encode it.
        return Response(
            profiler.output(renderer=SpeedscopeRenderer()),
            media_type="application/json",
        )
    return HTMLResponse(profiler.output_html())


@app.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "home.html", {"message": "Hello, World!"}
    )
