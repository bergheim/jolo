import ipaddress
import os

import pyroscope
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pyinstrument import Profiler
from pyinstrument.renderers.speedscope import SpeedscopeRenderer

# Continuous profiling. PROJECT and PYROSCOPE_HOST are set globally in
# the dev environment (host .zshrc → bind-mounted into every container)
# so we don't gate on env presence — missing means misconfigured devhost
# and we want startup to fail loudly.
pyroscope.configure(
    application_name=os.environ["PROJECT"],
    server_address=os.environ["PYROSCOPE_HOST"],
    oncpu=False,
    tags={"env": "dev"},
)

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


# Reject if any of these are set — request.client.host would reflect the
# proxy's loopback, not the real caller.
_PROXY_HEADERS = ("x-forwarded-for", "x-real-ip", "forwarded")


def profiling_enabled() -> bool:
    return os.environ.get("APP_PROFILE", "1") != "0"


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
        or request.query_params.get("profile") not in {"1", "true", "yes"}
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
            async for _chunk in iterator:
                pass
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
