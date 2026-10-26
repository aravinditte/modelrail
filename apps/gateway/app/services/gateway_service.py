"""Logical-request execution (spec 3.3 request lifecycle).

One logical request -> one LogicalRequest row, one budget reservation, and
one ProviderAttempt row PER provider attempt. The request ID never changes
across retries/fallbacks. Fallback is allowed only before any streaming
content has been emitted; afterwards a stream error terminates the response.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..core import metrics
from ..core.errors import ErrorClass, GatewayError, ProviderError, err
from ..core.logging_config import get_logger
from ..db.models import LogicalRequest, ModelRoute, Policy, Project, ProviderAttempt
from ..domain.pricing import calculate_cost, estimate_messages_tokens, reserve_estimate
from ..providers import CompletionRequest, create_provider
from ..schemas.chat import ChatCompletionRequest
from ..telemetry.tracing import span
from . import budget as budget_service
from .ratelimit import LIMITER
from .reliability import BREAKERS, backoff_delay
from .routing import eligible_routes, order_routes
from .usage import record_usage_event

log = get_logger("modelrail.gateway")


def _cost_basis(provider_name: str, usage_source: str) -> str:
    if provider_name.startswith("mock"):
        return "simulated"
    if usage_source == "provider_reported":
        return "provider_reported"
    if usage_source == "unknown":
        return "unknown"
    return "estimated"


class _Execution:
    """Shared per-request state for the streaming and non-streaming paths."""

    def __init__(self, db: Session, project: Project, policy: Policy, payload: ChatCompletionRequest):
        self.db = db
        self.project = project
        self.policy = policy
        self.payload = payload
        self.settings = get_settings()
        self.started = time.monotonic()
        self.deadline = self.started + self.settings.request_deadline_s
        self.attempt_no = 0
        self.last_error: ProviderError | None = None
        self.fallback_reason: str | None = None

        messages = payload.messages_as_dicts()
        self.messages = messages
        self.est_input_tokens = estimate_messages_tokens(messages)
        requested_output = payload.max_tokens or self.settings.default_max_output_tokens
        if requested_output > policy.max_output_tokens:
            raise err(
                400,
                "max_tokens_exceeds_policy",
                f"max_tokens {requested_output} exceeds the project policy limit "
                f"{policy.max_output_tokens}",
            )
        self.est_output_tokens = requested_output

        routes = eligible_routes(
            db, payload.model, list(policy.allowed_models or ["*"]), streaming=payload.stream
        )
        if not routes:
            if "*" not in (policy.allowed_models or []) and payload.model not in (
                policy.allowed_models or []
            ):
                raise err(
                    403,
                    "model_not_allowed",
                    f"model alias '{payload.model}' is not in this project's allowlist",
                    "authentication_error",
                )
            raise err(
                404,
                "model_not_found",
                f"no enabled route for model alias '{payload.model}'",
                "invalid_request_error",
            )
        self.ordered_routes, self.candidates_meta = order_routes(
            db, routes, policy.routing_policy, self.est_input_tokens, self.est_output_tokens
        )

        self.request_row = LogicalRequest(
            project_id=project.id,
            model_alias=payload.model,
            status="running",
            request_deadline=datetime.now(timezone.utc) + timedelta(seconds=self.settings.request_deadline_s),
            routing_policy=policy.routing_policy,
            route_decision={"policy": policy.routing_policy, "candidates": self.candidates_meta},
        )
        db.add(self.request_row)
        db.commit()
        db.refresh(self.request_row)

        reserve_amount = max(
            reserve_estimate(
                self.est_input_tokens,
                self.est_output_tokens,
                r.input_price_per_token,
                r.output_price_per_token,
            )
            for r in self.ordered_routes
        )
        self.reserve_amount = reserve_amount
        budget_limit = Decimal(str(policy.budget_limit)) if policy.budget_limit is not None else None
        try:
            self.reservation = budget_service.reserve(
                db, project.id, self.request_row.id, reserve_amount, budget_limit
            )
        except GatewayError:
            metrics.BUDGET_REJECTIONS.inc()
            self.request_row.status = "failed"
            self.request_row.error_code = "budget_exceeded"
            self.request_row.completed_at = datetime.now(timezone.utc)
            db.commit()
            raise

    # -- attempt bookkeeping --------------------------------------------
    def record_attempt(
        self,
        route: ModelRoute,
        status: str,
        started: float,
        usage=None,
        cost: Decimal | None = None,
        error_code: str | None = None,
    ) -> ProviderAttempt:
        latency_ms = int((time.monotonic() - started) * 1000)
        attempt = ProviderAttempt(
            request_id=self.request_row.id,
            provider=route.provider,
            upstream_model=route.upstream_model,
            attempt_number=self.attempt_no,
            status=status,
            latency_ms=latency_ms,
            input_tokens=(usage.input_tokens if usage else None),
            output_tokens=(usage.output_tokens if usage else None),
            cost=cost,
            cost_basis=(_cost_basis(route.provider, usage.source) if usage else None),
            error_code=error_code,
            fallback_reason=self.fallback_reason,
        )
        self.db.add(attempt)
        self.db.commit()
        self.db.refresh(attempt)
        metrics.ATTEMPTS.labels(provider=route.provider, status=status).inc()
        metrics.PROVIDER_LATENCY.labels(provider=route.provider).observe(latency_ms / 1000.0)
        return attempt

    def finalise_success(self, route: ModelRoute, usage, attempt: ProviderAttempt) -> Decimal:
        cost = calculate_cost(
            usage.input_tokens, usage.output_tokens, route.input_price_per_token, route.output_price_per_token
        )
        attempt.cost = cost
        attempt.cost_basis = _cost_basis(route.provider, usage.source)
        self.db.commit()
        record_usage_event(
            self.db,
            event_key=f"{self.request_row.id}:{attempt.id}",
            request_id=self.request_row.id,
            attempt_id=attempt.id,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cost=cost,
            usage_source=usage.source,
            pricing_version=str(route.pricing_version),
        )
        budget_service.settle(self.db, self.reservation.id, cost)
        total_ms = int((time.monotonic() - self.started) * 1000)
        row = self.request_row
        row.status = "succeeded"
        row.completed_at = datetime.now(timezone.utc)
        row.total_latency_ms = total_ms
        row.total_attempts = self.attempt_no
        row.input_tokens = usage.input_tokens
        row.output_tokens = usage.output_tokens
        row.final_cost = cost
        row.cost_basis = _cost_basis(route.provider, usage.source)
        row.selected_provider = route.provider
        row.selected_upstream_model = route.upstream_model
        row.fallback_reason = self.fallback_reason
        self.db.commit()
        metrics.REQUESTS.labels(status="succeeded", model_alias=row.model_alias).inc()
        metrics.REQUEST_LATENCY.labels(model_alias=row.model_alias).observe(total_ms / 1000.0)
        metrics.TOKENS.labels(direction="input", model_alias=row.model_alias).inc(usage.input_tokens)
        metrics.TOKENS.labels(direction="output", model_alias=row.model_alias).inc(usage.output_tokens)
        metrics.COST.labels(model_alias=row.model_alias).inc(float(cost))
        log.info(
            "request succeeded",
            extra={
                "request_id": row.id,
                "provider": route.provider,
                "duration_ms": total_ms,
                "outcome": "succeeded",
            },
        )
        return cost

    def finalise_failure(self, error_code: str) -> None:
        row = self.request_row
        row.status = "failed"
        row.completed_at = datetime.now(timezone.utc)
        row.total_latency_ms = int((time.monotonic() - self.started) * 1000)
        row.total_attempts = self.attempt_no
        row.error_code = error_code
        row.fallback_reason = self.fallback_reason
        row.cost_basis = "unknown" if self.attempt_no > 0 else row.cost_basis
        self.db.commit()
        if self.attempt_no > 0:
            # An attempt may have incurred provider usage we cannot see:
            # never invent it — park the reservation for reconciliation.
            budget_service.mark_reconciliation_needed(self.db, self.reservation.id)
        else:
            budget_service.release(self.db, self.reservation.id)
        metrics.REQUESTS.labels(status="failed", model_alias=row.model_alias).inc()
        log.info(
            "request failed", extra={"request_id": row.id, "error_code": error_code, "outcome": "failed"}
        )

    def provider_request(self, route: ModelRoute) -> CompletionRequest:
        remaining = max(0.1, self.deadline - time.monotonic())
        timeout = min(self.settings.provider_request_timeout_s, remaining)
        p = self.payload
        return CompletionRequest(
            upstream_model=route.upstream_model,
            messages=self.messages,
            temperature=p.temperature,
            top_p=p.top_p,
            max_tokens=self.est_output_tokens,
            stop=(p.stop if isinstance(p.stop, list) else ([p.stop] if p.stop else None)),
            seed=p.seed,
            request_id=self.request_row.id,
            timeout_s=timeout,
        )

    def response_body(
        self, route: ModelRoute, content: str, finish_reason: str, usage, cost: Decimal
    ) -> dict:
        body = {
            "id": f"chatcmpl-{self.request_row.id}",
            "object": "chat.completion",
            "created": int(datetime.now(timezone.utc).timestamp()),
            "model": self.payload.model,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": content},
                    "finish_reason": finish_reason,
                }
            ],
            "usage": {
                "prompt_tokens": usage.input_tokens,
                "completion_tokens": usage.output_tokens,
                "total_tokens": usage.input_tokens + usage.output_tokens,
            },
            "modelrail": {
                "request_id": self.request_row.id,
                "provider": route.provider,
                "upstream_model": route.upstream_model,
                "attempts": self.attempt_no,
                "cost": str(cost),
                "cost_basis": _cost_basis(route.provider, usage.source),
                "pricing_version": str(route.pricing_version),
                "fallback_reason": self.fallback_reason,
            },
        }
        self.request_row.response_json = body
        self.db.commit()
        return body


async def execute_chat(
    db: Session,
    project: Project,
    policy: Policy,
    payload: ChatCompletionRequest,
    idempotency_key: str | None = None,
) -> dict:
    if idempotency_key:
        existing = db.execute(
            select(LogicalRequest).where(
                LogicalRequest.project_id == project.id, LogicalRequest.idempotency_key == idempotency_key
            )
        ).scalar_one_or_none()
        if existing is not None and existing.status == "succeeded" and existing.response_json:
            return existing.response_json

    limited = LIMITER.check_and_record(
        project.id,
        policy.requests_per_minute,
        policy.tokens_per_minute,
        estimate_messages_tokens(payload.messages_as_dicts()),
    )
    if limited:
        metrics.RATE_LIMIT_REJECTIONS.labels(kind=limited).inc()
        raise err(429, limited, "rate limit exceeded for this project", "rate_limit_error")
    if not LIMITER.acquire_concurrency(project.id, policy.max_concurrency):
        metrics.RATE_LIMIT_REJECTIONS.labels(kind="concurrency").inc()
        raise err(
            429, "concurrency_limit", "too many concurrent requests for this project", "rate_limit_error"
        )
    metrics.IN_PROGRESS.inc()
    try:
        with span("modelrail.request", **{"modelrail.model_alias": payload.model}):
            ex = _Execution(db, project, policy, payload)
            if idempotency_key:
                ex.request_row.idempotency_key = idempotency_key
                db.commit()
            return await _run_non_streaming(ex)
    finally:
        LIMITER.release_concurrency(project.id)
        metrics.IN_PROGRESS.dec()


async def _run_non_streaming(ex: _Execution) -> dict:
    settings = ex.settings
    for route_index, route in enumerate(ex.ordered_routes):
        breaker = BREAKERS.get(route.provider, route.upstream_model)
        if not breaker.allow():
            ex.fallback_reason = f"circuit_open:{route.provider}"
            metrics.CIRCUIT_TRANSITIONS.labels(provider=route.provider).inc()
            continue
        retries_here = 0
        while ex.attempt_no < settings.max_total_attempts and time.monotonic() < ex.deadline:
            ex.attempt_no += 1
            attempt_start = time.monotonic()
            provider = create_provider(route.provider, route.configuration or {})
            request = ex.provider_request(route)
            try:
                with span(
                    "modelrail.provider_attempt",
                    **{"modelrail.provider": route.provider, "modelrail.attempt": ex.attempt_no},
                ):
                    result = await asyncio.wait_for(provider.complete(request), timeout=request.timeout_s)
            except (ProviderError, asyncio.TimeoutError) as exc:
                provider_error = (
                    exc
                    if isinstance(exc, ProviderError)
                    else ProviderError("provider timed out", ErrorClass.TIMEOUT)
                )
                ex.last_error = provider_error
                attempt = ex.record_attempt(
                    route, "failed", attempt_start, error_code=provider_error.error_class.value
                )
                if provider_error.error_class != ErrorClass.BAD_REQUEST:
                    before = breaker.state
                    breaker.record_failure()
                    if breaker.state != before:
                        metrics.CIRCUIT_TRANSITIONS.labels(provider=route.provider).inc()
                metrics.PROVIDER_ERRORS.labels(
                    provider=route.provider, error_class=provider_error.error_class.value
                ).inc()
                if (
                    provider_error.retryable
                    and retries_here < 2
                    and ex.attempt_no < settings.max_total_attempts
                    and time.monotonic() < ex.deadline
                ):
                    retries_here += 1
                    metrics.RETRIES.labels(provider=route.provider).inc()
                    await asyncio.sleep(backoff_delay(ex.attempt_no, provider_error.retry_after_s))
                    continue
                if provider_error.fallbackable and route_index < len(ex.ordered_routes) - 1:
                    ex.fallback_reason = f"{provider_error.error_class.value}:{route.provider}"
                    nxt = ex.ordered_routes[route_index + 1]
                    metrics.FALLBACKS.labels(from_provider=route.provider, to_provider=nxt.provider).inc()
                    break  # next route
                code = (
                    "provider_bad_request"
                    if provider_error.error_class == ErrorClass.BAD_REQUEST
                    else f"provider_{provider_error.error_class.value}"
                )
                ex.finalise_failure(code)
                status = 400 if provider_error.error_class == ErrorClass.BAD_REQUEST else 502
                raise err(
                    status, code, f"provider request failed: {provider_error.message}", "provider_error"
                )
            # success
            attempt = ex.record_attempt(route, "succeeded", attempt_start, usage=result.usage)
            breaker.record_success()
            cost = ex.finalise_success(route, result.usage, attempt)
            return ex.response_body(route, result.content, result.finish_reason, result.usage, cost)
    code = f"provider_{ex.last_error.error_class.value}" if ex.last_error else "no_eligible_route"
    ex.finalise_failure(code if ex.attempt_no else "all_routes_unavailable")
    raise err(
        502, "all_routes_failed", "all eligible provider routes failed or were unavailable", "provider_error"
    )


async def stream_chat(db: Session, project: Project, policy: Policy, payload: ChatCompletionRequest):
    """Async generator yielding SSE strings. Fallback only before first chunk."""
    limited = LIMITER.check_and_record(
        project.id,
        policy.requests_per_minute,
        policy.tokens_per_minute,
        estimate_messages_tokens(payload.messages_as_dicts()),
    )
    if limited:
        raise err(429, limited, "rate limit exceeded for this project", "rate_limit_error")
    if not LIMITER.acquire_concurrency(project.id, policy.max_concurrency):
        raise err(
            429, "concurrency_limit", "too many concurrent requests for this project", "rate_limit_error"
        )
    metrics.IN_PROGRESS.inc()
    ex: _Execution | None = None
    try:
        ex = _Execution(db, project, policy, payload)
        emitted = False
        for route_index, route in enumerate(ex.ordered_routes):
            breaker = BREAKERS.get(route.provider, route.upstream_model)
            if not breaker.allow():
                ex.fallback_reason = f"circuit_open:{route.provider}"
                continue
            ex.attempt_no += 1
            attempt_start = time.monotonic()
            provider = create_provider(route.provider, route.configuration or {})
            request = ex.provider_request(route)
            content_parts: list[str] = []
            final_usage = None
            finish_reason = "stop"
            try:
                async for chunk in provider.stream(request):
                    if chunk.content:
                        emitted = True
                        content_parts.append(chunk.content)
                        yield _sse_chunk(ex, route, chunk.content, None)
                    if chunk.usage is not None:
                        final_usage = chunk.usage
                    if chunk.finish_reason:
                        finish_reason = chunk.finish_reason
            except ProviderError as provider_error:
                ex.last_error = provider_error
                ex.record_attempt(route, "failed", attempt_start, error_code=provider_error.error_class.value)
                if provider_error.error_class != ErrorClass.BAD_REQUEST:
                    breaker.record_failure()
                metrics.PROVIDER_ERRORS.labels(
                    provider=route.provider, error_class=provider_error.error_class.value
                ).inc()
                if not emitted and provider_error.fallbackable and route_index < len(ex.ordered_routes) - 1:
                    ex.fallback_reason = f"{provider_error.error_class.value}:{route.provider}"
                    continue
                ex.finalise_failure(f"provider_{provider_error.error_class.value}")
                yield _sse_error(
                    ex,
                    provider_error.error_class.value,
                    "stream terminated after provider failure; no fallback is "
                    "possible once streaming has started"
                    if emitted
                    else "provider request failed",
                )
                yield "data: [DONE]\n\n"
                return
            if final_usage is None:
                from ..providers.base import Usage
                from ..domain.pricing import estimate_tokens

                final_usage = Usage(
                    input_tokens=ex.est_input_tokens,
                    output_tokens=max(1, estimate_tokens("".join(content_parts))),
                    source="estimated",
                )
            attempt = ex.record_attempt(route, "succeeded", attempt_start, usage=final_usage)
            breaker.record_success()
            cost = ex.finalise_success(route, final_usage, attempt)
            ex.response_body(route, "".join(content_parts), finish_reason, final_usage, cost)
            yield _sse_chunk(ex, route, "", finish_reason, usage=final_usage)
            yield "data: [DONE]\n\n"
            return
        ex.finalise_failure("all_routes_unavailable")
        yield _sse_error(ex, "all_routes_failed", "all eligible provider routes were unavailable")
        yield "data: [DONE]\n\n"
    finally:
        LIMITER.release_concurrency(project.id)
        metrics.IN_PROGRESS.dec()


def _sse_chunk(ex: _Execution, route: ModelRoute, content: str, finish_reason: str | None, usage=None) -> str:
    import json as _json

    delta: dict = {"role": "assistant"} if content else {}
    if content:
        delta["content"] = content
    chunk = {
        "id": f"chatcmpl-{ex.request_row.id}",
        "object": "chat.completion.chunk",
        "created": int(datetime.now(timezone.utc).timestamp()),
        "model": ex.payload.model,
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish_reason}],
    }
    if usage is not None:
        chunk["usage"] = {
            "prompt_tokens": usage.input_tokens,
            "completion_tokens": usage.output_tokens,
            "total_tokens": usage.input_tokens + usage.output_tokens,
        }
    return f"data: {_json.dumps(chunk)}\n\n"


def _sse_error(ex: _Execution, code: str, message: str) -> str:
    import json as _json

    payload = {
        "error": {"message": message, "type": "provider_error", "code": code},
        "modelrail": {"request_id": ex.request_row.id},
    }
    return f"event: error\ndata: {_json.dumps(payload)}\n\n"
