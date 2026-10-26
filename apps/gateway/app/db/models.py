"""Authoritative persistent schema (spec section 12).

PostgreSQL is the production store; SQLite is used for local tests/demos via
the same models. Money is always Decimal (Numeric), never float.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_id() -> str:
    return str(uuid.uuid4())


class Base(DeclarativeBase):
    pass


class Organization(Base):
    __tablename__ = "organizations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(32), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    projects: Mapped[list["Project"]] = relationship(back_populates="organization")


class Project(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(ForeignKey("organizations.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(32), default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    organization: Mapped[Organization] = relationship(back_populates="projects")


class ApiKey(Base):
    __tablename__ = "api_keys"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    name: Mapped[str] = mapped_column(String(120), default="default")
    key_prefix: Mapped[str] = mapped_column(String(24), index=True)
    key_hash: Mapped[str] = mapped_column(String(64), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AdminIdentity(Base):
    __tablename__ = "admin_identities"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120))
    token_prefix: Mapped[str] = mapped_column(String(24), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    role: Mapped[str] = mapped_column(String(32), default="viewer")  # admin | project_admin | viewer
    organization_id: Mapped[str | None] = mapped_column(ForeignKey("organizations.id"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ModelRoute(Base):
    __tablename__ = "model_routes"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    alias: Mapped[str] = mapped_column(String(120), index=True)
    provider: Mapped[str] = mapped_column(String(60))
    upstream_model: Mapped[str] = mapped_column(String(200))
    priority: Mapped[int] = mapped_column(Integer, default=100)
    capabilities: Mapped[dict] = mapped_column(JSON, default=dict)  # {streaming: bool, max_context: int}
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    configuration_version: Mapped[int] = mapped_column(Integer, default=1)
    configuration: Mapped[dict] = mapped_column(
        JSON, default=dict
    )  # provider-specific (fail_key, latency_ms...)
    input_price_per_token: Mapped[Decimal] = mapped_column(Numeric(18, 10), default=Decimal(0))
    output_price_per_token: Mapped[Decimal] = mapped_column(Numeric(18, 10), default=Decimal(0))
    pricing_version: Mapped[str] = mapped_column(String(32), default="price-v1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Policy(Base):
    __tablename__ = "policies"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    allowed_models: Mapped[list] = mapped_column(JSON, default=lambda: ["*"])
    requests_per_minute: Mapped[int] = mapped_column(Integer, default=600)
    tokens_per_minute: Mapped[int] = mapped_column(Integer, default=1_000_000)
    max_concurrency: Mapped[int] = mapped_column(Integer, default=32)
    max_output_tokens: Mapped[int] = mapped_column(Integer, default=4096)
    budget_limit: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)  # None = unlimited
    routing_policy: Mapped[str] = mapped_column(String(32), default="priority")  # priority|cost|latency
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class LogicalRequest(Base):
    __tablename__ = "logical_requests"
    __table_args__ = (UniqueConstraint("project_id", "idempotency_key", name="uq_req_idem"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)  # the request_id
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    idempotency_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    model_alias: Mapped[str] = mapped_column(String(120))
    status: Mapped[str] = mapped_column(String(32), default="running")  # succeeded|failed
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    request_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    total_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_attempts: Mapped[int] = mapped_column(Integer, default=0)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    final_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    cost_basis: Mapped[str | None] = mapped_column(
        String(32), nullable=True
    )  # provider_reported|estimated|simulated|unknown
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    routing_policy: Mapped[str | None] = mapped_column(String(32), nullable=True)
    selected_provider: Mapped[str | None] = mapped_column(String(60), nullable=True)
    selected_upstream_model: Mapped[str | None] = mapped_column(String(200), nullable=True)
    fallback_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    route_decision: Mapped[dict] = mapped_column(JSON, default=dict)
    response_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # for idempotent replay


class ProviderAttempt(Base):
    __tablename__ = "provider_attempts"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    request_id: Mapped[str] = mapped_column(ForeignKey("logical_requests.id"), index=True)
    provider: Mapped[str] = mapped_column(String(60))
    upstream_model: Mapped[str] = mapped_column(String(200))
    attempt_number: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(32))  # succeeded|failed
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    cost_basis: Mapped[str | None] = mapped_column(String(32), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    fallback_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)


class UsageEvent(Base):
    __tablename__ = "usage_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    event_key: Mapped[str] = mapped_column(String(200), unique=True, index=True)  # idempotency scope
    request_id: Mapped[str] = mapped_column(String(36), index=True)
    attempt_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost: Mapped[Decimal] = mapped_column(Numeric(18, 8), default=Decimal(0))
    currency_or_unit: Mapped[str] = mapped_column(String(16), default="USD")
    usage_source: Mapped[str] = mapped_column(
        String(32), default="estimated"
    )  # provider_reported|calculated|estimated|simulated|unknown
    pricing_version: Mapped[str] = mapped_column(String(32), default="price-v1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BudgetReservation(Base):
    __tablename__ = "budget_reservations"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    request_id: Mapped[str] = mapped_column(String(36), index=True)
    reserved_amount: Mapped[Decimal] = mapped_column(Numeric(18, 8), default=Decimal(0))
    settled_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), default="reserved"
    )  # reserved|settled|released|reconciliation_needed
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    settled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reconciliation_status: Mapped[str] = mapped_column(String(32), default="not_needed")


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    actor_id: Mapped[str] = mapped_column(String(120), default="unknown")
    action: Mapped[str] = mapped_column(String(120))
    resource_type: Mapped[str] = mapped_column(String(60))
    resource_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    event_metadata: Mapped[dict] = mapped_column("metadata", JSON, default=dict)


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    dataset_version: Mapped[str] = mapped_column(String(64), default="modelrail-eval-v1")
    candidate_model: Mapped[str] = mapped_column(String(120), default="mock-good")
    baseline_model: Mapped[str] = mapped_column(String(120), default="mock-good")
    configuration_version: Mapped[str] = mapped_column(String(64), default="cfg-v1")
    status: Mapped[str] = mapped_column(String(32), default="pending")  # pending|running|completed|failed
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    summary: Mapped[dict] = mapped_column(JSON, default=dict)


class EvaluationResult(Base):
    __tablename__ = "evaluation_results"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    run_id: Mapped[str] = mapped_column(ForeignKey("evaluation_runs.id"), index=True)
    case_id: Mapped[str] = mapped_column(String(64))
    metric_values: Mapped[dict] = mapped_column(JSON, default=dict)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="passed")
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
