"""ModelRail gateway application entrypoint."""

from __future__ import annotations

import time
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from .api.admin.routes import router as admin_router
from .api.public.routes import router as public_router
from .config import get_settings
from .core.errors import GatewayError
from .core.logging_config import get_logger, request_id_var, setup_logging
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


@app.exception_handler(GatewayError)
async def gateway_error_handler(request: Request, exc: GatewayError):
    return JSONResponse(status_code=exc.status_code, content=exc.envelope())


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception):
    log.error("unhandled error", exc_info=exc)
    return JSONResponse(
        status_code=500,
        content={
            "error": {"message": "internal server error", "type": "server_error", "code": "internal_error"}
        },
    )


@app.get("/metrics")
def metrics_endpoint():
    return PlainTextResponse(generate_latest().decode(), media_type=CONTENT_TYPE_LATEST)


app.include_router(public_router)
app.include_router(admin_router)


@app.on_event("startup")
def _startup():
    init_db()
    setup_tracing(app)
    log.info("modelrail gateway started")
