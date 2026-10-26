"""Prometheus metrics (spec 14.1). Label sets are bounded: provider, model
alias, status, error class — never request IDs, prompts or keys."""

from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

REQUESTS = Counter("modelrail_logical_requests_total", "Logical requests", ["status", "model_alias"])
ATTEMPTS = Counter("modelrail_provider_attempts_total", "Provider attempts", ["provider", "status"])
PROVIDER_ERRORS = Counter(
    "modelrail_provider_errors_total", "Provider errors by class", ["provider", "error_class"]
)
REQUEST_LATENCY = Histogram(
    "modelrail_request_latency_seconds",
    "Logical request latency",
    ["model_alias"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)
PROVIDER_LATENCY = Histogram(
    "modelrail_provider_latency_seconds",
    "Provider attempt latency",
    ["provider"],
    buckets=(0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10),
)
RETRIES = Counter("modelrail_retries_total", "Retries", ["provider"])
FALLBACKS = Counter("modelrail_fallbacks_total", "Fallbacks", ["from_provider", "to_provider"])
CIRCUIT_TRANSITIONS = Counter(
    "modelrail_circuit_transitions_total", "Circuit breaker transitions", ["provider"]
)
TOKENS = Counter("modelrail_tokens_total", "Tokens", ["direction", "model_alias"])
COST = Counter("modelrail_estimated_cost_total", "Estimated cost (USD)", ["model_alias"])
RATE_LIMIT_REJECTIONS = Counter("modelrail_rate_limit_rejections_total", "Rate limit rejections", ["kind"])
BUDGET_REJECTIONS = Counter("modelrail_budget_rejections_total", "Budget rejections")
IN_PROGRESS = Gauge("modelrail_in_progress_requests", "In-progress logical requests")
EVAL_RUNS = Counter("modelrail_evaluation_runs_total", "Evaluation runs", ["status"])
EVAL_DURATION = Histogram(
    "modelrail_evaluation_duration_seconds", "Evaluation duration", buckets=(0.1, 0.5, 1, 5, 10, 30, 60)
)
