import os

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pyinstrument import Profiler

app = FastAPI()

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


def profiling_enabled() -> bool:
    return os.environ.get("APP_PROFILE", "1") != "0"


@app.middleware("http")
async def profile_request(request: Request, call_next):
    if (
        not profiling_enabled()
        or request.query_params.get("profile") not in {"1", "true", "yes"}
    ):
        return await call_next(request)

    profiler = Profiler(async_mode="enabled")
    profiler.start()
    try:
        await call_next(request)
    finally:
        profiler.stop()

    if request.query_params.get("format") == "json":
        return Response(
            profiler.output_json(),
            media_type="application/json",
        )
    return HTMLResponse(profiler.output_html())


@app.get("/", response_class=HTMLResponse)
async def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request, "home.html", {"message": "Hello, World!"}
    )
