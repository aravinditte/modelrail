"""Regression tests for the 2026-10-26 double-audit fix round.

Each test pins one confirmed audit finding:
1. Budget: reservations parked as reconciliation_needed still count against
   the hard budget until reconciliation resolves them.
2. Capabilities: list-form capabilities are normalised to a dict at the
   admin API, and routing tolerates legacy list values without crashing.
3. Tenant scoping: an org-less non-admin identity fails closed, and
   GET /admin/v1/usage never leaks other tenants' totals or budgets.
4. Unknown request fields: 422 in the standard envelope, code
   unsupported_field.
5. Config: the documented .env.example variable names actually bind.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.core.errors import GatewayError
from app.core.security import hash_admin_token
from app.db.models import AdminIdentity
from app.main import app
from app.services import budget as budget_service
from tests.conftest import ADMIN, add_route, make_project

CHAT = "/v1/chat/completions"


@pytest.fixture()
def client():
    return TestClient(app)


# -- 1. budget: parked reservations keep counting ---------------------------


def test_parked_reservation_still_counts_against_budget(db):
    project = make_project(db, budget="0.45")
    pid = project["project_id"]
    first = budget_service.reserve(db, pid, "req-1", Decimal("0.21"), Decimal("0.45"))
    budget_service.mark_reconciliation_needed(db, first.id)
    assert budget_service.committed_amount(db, pid) == Decimal("0.21")
    # A second reservation fits (0.42 <= 0.45)...
    budget_service.reserve(db, pid, "req-2", Decimal("0.21"), Decimal("0.45"))
    # ...but a third must be rejected even though req-1's cost is unknown:
    # its parked reservation still occupies budget.
    with pytest.raises(GatewayError) as exc:
        budget_service.reserve(db, pid, "req-3", Decimal("0.21"), Decimal("0.45"))
    assert exc.value.code == "budget_exceeded"
    # After reconciliation resolves the stale reservations (no recorded
    # usage -> released without inventing usage), capacity frees up again.
    budget_service.reconcile(db, stale_after_s=-1)
    assert budget_service.committed_amount(db, pid) == Decimal("0")
    budget_service.reserve(db, pid, "req-4", Decimal("0.21"), Decimal("0.45"))


# -- 2. capabilities shapes ---------------------------------------------------


def test_admin_api_normalises_list_capabilities(client, db):
    project = make_project(db)
    resp = client.post(
        "/admin/v1/models",
        headers=ADMIN,
        json={
            "alias": "alias-caps",
            "provider": "mock",
            "upstream_model": "mock-1",
            "priority": 1,
            "capabilities": ["chat", "streaming"],
            "input_price_per_token": 0.000001,
            "output_price_per_token": 0.000002,
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["capabilities"] == {"chat": True, "streaming": True}
    # Streaming chat against the dashboard-style route must not 500.
    stream = client.post(
        CHAT,
        headers=project["auth"],
        json={
            "model": "alias-caps",
            "stream": True,
            "messages": [{"role": "user", "content": "echo: hi"}],
        },
    )
    assert stream.status_code == 200
    assert stream.text.rstrip().endswith("[DONE]")


def test_routing_tolerates_legacy_list_capabilities(client, db):
    project = make_project(db)
    add_route(db, "alias-legacy", caps=["chat", "streaming"])
    resp = client.post(
        CHAT,
        headers=project["auth"],
        json={"model": "alias-legacy", "messages": [{"role": "user", "content": "echo: hi"}]},
    )
    assert resp.status_code == 200


# -- 3. tenant scoping ---------------------------------------------------------


def _identity(db, token: str, role: str, organization_id: str | None) -> dict:
    db.add(
        AdminIdentity(
            name="audit-test",
            role=role,
            organization_id=organization_id,
            token_prefix=token[:16],
            token_hash=hash_admin_token(token),
        )
    )
    db.commit()
    return {"X-Admin-Token": token}


def test_orgless_scoped_identity_fails_closed(client, db):
    project = make_project(db)
    headers = _identity(db, "orgless-pa-token-1", "project_admin", None)
    resp = client.get(f"/admin/v1/usage?project_id={project['project_id']}", headers=headers)
    assert resp.status_code == 403
    assert resp.json()["error"]["code"] == "organization_scope_required"
    usage = client.get("/admin/v1/usage", headers=headers)
    assert usage.status_code == 200
    assert usage.json()["budgets"] == []
    assert usage.json()["totals"]["cost"] == "0"


def test_usage_endpoint_scopes_to_own_org(client, db):
    mine = make_project(db, budget="5.00")
    other = make_project(db, budget="7.00")
    add_route(db, "alias-usage")
    for proj in (mine, other):
        resp = client.post(
            CHAT,
            headers=proj["auth"],
            json={"model": "alias-usage", "messages": [{"role": "user", "content": "echo: hi"}]},
        )
        assert resp.status_code == 200
    headers = _identity(db, "org-viewer-token-1", "viewer", mine["org_id"])
    usage = client.get("/admin/v1/usage", headers=headers)
    assert usage.status_code == 200
    body = usage.json()
    budget_projects = {b["project_id"] for b in body["budgets"]}
    assert budget_projects == {mine["project_id"]}
    breakdown_projects = {e["id"] for e in body["breakdown"] if e["scope"] == "by_project"}
    assert breakdown_projects == {mine["project_id"]}
    # Global admin still sees everything.
    admin_usage = client.get("/admin/v1/usage", headers=ADMIN).json()
    assert {b["project_id"] for b in admin_usage["budgets"]} == {
        mine["project_id"],
        other["project_id"],
    }


# -- 4. unknown fields ----------------------------------------------------------


def test_unknown_field_returns_envelope_422(client, db):
    project = make_project(db)
    add_route(db, "alias-unknown")
    resp = client.post(
        CHAT,
        headers=project["auth"],
        json={
            "model": "alias-unknown",
            "messages": [{"role": "user", "content": "hi"}],
            "definitely_not_a_field": 1,
        },
    )
    assert resp.status_code == 422
    error = resp.json()["error"]
    assert error["code"] == "unsupported_field"
    assert "definitely_not_a_field" in error["message"]


# -- 5. documented env names bind -----------------------------------------------


def test_documented_env_names_bind(monkeypatch):
    from app.config import Settings

    monkeypatch.setenv("PROVIDER_REQUEST_TIMEOUT_SECONDS", "12.5")
    monkeypatch.setenv("OVERALL_REQUEST_DEADLINE_SECONDS", "33")
    monkeypatch.setenv("RETRY_MAX_ATTEMPTS", "7")
    monkeypatch.setenv("EVALUATION_JOB_DEADLINE_SECONDS", "55")
    monkeypatch.setenv("PRICING_VERSION", "price-test-9")
    monkeypatch.setenv("DEFAULT_CURRENCY", "JPY")
    settings = Settings()
    assert settings.provider_request_timeout_s == 12.5
    assert settings.request_deadline_s == 33.0
    assert settings.max_total_attempts == 7
    assert settings.evaluation_job_deadline_s == 55.0
    assert settings.pricing_version == "price-test-9"
    assert settings.default_currency == "JPY"
