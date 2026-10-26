"""Public OpenAI-compatible API (spec 6.1)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ...db.models import ModelRoute
from ...db.session import db_session
from ...schemas.chat import ChatCompletionRequest
from ...services.auth_service import authenticate_api_key
from ...services.gateway_service import execute_chat, stream_chat

router = APIRouter()


def _extract_key(request: Request) -> str | None:
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.headers.get("x-api-key")


@router.get("/health/live")
def health_live():
    return {"status": "live"}


@router.get("/health/ready")
def health_ready(db: Session = Depends(db_session)):
    from sqlalchemy import text

    try:
        db.execute(text("SELECT 1"))
        db_ok = True
    except Exception:
        db_ok = False
    # Optional providers (Ollama/remote) never fail readiness unless configured
    # as required — see docs/operations.md.
    return JSONResponse(
        status_code=200 if db_ok else 503,
        content={"status": "ready" if db_ok else "not_ready", "database": db_ok},
    )


@router.get("/v1/models")
def list_models(request: Request, db: Session = Depends(db_session)):
    _, _, policy = authenticate_api_key(db, _extract_key(request))
    aliases = (
        db.execute(select(ModelRoute.alias).where(ModelRoute.enabled.is_(True)).distinct()).scalars().all()
    )
    allowed = list(policy.allowed_models or ["*"])
    data = [
        {"id": a, "object": "model", "owned_by": "modelrail"}
        for a in sorted(aliases)
        if "*" in allowed or a in allowed
    ]
    return {"object": "list", "data": data}


@router.post("/v1/chat/completions")
async def chat_completions(
    payload: ChatCompletionRequest,
    request: Request,
    db: Session = Depends(db_session),
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    _, project, policy = authenticate_api_key(db, _extract_key(request))
    if payload.stream:
        generator = stream_chat(db, project, policy, payload)
        return StreamingResponse(generator, media_type="text/event-stream", headers={"x-request-id": ""})
    result = await execute_chat(db, project, policy, payload, idempotency_key=idempotency_key)
    return JSONResponse(content=result, headers={"x-request-id": result["modelrail"]["request_id"]})
