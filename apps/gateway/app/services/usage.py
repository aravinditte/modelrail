"""Idempotent usage-event recording (spec 10.4).

The event_key unique constraint is the enforcement; a duplicate submission
returns the existing event and never double-counts.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..db.models import UsageEvent


def record_usage_event(
    db: Session,
    *,
    event_key: str,
    request_id: str,
    attempt_id: str | None,
    input_tokens: int,
    output_tokens: int,
    cost: Decimal,
    usage_source: str,
    pricing_version: str,
) -> tuple[UsageEvent, bool]:
    existing = db.execute(select(UsageEvent).where(UsageEvent.event_key == event_key)).scalar_one_or_none()
    if existing is not None:
        return existing, False
    event = UsageEvent(
        event_key=event_key,
        request_id=request_id,
        attempt_id=attempt_id,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cost=cost,
        usage_source=usage_source,
        pricing_version=pricing_version,
    )
    db.add(event)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.execute(select(UsageEvent).where(UsageEvent.event_key == event_key)).scalar_one()
        return existing, False
    db.refresh(event)
    return event, True
