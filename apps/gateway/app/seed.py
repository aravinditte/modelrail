"""Seed a runnable demo: organization, project, policy, routes, one API key.

Usage:  python -m app.seed     (prints the API key ONCE — store it safely)
Idempotent for org/project/routes; a fresh key is minted on each run.
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

if __package__ is None or __package__ == "":
    import sys

    _gateway_dir = Path(__file__).resolve().parent.parent
    if str(_gateway_dir) not in sys.path:
        sys.path.insert(0, str(_gateway_dir))
    from app.core.security import generate_api_key
    from app.db.models import ApiKey, ModelRoute, Organization, Policy, Project
    from app.db.session import get_session_factory, init_db
else:
    from .core.security import generate_api_key
    from .db.models import ApiKey, ModelRoute, Organization, Policy, Project
    from .db.session import get_session_factory, init_db

MOCK_IN = Decimal("0.000001")  # $1 per 1M input tokens (simulated pricing)
MOCK_OUT = Decimal("0.000002")


def seed(db: Session) -> dict:
    org = db.execute(select(Organization).where(Organization.name == "Demo Org")).scalar_one_or_none()
    if org is None:
        org = Organization(name="Demo Org")
        db.add(org)
        db.commit()
        db.refresh(org)
    project = db.execute(select(Project).where(Project.name == "demo-app")).scalar_one_or_none()
    if project is None:
        project = Project(name="demo-app", organization_id=org.id)
        db.add(project)
        db.commit()
        db.refresh(project)
    policy = db.execute(select(Policy).where(Policy.project_id == project.id)).scalar_one_or_none()
    if policy is None:
        policy = Policy(
            project_id=project.id,
            allowed_models=["*"],
            requests_per_minute=600,
            tokens_per_minute=1_000_000,
            max_concurrency=16,
            max_output_tokens=2048,
            budget_limit=Decimal("10.00"),
            routing_policy="priority",
        )
        db.add(policy)
        db.commit()

    def ensure_route(
        alias, provider, upstream, priority, caps=None, config=None, in_price=MOCK_IN, out_price=MOCK_OUT
    ):
        existing = db.execute(
            select(ModelRoute).where(
                ModelRoute.alias == alias,
                ModelRoute.provider == provider,
                ModelRoute.upstream_model == upstream,
            )
        ).scalar_one_or_none()
        if existing is None:
            db.add(
                ModelRoute(
                    alias=alias,
                    provider=provider,
                    upstream_model=upstream,
                    priority=priority,
                    capabilities=caps or {"streaming": True},
                    configuration=config or {},
                    input_price_per_token=in_price,
                    output_price_per_token=out_price,
                )
            )
            db.commit()

    # Primary deterministic route + Ollama fallback on the same alias
    ensure_route("modelrail-fast", "mock", "mock-1", 1, config={"fail_key": "primary"})
    ensure_route("modelrail-fast", "ollama", "llama3.1", 2, config={"fail_key": "ollama"})
    # Secondary mock used by the failure/recovery demo as an independent route
    ensure_route("modelrail-resilient", "mock", "mock-1", 1, config={"fail_key": "primary"})
    ensure_route("modelrail-resilient", "mock-secondary", "mock-2", 2, config={"fail_key": "secondary"})
    # Cost/latency demo alias with two mocks at different prices
    ensure_route(
        "modelrail-flex",
        "mock",
        "mock-1",
        1,
        config={"fail_key": "primary"},
        in_price=Decimal("0.000003"),
        out_price=Decimal("0.000006"),
    )
    ensure_route(
        "modelrail-flex",
        "mock-secondary",
        "mock-2",
        2,
        config={"fail_key": "secondary"},
        in_price=Decimal("0.0000005"),
        out_price=Decimal("0.000001"),
    )

    plaintext, prefix, key_hash = generate_api_key()
    key = ApiKey(project_id=project.id, name="demo-key", key_prefix=prefix, key_hash=key_hash)
    db.add(key)
    db.commit()
    return {
        "organization_id": org.id,
        "project_id": project.id,
        "project_name": project.name,
        "api_key": plaintext,
        "key_prefix": prefix,
    }


def main() -> None:
    init_db()
    factory = get_session_factory()
    session = factory()
    try:
        result = seed(session)
    finally:
        session.close()
    print("ModelRail demo seeded.")
    print(f"  project: {result['project_name']} ({result['project_id']})")
    print(f"  API key (shown once): {result['api_key']}")
    print(
        "  Try: curl http://localhost:8000/v1/chat/completions -H "
        f"'Authorization: Bearer {result['api_key']}' -H 'Content-Type: application/json' "
        "-d '{\"model\": \"modelrail-fast\", \"messages\": [{\"role\": \"user\", \"content\": \"hello\"}]}'"
    )


if __name__ == "__main__":
    main()
