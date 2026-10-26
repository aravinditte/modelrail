"""Routing engine (spec section 8).

Pure selection logic over eligible routes — no provider HTTP code here.
Eligibility: route enabled, alias allowed by the project policy, capability
match (e.g. streaming), circuit not open. Ordering by policy:
- priority: lowest priority value first
- cost: lowest estimated cost for the estimated workload first
- latency: lowest rolling mean attempt latency first; routes with fewer than
  MIN_LATENCY_SAMPLES measurements fall back to priority order (cold start)
Every decision is returned as an auditable record (no prompt content).
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..db.models import ModelRoute, ProviderAttempt
from ..domain.pricing import calculate_cost
from .reliability import BREAKERS

MIN_LATENCY_SAMPLES = 5
LATENCY_WINDOW = 50


def eligible_routes(db: Session, alias: str, allowed_models: list, streaming: bool) -> list[ModelRoute]:
    if "*" not in allowed_models and alias not in allowed_models:
        return []
    routes = (
        db.execute(select(ModelRoute).where(ModelRoute.alias == alias, ModelRoute.enabled.is_(True)))
        .scalars()
        .all()
    )
    out = []
    for r in routes:
        caps = r.capabilities or {}
        if isinstance(caps, list):
            # Legacy/client-supplied list form: ["chat", "streaming"] means
            # each named capability is supported.
            caps = {str(c): True for c in caps}
        if streaming and isinstance(caps, dict) and caps.get("streaming") is False:
            continue
        out.append(r)
    return out


def rolling_latency_ms(db: Session, route: ModelRoute) -> tuple[float | None, int]:
    rows = (
        db.execute(
            select(ProviderAttempt.latency_ms)
            .where(
                ProviderAttempt.provider == route.provider,
                ProviderAttempt.upstream_model == route.upstream_model,
                ProviderAttempt.status == "succeeded",
                ProviderAttempt.latency_ms.is_not(None),
            )
            .order_by(ProviderAttempt.started_at.desc())
            .limit(LATENCY_WINDOW)
        )
        .scalars()
        .all()
    )
    non_null_rows = [r for r in rows if r is not None]
    if not non_null_rows:
        return None, 0
    return sum(non_null_rows) / len(non_null_rows), len(non_null_rows)


def order_routes(
    db: Session, routes: list[ModelRoute], policy_name: str, est_input_tokens: int, est_output_tokens: int
) -> tuple[list[ModelRoute], list[dict]]:
    candidates_meta = []
    for r in routes:
        est_cost = calculate_cost(
            est_input_tokens, est_output_tokens, r.input_price_per_token, r.output_price_per_token
        )
        avg_latency, samples = rolling_latency_ms(db, r)
        candidates_meta.append(
            {
                "route_id": r.id,
                "provider": r.provider,
                "upstream_model": r.upstream_model,
                "priority": r.priority,
                "estimated_cost": str(est_cost),
                "avg_latency_ms": avg_latency,
                "latency_samples": samples,
                "circuit": BREAKERS.get(r.provider, r.upstream_model).state,
            }
        )
    meta_by_id = {m["route_id"]: m for m in candidates_meta}

    if policy_name == "cost":
        ordered = sorted(routes, key=lambda r: (Decimal(str(meta_by_id[r.id]["estimated_cost"])), r.priority))
    elif policy_name == "latency":

        def latency_key(r: ModelRoute):
            m = meta_by_id[r.id]
            if int(str(m["latency_samples"])) < MIN_LATENCY_SAMPLES or m["avg_latency_ms"] is None:
                return (1, r.priority)  # cold start: priority order, after measured routes
            return (0, float(str(m["avg_latency_ms"])))

        ordered = sorted(routes, key=latency_key)
    else:  # priority
        ordered = sorted(routes, key=lambda r: r.priority)
    return ordered, candidates_meta
