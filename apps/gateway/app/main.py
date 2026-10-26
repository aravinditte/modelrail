"""ModelRail gateway application entrypoint."""

from __future__ import annotations

import os
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from .api.admin.routes import router as admin_router
from .api.public.routes import router as public_router
from .config import get_settings
from .core.errors import GatewayError
from .core.logging_config import get_logger, request_id_var, setup_logging, trace_id_var
from .db.session import init_db
from .telemetry.tracing import setup_tracing

setup_logging()
log = get_logger("modelrail.gateway")

app = FastAPI(
    title="ModelRail Gateway",
    version="1.0.0",
    description="Local-first, OpenAI-compatible LLM gateway and AI reliability platform.",
)


@app.middleware("http")
async def request_context_and_limits(request: Request, call_next):
    settings = get_settings()
    request_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    token = request_id_var.set(request_id)
    # Populate the log trace_id from the active OTEL span when tracing is
    # enabled; without a span it stays empty rather than being fabricated.
    trace_token = None
    try:
        from opentelemetry import trace as _otel_trace

        _ctx = _otel_trace.get_current_span().get_span_context()
        if _ctx and _ctx.is_valid:
            trace_token = trace_id_var.set(format(_ctx.trace_id, "032x"))
    except Exception:
        trace_token = None
    started = time.monotonic()
    try:
        content_length = request.headers.get("content-length")
        if content_length is not None and int(content_length) > settings.max_request_bytes:
            return JSONResponse(
                status_code=413,
                content={
                    "error": {
                        "message": "request body exceeds the maximum allowed size",
                        "type": "invalid_request_error",
                        "code": "payload_too_large",
                    }
                },
            )
        response = await call_next(request)
        # Handlers may set their own correlation ID (the logical request ID
        # for chat completions) — never overwrite it.
        if "x-request-id" not in response.headers:
            response.headers["x-request-id"] = request_id
        response.headers["x-modelrail-duration-ms"] = str(int((time.monotonic() - started) * 1000))
        return response
    finally:
        request_id_var.reset(token)
        if trace_token is not None:
            trace_id_var.reset(trace_token)


@app.exception_handler(GatewayError)
async def gateway_error_handler(request: Request, exc: GatewayError):
    return JSONResponse(status_code=exc.status_code, content=exc.envelope())


@app.exception_handler(RequestValidationError)
async def validation_error_handler(request: Request, exc: RequestValidationError):
    """All validation failures use the standard error envelope (spec 6.1).
    Unknown/unsupported fields get their own stable code so clients can
    distinguish them from malformed values."""
    errors = exc.errors()
    unsupported = [e for e in errors if e.get("type") == "extra_forbidden"]
    if unsupported:
        fields = ", ".join(str(e.get("loc", ["?"])[-1]) for e in unsupported)
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "message": f"unsupported field(s): {fields}",
                    "type": "invalid_request_error",
                    "code": "unsupported_field",
                }
            },
        )
    first = errors[0] if errors else {}
    loc = ".".join(str(p) for p in first.get("loc", []))
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "message": f"request validation failed at {loc}: {first.get('msg', 'invalid')}",
                "type": "invalid_request_error",
                "code": "validation_error",
            }
        },
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    log.error("unhandled error", exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={
            "error": {"message": "internal server error", "type": "server_error", "code": "internal_error"}
        },
    )


def _find_landing_page_dir() -> Path | None:
    env_dir = os.environ.get("LANDING_PAGE_DIR")
    if env_dir:
        p = Path(env_dir)
        if p.is_dir():
            return p
    candidates = [
        Path(__file__).resolve().parent.parent.parent / "landing page",
        Path.cwd() / "landing page",
        Path("/repo/landing page"),
    ]
    for c in candidates:
        if c.is_dir() and (c / "index.html").is_file():
            return c
    return None


_landing_dir = _find_landing_page_dir()


@app.get("/", include_in_schema=False)
def root(request: Request):
    accept = request.headers.get("accept", "")
    if "application/json" in accept and "text/html" not in accept:
        return {
            "service": "modelrail-gateway",
            "version": "1.0.0",
            "status": "running",
            "docs_url": "/docs",
            "openapi_url": "/openapi.json",
            "health_url": "/health/ready",
            "models_url": "/v1/models",
        }
    if _landing_dir is not None and (_landing_dir / "index.html").is_file():
        return FileResponse(_landing_dir / "index.html")
    return {
        "service": "modelrail-gateway",
        "version": "1.0.0",
        "status": "running",
        "docs_url": "/docs",
        "openapi_url": "/openapi.json",
        "health_url": "/health/ready",
        "models_url": "/v1/models",
    }


@app.get("/api", tags=["system"])
def api_discovery():
    return {
        "service": "modelrail-gateway",
        "version": "1.0.0",
        "status": "running",
        "docs_url": "/docs",
        "openapi_url": "/openapi.json",
        "health_url": "/health/ready",
        "models_url": "/v1/models",
    }


@app.get("/ja", include_in_schema=False)
def japanese_landing():
    if _landing_dir is not None and (_landing_dir / "index-ja.html").is_file():
        return FileResponse(_landing_dir / "index-ja.html")
    if _landing_dir is not None and (_landing_dir / "index.html").is_file():
        return FileResponse(_landing_dir / "index.html")
    return {
        "service": "modelrail-gateway",
        "version": "1.0.0",
        "status": "running",
    }


@app.get("/favicon.ico", include_in_schema=False)
def favicon_endpoint():
    if _landing_dir is not None:
        ico = _landing_dir / "favicon.ico"
        if ico.is_file():
            return FileResponse(ico, media_type="image/x-icon")
        svg = _landing_dir / "favicon.svg"
        if svg.is_file():
            return FileResponse(svg, media_type="image/svg+xml")
    return JSONResponse(status_code=404, content={"detail": "favicon not found"})


@app.get("/metrics")
def metrics_endpoint():
    return PlainTextResponse(generate_latest().decode(), media_type=CONTENT_TYPE_LATEST)


app.include_router(public_router)
app.include_router(admin_router)

if _landing_dir is not None and _landing_dir.is_dir():
    app.mount("/", StaticFiles(directory=str(_landing_dir), html=True), name="site")


@app.on_event("startup")
def _startup():
    init_db()
    setup_tracing(app)
    settings = get_settings()
    if (
        settings.admin_token == "dev-admin-token-change-me"
        or settings.api_key_pepper == "dev-pepper-change-me"
    ):
        log.warning(
            "SECURITY: built-in default admin token and/or API-key pepper are in use. "
            "Set ADMIN_TOKEN and MODELRAIL_API_KEY_PEPPER to unique random values "
            "before exposing this gateway beyond a local demo."
        )
    log.info("modelrail gateway started")
