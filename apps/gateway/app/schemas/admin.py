"""Administrative API schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ModelRouteIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    alias: str = Field(min_length=1, max_length=120)
    provider: str = Field(min_length=1, max_length=60)
    upstream_model: str = Field(min_length=1, max_length=200)
    priority: int = 100
    capabilities: dict = Field(default_factory=lambda: {"streaming": True})
    enabled: bool = True
    configuration: dict = Field(default_factory=dict)
    input_price_per_token: float = 0.0
    output_price_per_token: float = 0.0
    pricing_version: str = "price-v1"


class ModelRouteUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    alias: str | None = None
    provider: str | None = None
    upstream_model: str | None = None
    priority: int | None = None
    capabilities: dict | None = None
    enabled: bool | None = None
    configuration: dict | None = None
    input_price_per_token: float | None = None
    output_price_per_token: float | None = None
    pricing_version: str | None = None


class ProjectIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=200)
    organization_id: str | None = None
    organization_name: str | None = None


class KeyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str
    name: str = "default"
    expires_at: datetime | None = None


class PolicyIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    project_id: str
    allowed_models: list[str] = Field(default_factory=lambda: ["*"])
    requests_per_minute: int = 600
    tokens_per_minute: int = 1_000_000
    max_concurrency: int = 32
    max_output_tokens: int = 4096
    budget_limit: float | None = None
    routing_policy: str = Field(default="priority", pattern="^(priority|cost|latency)$")


class PolicyUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    allowed_models: list[str] | None = None
    requests_per_minute: int | None = None
    tokens_per_minute: int | None = None
    max_concurrency: int | None = None
    max_output_tokens: int | None = None
    budget_limit: float | None = None
    routing_policy: str | None = Field(default=None, pattern="^(priority|cost|latency)$")


class EvaluationIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dataset_version: str = "modelrail-eval-v1"
    candidate_model: str = "mock-good"
    baseline_model: str = "mock-good"
    configuration_version: str = "cfg-v1"
    run_async: bool = False


class AdminIdentityIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=120)
    role: str = Field(default="viewer", pattern="^(admin|project_admin|viewer)$")
    organization_id: str | None = None
