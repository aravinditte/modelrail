"""Administrative API (spec 6.2).

Admin auth is independent of gateway API keys: an X-Admin-Token belonging to
an AdminIdentity (or the bootstrap token). Roles: admin (all), project_admin
(scoped to its organization, write allowed), viewer (read-only). Every
mutation writes an audit event. Plaintext keys are returned exactly once, at
creation.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ...core.errors import err
from ...core.security import generate_api_key, hash_admin_token
from ...db.models import (
    AdminIdentity,
    ApiKey,
    AuditEvent,
    BudgetReservation,
    EvaluationRun,
    LogicalRequest,
    ModelRoute,
    Organization,
    Policy,
    Project,
    ProviderAttempt,
    UsageEvent,
)
from ...db.session import db_session
from ...schemas.admin import (
    AdminIdentityIn,
    EvaluationIn,
    KeyIn,
    ModelRouteIn,
    ModelRouteUpdate,
    PolicyIn,
    PolicyUpdate,
    ProjectIn,
)
from ...services.auth_service import AdminPrincipal, authenticate_admin
from ...services.evaluation_service import execute_run

router = APIRouter(prefix="/admin/v1")


def principal(request: Request, db: Session) -> AdminPrincipal:
    return authenticate_admin(db, request.headers.get("x-admin-token"))


def audit(
    db: Session,
    who: AdminPrincipal,
    action: str,
    resource_type: str,
    resource_id: str | None,
    organization_id: str | None = None,
    metadata: dict | None = None,
) -> None:
    db.add(
        AuditEvent(
            organization_id=organization_id or who.organization_id,
            actor_id=who.actor_id,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            event_metadata=metadata or {},
        )
    )
    db.commit()


def _route_dict(r: ModelRoute) -> dict:
    return {
        "id": r.id,
        "alias": r.alias,
        "provider": r.provider,
        "upstream_model": r.upstream_model,
        "priority": r.priority,
        "capabilities": r.capabilities,
        "enabled": r.enabled,
        "configuration": r.configuration,
        "configuration_version": r.configuration_version,
        "input_price_per_token": str(r.input_price_per_token),
        "output_price_per_token": str(r.output_price_per_token),
        "pricing_version": r.pricing_version,
    }


def _project_dict(p: Project) -> dict:
    return {
        "id": p.id,
        "organization_id": p.organization_id,
        "name": p.name,
        "status": p.status,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


def _policy_dict(p: Policy) -> dict:
    return {
        "id": p.id,
        "project_id": p.project_id,
        "allowed_models": p.allowed_models,
        "requests_per_minute": p.requests_per_minute,
        "tokens_per_minute": p.tokens_per_minute,
        "max_concurrency": p.max_concurrency,
        "max_output_tokens": p.max_output_tokens,
        "budget_limit": str(p.budget_limit) if p.budget_limit is not None else None,
        "routing_policy": p.routing_policy,
    }


def _get_project_scoped(db: Session, who: AdminPrincipal, project_id: str) -> Project:
    project = db.get(Project, project_id)
    if project is None:
        raise err(404, "project_not_found", "project not found")
    who.check_org(project.organization_id)
    return project


# -- models ---------------------------------------------------------------
@router.get("/models")
def list_model_routes(request: Request, db: Session = Depends(db_session), limit: int = 100, offset: int = 0):
    principal(request, db)
    rows = (
        db.execute(
            select(ModelRoute).order_by(ModelRoute.alias, ModelRoute.priority).limit(limit).offset(offset)
        )
        .scalars()
        .all()
    )
    return {"data": [_route_dict(r) for r in rows]}


@router.post("/models", status_code=201)
def create_model_route(body: ModelRouteIn, request: Request, db: Session = Depends(db_session)):
    who = principal(request, db)
    who.require_write()
    route = ModelRoute(**body.model_dump())
    db.add(route)
    db.commit()
    db.refresh(route)
    audit(db, who, "model_route.create", "model_route", route.id, metadata={"alias": route.alias})
    return _route_dict(route)


@router.put("/models/{route_id}")
def update_model_route(
    route_id: str, body: ModelRouteUpdate, request: Request, db: Session = Depends(db_session)
):
    who = principal(request, db)
    who.require_write()
    route = db.get(ModelRoute, route_id)
    if route is None:
        raise err(404, "model_route_not_found", "model route not found")
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(route, field, value)
    route.configuration_version += 1
    db.commit()
    db.refresh(route)
    audit(db, who, "model_route.update", "model_route", route.id)
    return _route_dict(route)


# -- projects & organizations ----------------------------------------------
@router.get("/projects")
def list_projects(request: Request, db: Session = Depends(db_session), limit: int = 100, offset: int = 0):
    who = principal(request, db)
    query = select(Project).order_by(Project.created_at)
    if who.role != "admin" and who.organization_id:
        query = query.where(Project.organization_id == who.organization_id)
    rows = db.execute(query.limit(limit).offset(offset)).scalars().all()
    return {"data": [_project_dict(p) for p in rows]}


@router.post("/projects", status_code=201)
def create_project(body: ProjectIn, request: Request, db: Session = Depends(db_session)):
    who = principal(request, db)
    who.require_write()
    org_id = body.organization_id
    if org_id is None:
        org = Organization(name=body.organization_name or f"{body.name} org")
        db.add(org)
        db.commit()
        db.refresh(org)
        org_id = org.id
    who.check_org(org_id)
    project = Project(name=body.name, organization_id=org_id)
    db.add(project)
    db.commit()
    db.refresh(project)
    db.add(Policy(project_id=project.id))
    db.commit()
    audit(db, who, "project.create", "project", project.id, organization_id=org_id)
    return _project_dict(project)


# -- keys -------------------------------------------------------------------
@router.get("/keys")
def list_keys(
    request: Request,
    db: Session = Depends(db_session),
    project_id: str | None = None,
    limit: int = 100,
    offset: int = 0,
):
    who = principal(request, db)
    query = select(ApiKey).order_by(ApiKey.created_at)
    if project_id:
        _get_project_scoped(db, who, project_id)
        query = query.where(ApiKey.project_id == project_id)
    elif who.role != "admin" and who.organization_id:
        query = query.join(Project, ApiKey.project_id == Project.id).where(
            Project.organization_id == who.organization_id
        )
    rows = db.execute(query.limit(limit).offset(offset)).scalars().all()
    return {
        "data": [
            {
                "id": k.id,
                "project_id": k.project_id,
                "name": k.name,
                "key_prefix": k.key_prefix,
                "created_at": k.created_at.isoformat(),
                "expires_at": k.expires_at.isoformat() if k.expires_at else None,
                "revoked_at": k.revoked_at.isoformat() if k.revoked_at else None,
                "last_used_at": k.last_used_at.isoformat() if k.last_used_at else None,
            }
            for k in rows
        ]
    }


@router.post("/keys", status_code=201)
def create_key(body: KeyIn, request: Request, db: Session = Depends(db_session)):
    who = principal(request, db)
    who.require_write()
    project = _get_project_scoped(db, who, body.project_id)
    plaintext, prefix, key_hash = generate_api_key()
    key = ApiKey(
        project_id=project.id,
        name=body.name,
        key_prefix=prefix,
        key_hash=key_hash,
        expires_at=body.expires_at,
    )
    db.add(key)
    db.commit()
    db.refresh(key)
    audit(
        db,
        who,
        "api_key.create",
        "api_key",
        key.id,
        organization_id=project.organization_id,
        metadata={"prefix": prefix},
    )
    # Plaintext is returned exactly once, here. It is never stored or logged.
    return {
        "id": key.id,
        "project_id": key.project_id,
        "name": key.name,
        "key_prefix": prefix,
        "api_key": plaintext,
    }


@router.delete("/keys/{key_id}")
def revoke_key(key_id: str, request: Request, db: Session = Depends(db_session)):
    who = principal(request, db)
    who.require_write()
    key = db.get(ApiKey, key_id)
    if key is None:
        raise err(404, "key_not_found", "api key not found")
    project = _get_project_scoped(db, who, key.project_id)
    if key.revoked_at is None:
        key.revoked_at = datetime.now(timezone.utc)
        db.commit()
        audit(db, who, "api_key.revoke", "api_key", key.id, organization_id=project.organization_id)
    return {"id": key.id, "revoked": True}


# -- policies ---------------------------------------------------------------
@router.get("/policies")
def list_policies(request: Request, db: Session = Depends(db_session), project_id: str | None = None):
    who = principal(request, db)
    query = select(Policy)
    if project_id:
        _get_project_scoped(db, who, project_id)
        query = query.where(Policy.project_id == project_id)
    elif who.role != "admin" and who.organization_id:
        query = query.join(Project, Policy.project_id == Project.id).where(
            Project.organization_id == who.organization_id
        )
    return {"data": [_policy_dict(p) for p in db.execute(query).scalars().all()]}


@router.post("/policies", status_code=201)
def create_policy(body: PolicyIn, request: Request, db: Session = Depends(db_session)):
    who = principal(request, db)
    who.require_write()
    project = _get_project_scoped(db, who, body.project_id)
    existing = db.execute(select(Policy).where(Policy.project_id == project.id)).scalar_one_or_none()
    if existing is not None:
        raise err(409, "policy_exists", "a policy already exists for this project; update it instead")
    policy = Policy(**body.model_dump())
    db.add(policy)
    db.commit()
    db.refresh(policy)
    audit(db, who, "policy.create", "policy", policy.id, organization_id=project.organization_id)
    return _policy_dict(policy)


@router.put("/policies/{policy_id}")
def update_policy(policy_id: str, body: PolicyUpdate, request: Request, db: Session = Depends(db_session)):
    who = principal(request, db)
    who.require_write()
    policy = db.get(Policy, policy_id)
    if policy is None:
        raise err(404, "policy_not_found", "policy not found")
    _get_project_scoped(db, who, policy.project_id)
    for field, value in body.model_dump(exclude_none=True).items():
        setattr(policy, field, value)
    db.commit()
    db.refresh(policy)
    audit(db, who, "policy.update", "policy", policy.id)
    return _policy_dict(policy)


# -- usage & requests ---------------------------------------------------------
@router.get("/usage")
def usage(request: Request, db: Session = Depends(db_session), project_id: str | None = None):
    who = principal(request, db)
    if project_id:
        _get_project_scoped(db, who, project_id)
    base = select(
        UsageEvent.request_id,
        func.sum(UsageEvent.input_tokens),
        func.sum(UsageEvent.output_tokens),
        func.sum(UsageEvent.cost),
    )
    totals_row = db.execute(base).one()
    by_request: dict[str, dict] = {}
    project_by_request = dict(db.execute(select(LogicalRequest.id, LogicalRequest.project_id)).all())
    alias_by_request = dict(db.execute(select(LogicalRequest.id, LogicalRequest.model_alias)).all())
    for req_id, in_t, out_t, cost in db.execute(base.group_by(UsageEvent.request_id)).all():
        pid = project_by_request.get(req_id)
        if project_id and pid != project_id:
            continue
        for bucket_key, bucket in (("by_project", pid), ("by_model", alias_by_request.get(req_id))):
            if bucket is None:
                continue
            entry = by_request.setdefault(
                f"{bucket_key}:{bucket}",
                {
                    "scope": bucket_key,
                    "id": bucket,
                    "requests": 0,
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cost": "0",
                },
            )
            entry["requests"] += 1
            entry["input_tokens"] += int(in_t or 0)
            entry["output_tokens"] += int(out_t or 0)
            entry["cost"] = str(float(entry["cost"]) + float(cost or 0))
    budgets = []
    policy_query = select(Policy)
    if project_id:
        policy_query = policy_query.where(Policy.project_id == project_id)
    for policy in db.execute(policy_query).scalars().all():
        settled = db.execute(
            select(func.coalesce(func.sum(BudgetReservation.settled_amount), 0)).where(
                BudgetReservation.project_id == policy.project_id, BudgetReservation.status == "settled"
            )
        ).scalar_one()
        reserved = db.execute(
            select(func.coalesce(func.sum(BudgetReservation.reserved_amount), 0)).where(
                BudgetReservation.project_id == policy.project_id, BudgetReservation.status == "reserved"
            )
        ).scalar_one()
        pending = db.execute(
            select(func.count())
            .select_from(BudgetReservation)
            .where(
                BudgetReservation.project_id == policy.project_id,
                BudgetReservation.status == "reconciliation_needed",
            )
        ).scalar_one()
        budgets.append(
            {
                "project_id": policy.project_id,
                "budget_limit": str(policy.budget_limit) if policy.budget_limit is not None else None,
                "settled": str(settled),
                "reserved": str(reserved),
                "reconciliation_needed": pending,
                "utilisation": (
                    str((float(settled) + float(reserved)) / float(policy.budget_limit))
                    if policy.budget_limit
                    else None
                ),
            }
        )
    return {
        "totals": {
            "requests_with_usage": len({r for r in project_by_request}),
            "input_tokens": int(totals_row[1] or 0),
            "output_tokens": int(totals_row[2] or 0),
            "cost": str(totals_row[3] or 0),
        },
        "breakdown": sorted(by_request.values(), key=lambda e: (e["scope"], e["id"])),
        "budgets": budgets,
    }


@router.get("/requests")
def list_requests(
    request: Request,
    db: Session = Depends(db_session),
    status: str | None = None,
    model: str | None = None,
    project_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
):
    who = principal(request, db)
    query = select(LogicalRequest).order_by(LogicalRequest.started_at.desc())
    if status:
        query = query.where(LogicalRequest.status == status)
    if model:
        query = query.where(LogicalRequest.model_alias == model)
    if project_id:
        _get_project_scoped(db, who, project_id)
        query = query.where(LogicalRequest.project_id == project_id)
    elif who.role != "admin" and who.organization_id:
        query = query.join(Project, LogicalRequest.project_id == Project.id).where(
            Project.organization_id == who.organization_id
        )
    rows = db.execute(query.limit(limit).offset(offset)).scalars().all()
    return {"data": [_request_dict(r) for r in rows]}


def _request_dict(r: LogicalRequest) -> dict:
    return {
        "id": r.id,
        "project_id": r.project_id,
        "model_alias": r.model_alias,
        "status": r.status,
        "started_at": r.started_at.isoformat() if r.started_at else None,
        "completed_at": r.completed_at.isoformat() if r.completed_at else None,
        "total_latency_ms": r.total_latency_ms,
        "total_attempts": r.total_attempts,
        "input_tokens": r.input_tokens,
        "output_tokens": r.output_tokens,
        "final_cost": str(r.final_cost) if r.final_cost is not None else None,
        "cost_basis": r.cost_basis,
        "error_code": r.error_code,
        "selected_provider": r.selected_provider,
        "selected_upstream_model": r.selected_upstream_model,
        "fallback_reason": r.fallback_reason,
        "routing_policy": r.routing_policy,
        "route_decision": r.route_decision,
    }


@router.get("/requests/{request_id}")
def get_request(request_id: str, request: Request, db: Session = Depends(db_session)):
    who = principal(request, db)
    row = db.get(LogicalRequest, request_id)
    if row is None:
        raise err(404, "request_not_found", "request not found")
    _get_project_scoped(db, who, row.project_id)
    attempts = (
        db.execute(
            select(ProviderAttempt)
            .where(ProviderAttempt.request_id == row.id)
            .order_by(ProviderAttempt.attempt_number)
        )
        .scalars()
        .all()
    )
    detail = _request_dict(row)
    detail["attempts"] = [
        {
            "id": a.id,
            "provider": a.provider,
            "upstream_model": a.upstream_model,
            "attempt_number": a.attempt_number,
            "status": a.status,
            "latency_ms": a.latency_ms,
            "input_tokens": a.input_tokens,
            "output_tokens": a.output_tokens,
            "cost": str(a.cost) if a.cost is not None else None,
            "cost_basis": a.cost_basis,
            "error_code": a.error_code,
            "fallback_reason": a.fallback_reason,
        }
        for a in attempts
    ]
    return detail


# -- evaluations --------------------------------------------------------------
@router.post("/evaluations", status_code=201)
def create_evaluation(body: EvaluationIn, request: Request, db: Session = Depends(db_session)):
    who = principal(request, db)
    who.require_write()
    run = EvaluationRun(
        dataset_version=body.dataset_version,
        candidate_model=body.candidate_model,
        baseline_model=body.baseline_model,
        configuration_version=body.configuration_version,
        status="pending",
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    audit(db, who, "evaluation.create", "evaluation_run", run.id)
    if not body.run_async:
        run = execute_run(db, run)
    return _run_dict(run)


def _run_dict(run: EvaluationRun) -> dict:
    return {
        "id": run.id,
        "dataset_version": run.dataset_version,
        "candidate_model": run.candidate_model,
        "baseline_model": run.baseline_model,
        "configuration_version": run.configuration_version,
        "status": run.status,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "completed_at": run.completed_at.isoformat() if run.completed_at else None,
        "summary": run.summary,
    }


@router.get("/evaluations/{run_id}")
def get_evaluation(run_id: str, request: Request, db: Session = Depends(db_session)):
    principal(request, db)
    run = db.get(EvaluationRun, run_id)
    if run is None:
        raise err(404, "evaluation_not_found", "evaluation run not found")
    return _run_dict(run)


# -- audit ----------------------------------------------------------------------
@router.get("/audit-events")
def list_audit_events(request: Request, db: Session = Depends(db_session), limit: int = 100, offset: int = 0):
    who = principal(request, db)
    query = select(AuditEvent).order_by(AuditEvent.created_at.desc())
    if who.role != "admin" and who.organization_id:
        query = query.where(AuditEvent.organization_id == who.organization_id)
    rows = db.execute(query.limit(limit).offset(offset)).scalars().all()
    return {
        "data": [
            {
                "id": e.id,
                "organization_id": e.organization_id,
                "actor_id": e.actor_id,
                "action": e.action,
                "resource_type": e.resource_type,
                "resource_id": e.resource_id,
                "created_at": e.created_at.isoformat() if e.created_at else None,
                "metadata": e.event_metadata,
            }
            for e in rows
        ]
    }


# -- admin identities & reconciliation -------------------------------------------
@router.post("/admin-identities", status_code=201)
def create_admin_identity(body: AdminIdentityIn, request: Request, db: Session = Depends(db_session)):
    who = principal(request, db)
    who.require_admin()
    import secrets as _secrets

    token = "mr_admin_" + _secrets.token_urlsafe(32)
    identity = AdminIdentity(
        name=body.name,
        role=body.role,
        organization_id=body.organization_id,
        token_prefix=token[:16],
        token_hash=hash_admin_token(token),
    )
    db.add(identity)
    db.commit()
    db.refresh(identity)
    audit(db, who, "admin_identity.create", "admin_identity", identity.id)
    return {
        "id": identity.id,
        "name": identity.name,
        "role": identity.role,
        "organization_id": identity.organization_id,
        "admin_token": token,
    }


@router.post("/reconcile")
def run_reconcile(request: Request, db: Session = Depends(db_session)):
    who = principal(request, db)
    who.require_write()
    from ...config import get_settings
    from ...services.budget import reconcile

    report = reconcile(db, stale_after_s=get_settings().stale_reservation_s)
    audit(db, who, "budget.reconcile", "budget", None, metadata={"checked": report["checked"]})
    return report
