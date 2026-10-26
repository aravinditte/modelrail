"""Property-based tests (spec 17.6) for the core accounting invariants."""

from __future__ import annotations

import uuid
from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from app.domain.pricing import calculate_cost, estimate_tokens
from app.services.usage import record_usage_event


@given(
    in_t=st.integers(min_value=0, max_value=1_000_000),
    out_t=st.integers(min_value=0, max_value=1_000_000),
    in_p=st.decimals(min_value=0, max_value="0.01", places=6),
    out_p=st.decimals(min_value=0, max_value="0.01", places=6),
)
@settings(max_examples=50, deadline=None)
def test_cost_is_nonnegative_and_monotonic(in_t, out_t, in_p, out_p):
    cost = calculate_cost(in_t, out_t, in_p, out_p)
    assert cost >= 0
    assert calculate_cost(in_t + 10, out_t, in_p, out_p) >= cost
    assert calculate_cost(in_t, out_t + 10, in_p, out_p) >= cost


@given(text=st.text(max_size=500))
@settings(max_examples=50, deadline=None)
def test_token_estimate_never_exceeds_chars(text):
    assert 0 <= estimate_tokens(text) <= max(1, len(text)) if text else estimate_tokens(text) == 0


@given(times=st.integers(min_value=1, max_value=5))
@settings(max_examples=20, deadline=None)
def test_usage_event_submission_is_idempotent(times):
    # Hypothesis tests cannot use pytest fixtures; open a session directly.
    from app.db.session import get_session_factory

    db = get_session_factory()()
    key = f"prop-{uuid.uuid4()}"
    first_total = None
    for _ in range(times):
        event, created = record_usage_event(
            db,
            event_key=key,
            request_id="req-x",
            attempt_id="att-x",
            input_tokens=10,
            output_tokens=5,
            cost=Decimal("0.001"),
            usage_source="simulated",
            pricing_version="price-v1",
        )
        if first_total is None:
            assert created is True
            first_total = event.cost
        else:
            assert created is False
    from sqlalchemy import func, select
    from app.db.models import UsageEvent

    total = db.execute(
        select(func.coalesce(func.sum(UsageEvent.cost), 0)).where(UsageEvent.event_key == key)
    ).scalar_one()
    assert Decimal(str(total)) == Decimal("0.001")
