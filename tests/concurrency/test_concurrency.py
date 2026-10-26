"""Concurrency tests (spec 17.2/17.6): concurrent budget reservations can
never over-allocate, and settled totals stay consistent."""

from __future__ import annotations

import threading

from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import add_route, make_project

CHAT = "/v1/chat/completions"


def test_concurrent_budget_no_over_allocation(db):
    # Route price: 0.01/token. The prompt below estimates to 11 input tokens,
    # max_tokens=10 -> reservation = 0.11 + 0.10 = 0.21. Budget 0.45 fits
    # exactly two reservations in flight (0.42); a third would reach 0.63.
    # The latency marker holds requests open so reservations genuinely overlap.
    project = make_project(db, budget="0.45", max_concurrency=64)
    add_route(db, "alias-conc", in_price="0.01", out_price="0.01", config={"fail_key": "primary"})
    barrier = threading.Barrier(8)
    results: list[int] = []
    errors: list[str] = []

    def worker():
        client = TestClient(app)
        try:
            barrier.wait(timeout=60)
            resp = client.post(
                CHAT,
                headers=project["auth"],
                json={
                    "model": "alias-conc",
                    "max_tokens": 10,
                    "messages": [{"role": "user", "content": "[mock:latency=1500] echo: hi"}],
                },
            )
            results.append(resp.status_code)
            if resp.status_code not in (200, 429):
                errors.append(resp.text[:200])
        except Exception as exc:  # noqa: BLE001
            errors.append(str(exc))

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=120)
    assert not errors, errors
    assert set(results) <= {200, 429}
    successes = results.count(200)
    assert successes >= 2  # at least the two that fit the budget concurrently

    from sqlalchemy import func, select
    from app.db.models import BudgetReservation

    settled = db.execute(
        select(func.coalesce(func.sum(BudgetReservation.settled_amount), 0)).where(
            BudgetReservation.project_id == project["project_id"], BudgetReservation.status == "settled"
        )
    ).scalar_one()
    reserved = db.execute(
        select(func.coalesce(func.sum(BudgetReservation.reserved_amount), 0)).where(
            BudgetReservation.project_id == project["project_id"], BudgetReservation.status == "reserved"
        )
    ).scalar_one()
    # The core invariant: committed spend never exceeds the hard budget.
    assert float(settled) + float(reserved) <= 0.45 + 1e-9
