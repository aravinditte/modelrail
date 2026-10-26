"""Authentication / authorization for gateway keys and admin identities."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..core.errors import err
from ..core.security import hash_admin_token, is_bootstrap_admin, key_prefix_of, verify_api_key
from ..db.models import AdminIdentity, ApiKey, Policy, Project


def authenticate_api_key(db: Session, plaintext: str | None) -> tuple[ApiKey, Project, Policy]:
    if not plaintext:
        raise err(401, "missing_api_key", "an API key is required", "authentication_error")
    prefix = key_prefix_of(plaintext)
    candidates = (
        db.execute(select(ApiKey).where(ApiKey.key_prefix == prefix, ApiKey.revoked_at.is_(None)))
        .scalars()
        .all()
    )
    key_row = next((k for k in candidates if verify_api_key(plaintext, k.key_hash)), None)
    if key_row is None:
        raise err(
            401, "invalid_api_key", "the provided API key is invalid or revoked", "authentication_error"
        )
    if key_row.expires_at is not None:
        expires = key_row.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        if expires < datetime.now(timezone.utc):
            raise err(401, "expired_api_key", "the provided API key has expired", "authentication_error")
    project = db.get(Project, key_row.project_id)
    if project is None or project.status != "active":
        raise err(403, "project_inactive", "the project for this key is not active", "authentication_error")
    policy = db.execute(select(Policy).where(Policy.project_id == project.id)).scalar_one_or_none()
    if policy is None:
        policy = Policy(project_id=project.id)
        db.add(policy)
        db.commit()
        db.refresh(policy)
    key_row.last_used_at = datetime.now(timezone.utc)
    db.commit()
    return key_row, project, policy


class AdminPrincipal:
    def __init__(self, actor_id: str, role: str, organization_id: str | None):
        self.actor_id = actor_id
        self.role = role
        self.organization_id = organization_id

    def require_write(self) -> None:
        if self.role == "viewer":
            raise err(
                403, "admin_read_only", "viewer identities cannot modify resources", "authentication_error"
            )

    def require_admin(self) -> None:
        if self.role != "admin":
            raise err(403, "admin_required", "this operation requires the admin role", "authentication_error")

    def check_org(self, organization_id: str | None) -> None:
        if self.role == "admin":
            return
        if self.organization_id is None:
            # A non-admin identity with no organization scope must NOT fall
            # through to global access (fail closed).
            raise err(
                403,
                "organization_scope_required",
                "this identity has no organization scope; access denied",
                "authentication_error",
            )
        if organization_id is not None and self.organization_id != organization_id:
            raise err(
                403,
                "cross_tenant_forbidden",
                "identity is scoped to a different organization",
                "authentication_error",
            )


def authenticate_admin(db: Session, token: str | None) -> AdminPrincipal:
    if not token:
        raise err(401, "missing_admin_token", "an admin token is required", "authentication_error")
    if is_bootstrap_admin(token):
        return AdminPrincipal(actor_id="bootstrap-admin", role="admin", organization_id=None)
    prefix = token[:16]
    candidates = (
        db.execute(
            select(AdminIdentity).where(
                AdminIdentity.token_prefix == prefix, AdminIdentity.revoked_at.is_(None)
            )
        )
        .scalars()
        .all()
    )
    for identity in candidates:
        if hash_admin_token(token) == identity.token_hash:
            return AdminPrincipal(
                actor_id=identity.id, role=identity.role, organization_id=identity.organization_id
            )
    raise err(401, "invalid_admin_token", "the provided admin token is invalid", "authentication_error")
