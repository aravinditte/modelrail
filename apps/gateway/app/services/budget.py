"""Budget reservations and settlement (spec section 10).

Concurrency strategy: the project's Project row is locked with
SELECT ... FOR UPDATE inside the reservation transaction (PostgreSQL), and a
per-project in-process lock serialises the same critical section for the
SQLite demo/test configuration. Committed spend = settled reservations +
still-reserved amounts; a new reservation that would exceed the hard budget
is rejected BEFORE any provider call. No check-then-write without the lock.

Settlement is idempotent per reservation; usage events are idempotent per
event_key (unique constraint + insert-or-ignore semantics in usage.py).
"""

from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..core.errors import err
from ..db.models import BudgetReservation, Project, UsageEvent

_project_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def _project_lock(project_id: str) -> threading.Lock:
    with _locks_guard:
        if project_id not in _project_locks:
            _project_locks[project_id] = threading.Lock()
        return _project_locks[project_id]


def committed_amount(db: Session, project_id: str) -> Decimal:
    settled = db.execute(
        select(func.coalesce(func.sum(BudgetReservation.settled_amount), 0)).where(
            BudgetReservation.project_id == project_id,
            BudgetReservation.status == "settled",
        )
    ).scalar_one()
    reserved = db.execute(
        select(func.coalesce(func.sum(BudgetReservation.reserved_amount), 0)).where(
            BudgetReservation.project_id == project_id,
            BudgetReservation.status == "reserved",
        )
    ).scalar_one()
    return Decimal(str(settled)) + Decimal(str(reserved))


def reserve(
    db: Session, project_id: str, request_id: str, amount: Decimal, budget_limit: Decimal | None
) -> BudgetReservation:
    """Atomically reserve. Raises GatewayError(429, budget_exceeded)."""
    with _project_lock(project_id):
        # Row lock on the project (effective on PostgreSQL; harmless on SQLite)
        db.execute(select(Project).where(Project.id == project_id).with_for_update()).scalars().first()
        if budget_limit is not None:
            committed = committed_amount(db, project_id)
            if committed + amount > budget_limit:
                db.rollback()
                raise err(
                    429,
                    "budget_exceeded",
                    f"project budget would be exceeded (committed {committed}, "
                    f"requested {amount}, limit {budget_limit})",
                    "rate_limit_error",
                )
        reservation = BudgetReservation(
            project_id=project_id, request_id=request_id, reserved_amount=amount, status="reserved"
        )
        db.add(reservation)
        db.commit()
        db.refresh(reservation)
        return reservation


def settle(db: Session, reservation_id: str, final_cost: Decimal) -> BudgetReservation:
    """Settle exactly once; a second settle is a no-op returning current state."""
    reservation = db.get(BudgetReservation, reservation_id)
    if reservation is None:
        raise err(404, "reservation_not_found", "budget reservation not found")
    if reservation.status == "settled":
        return reservation
    reservation.settled_amount = final_cost
    reservation.status = "settled"
    reservation.settled_at = datetime.now(timezone.utc)
    reservation.reconciliation_status = "not_needed"
    db.commit()
    db.refresh(reservation)
    return reservation


def mark_reconciliation_needed(db: Session, reservation_id: str) -> None:
    reservation = db.get(BudgetReservation, reservation_id)
    if reservation and reservation.status == "reserved":
        reservation.status = "reconciliation_needed"
        reservation.reconciliation_status = "pending"
        db.commit()


def release(db: Session, reservation_id: str) -> None:
    reservation = db.get(BudgetReservation, reservation_id)
    if reservation and reservation.status in ("reserved", "reconciliation_needed"):
        reservation.status = "released"
        reservation.settled_amount = Decimal("0")
        reservation.settled_at = datetime.now(timezone.utc)
        db.commit()


def reconcile(db: Session, stale_after_s: int) -> dict:
    """Find stale reservations, settle from recorded usage where it exists,
    otherwise release without inventing usage, and flag the affected requests."""
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=stale_after_s)
    stale = (
        db.execute(
            select(BudgetReservation).where(
                BudgetReservation.status.in_(["reserved", "reconciliation_needed"]),
                BudgetReservation.created_at < cutoff,
            )
        )
        .scalars()
        .all()
    )
    report = {
        "checked": len(stale),
        "settled_from_usage": 0,
        "released_no_usage": 0,
        "unknown_usage_requests": [],
    }
    for reservation in stale:
        usage_total = db.execute(
            select(func.coalesce(func.sum(UsageEvent.cost), 0)).where(
                UsageEvent.request_id == reservation.request_id
            )
        ).scalar_one()
        has_usage = (
            db.execute(
                select(func.count())
                .select_from(UsageEvent)
                .where(UsageEvent.request_id == reservation.request_id)
            ).scalar_one()
            > 0
        )
        if has_usage:
            reservation.settled_amount = Decimal(str(usage_total))
            reservation.status = "settled"
            reservation.settled_at = datetime.now(timezone.utc)
            reservation.reconciliation_status = "settled_from_recorded_usage"
            report["settled_from_usage"] += 1
        else:
            reservation.status = "released"
            reservation.settled_amount = Decimal("0")
            reservation.settled_at = datetime.now(timezone.utc)
            reservation.reconciliation_status = "released_no_usage_recorded"
            report["released_no_usage"] += 1
            report["unknown_usage_requests"].append(reservation.request_id)
        db.add(reservation)
    # duplicate usage check (unique constraint should make this zero)
    dupes = db.execute(
        select(UsageEvent.event_key, func.count()).group_by(UsageEvent.event_key).having(func.count() > 1)
    ).all()
    report["duplicate_event_keys"] = len(dupes)
    db.commit()
    return report
