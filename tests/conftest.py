"""Shared fixtures: isolated SQLite DB, seeded helpers, clean registries."""

from __future__ import annotations

import os
import sys
import uuid
from decimal import Decimal
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "apps" / "gateway"))
sys.path.insert(0, str(REPO_ROOT / "packages" / "evals"))

os.environ.setdefault("DATABASE_URL", f"sqlite:///{REPO_ROOT}/.pytest-modelrail.db")
os.environ.setdefault("ADMIN_TOKEN", "test-admin-token")
os.environ.setdefault("API_KEY_PEPPER", "test-pepper")
os.environ["EVAL_DATASET_PATH"] = str(REPO_ROOT / "packages/evals/datasets/modelrail-eval-v1.jsonl")
os.environ["EVAL_PACKAGE_PATH"] = str(REPO_ROOT / "packages" / "evals")
os.environ["CIRCUIT_FAILURE_THRESHOLD"] = "3"
os.environ["RETRY_BASE_DELAY_S"] = "0.01"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.core.security import generate_api_key  # noqa: E402
from app.db.models import ApiKey, Base, ModelRoute, Organization, Policy, Project  # noqa: E402
from app.db.session import get_engine, get_session_factory, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.providers.mock import MockProvider  # noqa: E402
from app.services.ratelimit import LIMITER  # noqa: E402
from app.services.reliability import BREAKERS  # noqa: E402

ADMIN = {"X-Admin-Token": "test-admin-token"}


@pytest.fixture(scope="session", autouse=True)
def _database():
    engine = get_engine()
    Base.metadata.drop_all(bind=engine)
    init_db()
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture(autouse=True)
def _clean_state():
    LIMITER.reset()
    BREAKERS.reset()
    MockProvider.reset()
    # Full row-level isolation: the DB is session-scoped for speed, but routes
    # and requests from a previous test must never leak into the next one
    # (duplicate routes for one alias would corrupt routing/attempt counts).
    from app.db.models import (
        AdminIdentity,
        ApiKey,
        AuditEvent,
        BudgetReservation,
        EvaluationResult,
        EvaluationRun,
        LogicalRequest,
        ModelRoute,
        Organization,
        Policy,
        Project,
        ProviderAttempt,
        UsageEvent,
    )

    factory = get_session_factory()
    session = factory()
    try:
        for model in (
            ProviderAttempt,
            UsageEvent,
            BudgetReservation,
            EvaluationResult,
            EvaluationRun,
            LogicalRequest,
            AuditEvent,
            ApiKey,
            Policy,
            AdminIdentity,
            ModelRoute,
            Project,
            Organization,
        ):
            session.query(model).delete()
        session.commit()
    finally:
        session.close()
    yield


@pytest.fixture()
def client():
    return TestClient(app)


@pytest.fixture()
def db():
    factory = get_session_factory()
    session = factory()
    try:
        yield session
    finally:
        session.close()


def make_project(
    db,
    *,
    budget: str | None = None,
    routing_policy: str = "priority",
    allowed: list | None = None,
    rpm: int = 100000,
    tpm: int = 100_000_000,
    max_concurrency: int = 64,
    max_output_tokens: int = 4096,
    org_name: str | None = None,
) -> dict:
    suffix = uuid.uuid4().hex[:8]
    org = Organization(name=org_name or f"Org {suffix}")
    db.add(org)
    db.commit()
    db.refresh(org)
    project = Project(name=f"proj-{suffix}", organization_id=org.id)
    db.add(project)
    db.commit()
    db.refresh(project)
    policy = Policy(
        project_id=project.id,
        allowed_models=allowed or ["*"],
        requests_per_minute=rpm,
        tokens_per_minute=tpm,
        max_concurrency=max_concurrency,
        max_output_tokens=max_output_tokens,
        budget_limit=Decimal(budget) if budget is not None else None,
        routing_policy=routing_policy,
    )
    db.add(policy)
    db.commit()
    plaintext, prefix, key_hash = generate_api_key()
    db.add(ApiKey(project_id=project.id, name="test", key_prefix=prefix, key_hash=key_hash))
    db.commit()
    return {
        "org_id": org.id,
        "project_id": project.id,
        "policy_id": policy.id,
        "api_key": plaintext,
        "auth": {"Authorization": f"Bearer {plaintext}"},
    }


def add_route(
    db,
    alias: str,
    provider: str = "mock",
    upstream: str = "mock-1",
    priority: int = 1,
    config: dict | None = None,
    in_price: str = "0.000001",
    out_price: str = "0.000002",
    enabled: bool = True,
    caps: dict | None = None,
) -> str:
    route = ModelRoute(
        alias=alias,
        provider=provider,
        upstream_model=upstream,
        priority=priority,
        capabilities=caps or {"streaming": True},
        configuration=config or {},
        input_price_per_token=Decimal(in_price),
        output_price_per_token=Decimal(out_price),
        enabled=enabled,
    )
    db.add(route)
    db.commit()
    db.refresh(route)
    return route.id


@pytest.fixture()
def project(db):
    return make_project(db)


def get_route(db, alias: str, provider: str):
    return db.execute(
        select(ModelRoute).where(ModelRoute.alias == alias, ModelRoute.provider == provider)
    ).scalar_one()
