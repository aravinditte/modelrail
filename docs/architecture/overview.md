# ModelRail Architecture Overview

ModelRail is a self-hostable, OpenAI-compatible LLM gateway implemented as a
**modular monolith with separate worker processes** (spec §3, ADR-0001).
PostgreSQL is the authoritative store; Redis holds only transient
coordination state (ADR-0002).

## Context diagram

```mermaid
flowchart LR
    Client[Client applications] -->|OpenAI-compatible API + API key| GW[ModelRail Gateway]
    Admin[Operator / administrator] -->|Admin API + separate admin auth| GW
    Admin --> Dash[Next.js Dashboard]
    Dash -->|Admin API| GW
    GW -->|optional local inference| Ollama[Ollama]
    GW -->|optional, explicitly configured| Remote[OpenAI-compatible remote provider]
    GW --> Mock[Deterministic mock provider]
```

## Component diagram

```mermaid
flowchart TB
    subgraph Gateway["Gateway (FastAPI modular monolith)"]
        Pub[Public API /v1] --> Auth[Auth & tenant resolution]
        Adm[Admin API /admin/v1] --> Auth
        Auth --> Policy[Policy, quotas & rate limits]
        Policy --> Budget[Budget reservations]
        Budget --> Router[Routing engine]
        Router --> Exec[Provider execution: retries, circuit breaker, fallback]
        Exec --> Prov[Provider adapters: mock / Ollama / remote]
        Exec --> Meter[Usage settlement & audit]
    end
    Worker[Evaluation worker] --> DB
    Meter --> DB[(PostgreSQL)]
    Policy --> Redis[(Redis: rate limits, transient coordination)]
    Gateway -->|OTLP| Otel[OTel Collector] --> Tempo[Tempo]
    Gateway -->|/metrics| Prom[Prometheus] --> Graf[Grafana]
```

Boundaries (spec §3.4): the domain layer never depends on FastAPI request
objects; provider adapters implement one shared interface; the router contains
no provider-specific HTTP code; policy enforcement is separate from model
selection; usage accounting is separate from response rendering.

## Request lifecycle

```mermaid
sequenceDiagram
    participant C as Client
    participant G as Gateway
    participant P as Policy/Budget
    participant R as Router
    participant A as Provider adapter
    C->>G: POST /v1/chat/completions (request ID assigned)
    G->>G: Validate schema, payload size, unknown fields
    G->>G: Verify API key hash, resolve organisation + project
    G->>P: Allowlists, rate/concurrency limits
    G->>P: Atomically reserve budget (row lock, Decimal)
    G->>R: Resolve alias, select eligible route by policy
    R->>A: Attempt 1 (attempt ID, same request ID)
    alt Retryable failure and deadline permits
        A-->>R: Classified error
        R->>A: Retry or fallback attempt (new attempt ID)
    end
    A-->>G: Normalised response + usage (or unknown usage)
    G->>P: Settle or flag reservation for reconciliation
    G->>G: Persist request + attempts, emit metrics/logs/traces
    G-->>C: Response or standardised error
```

The request ID is constant across all attempts of one logical request; every
provider attempt has its own attempt ID (spec §3.3).

## Database relationships

```mermaid
erDiagram
    ORGANIZATIONS ||--o{ PROJECTS : owns
    PROJECTS ||--o{ API_KEYS : has
    PROJECTS ||--o{ POLICIES : governed_by
    PROJECTS ||--o{ LOGICAL_REQUESTS : makes
    LOGICAL_REQUESTS ||--o{ PROVIDER_ATTEMPTS : contains
    LOGICAL_REQUESTS ||--o{ USAGE_EVENTS : produces
    PROVIDER_ATTEMPTS ||--o{ USAGE_EVENTS : produces
    PROJECTS ||--o{ BUDGET_RESERVATIONS : holds
    LOGICAL_REQUESTS ||--o| BUDGET_RESERVATIONS : reserved_for
    ORGANIZATIONS ||--o{ AUDIT_EVENTS : records
    EVALUATION_RUNS ||--o{ EVALUATION_RESULTS : contains
```

Tables and fields are specified in spec §12: organisations, projects, API keys
(hash + prefix only, never plaintext), model routes, policies, logical
requests, provider attempts, usage events (unique `event_key`), budget
reservations, audit events, evaluation runs and evaluation results.

## Provider adapter contract

All adapters implement one typed contract (spec §7):

| Method | Responsibility |
|---|---|
| `capabilities()` | Provider identity, configured models, supported modes (streaming, max tokens) |
| `health_check()` | Availability without performing inference |
| `complete(request)` | Non-streaming inference, normalised response + usage |
| `stream(request)` | Streaming inference as normalised events, in order |
| `normalize_usage(response)` | Provider-reported usage preferred; explicit estimate/unknown otherwise |
| `classify_error(error)` | Map to retryable / non-retryable classes (timeout, rate-limit, auth, server, malformed) |
| `close()` | Release HTTP clients/connections safely |

Adapters: **mock** (deterministic, fault-injectable, sufficient for the full
test suite), **Ollama** (local, optional), **remote OpenAI-compatible**
(disabled unless explicitly configured; credentials from environment only;
upstream destinations validated — never taken from client requests).

## Routing decision process

```mermaid
flowchart TD
    A[Model alias requested] --> B{Alias exists & enabled?}
    B -- no --> E1[404 model_not_found]
    B -- yes --> C[Filter routes: tenant allowlist, capability, required output mode, provider health / open circuit]
    C --> D{Any eligible route?}
    D -- no --> E2[503 no_eligible_route]
    D -- yes --> F{Routing policy}
    F -- priority --> G[Highest priority eligible route]
    F -- cost --> H[Lowest estimated cost for estimated tokens, per versioned price schedule]
    F -- latency --> I[Lowest rolling latency, min sample count, cold-start default]
    G & H & I --> J[Record decision: alias, candidates, selected route, policy + config version]
```

Estimated cost is never presented as actual provider billing (spec §8.2).
Latency routing defines a measurement window, minimum samples, exclusion of
unhealthy routes and a configured fallback before history exists (§8.3).
Every decision is auditable without logging prompt content (§8.4).

## Budget reservation lifecycle

```mermaid
stateDiagram-v2
    [*] --> Reserved: atomic reservation (row lock / atomic update)
    Reserved --> Settled: final usage known, settle at actual cost
    Reserved --> Released: request failed before any billable attempt
    Reserved --> ReconciliationNeeded: crash, unknown usage, or settlement failure
    ReconciliationNeeded --> Settled: reconciler settles from recorded usage
    ReconciliationNeeded --> Released: reconciler proves no usage occurred
    Settled --> [*]
    Released --> [*]
```

Rules (spec §10, ADR-0003): conservative reservation amount; hard-budget
rejection if the reservation would exceed the budget; never a check-then-write
sequence without concurrency protection; Decimal arithmetic with pricing
version stored; usage-event ingestion is idempotent via a unique event key, so
retries never double-count; uncertain usage is represented explicitly
(provider-reported / calculated / estimated / simulated / unknown), never
invented.
