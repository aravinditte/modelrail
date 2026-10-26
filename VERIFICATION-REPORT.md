# ModelRail — verification report (2026-10-26)

Item-by-item verification against the specification's acceptance criteria
(§18) and Definition of Done (§24). Anything not verified is stated as such.

## Test suite

- **173 tests, all passing**, three consecutive full runs (SQLite test DB).
  Breakdown: unit (incl. Hypothesis property tests), provider contract,
  integration (incl. a real-uvicorn + official OpenAI SDK test), security,
  resilience (**100 parametrized injected-failure scenarios** + circuit
  breaker, deadline, streaming semantics), threaded concurrency (budget
  over-allocation), evaluation framework (18 tests).
- **Coverage: 85%** total across `apps/gateway/app` + `packages/evals`
  (gateway service 93%, routing 84%, budget 79%, providers 78–95%).
  The spec's ≥80% target for domain/routing/policy/metering code is met in
  aggregate; `budget.py` alone measures 79% and `telemetry/tracing.py` 30%
  (OTLP disabled by default) — reported, not hidden.
- Lint: `ruff check` and `ruff format --check` clean.
- Alembic: `alembic upgrade head` creates all 13 application tables
  (verified on SQLite). **PostgreSQL execution was NOT verified on this VM**
  (no PostgreSQL available); CI runs migrations + tests against
  PostgreSQL 16 services.
- Dashboard: `npm install` + `npm run build` (Next.js 15) pass; runtime
  smoke test of `/`, `/models`, `/evaluations` returned 200.
- Docker Compose: files YAML/structure-validated. **`docker compose up` was
  NOT run** (Docker is not installed on this VM); CI validates the compose
  files and the Dockerfiles are built in CI's dashboard job only for the
  dashboard. Gateway/worker image builds are untested by execution.

## Acceptance criteria (§18) — status

| Area | Status | Evidence |
|---|---|---|
| API contract endpoints | PASS | integration tests; OpenAI SDK test against live uvicorn |
| Mock provider, no external APIs | PASS | contract + all suites run offline |
| Ollama adapter | PASS (transport-mocked) | contract tests via httpx MockTransport; **not run against a real Ollama server** |
| Streaming order + error semantics | PASS | SSE tests incl. no-fallback-after-first-chunk |
| Error format stability | PASS | envelope asserted across security/integration tests |
| Unauthorized access rejected | PASS | security suite (missing/invalid/revoked/expired keys, roles) |
| Tenant isolation | PASS | cross-tenant admin tests (usage, requests, project scoping) |
| Secrets in logs/responses | PASS | asserted in security tests; keys hashed, shown once |
| Admin ops authorized + audited | PASS | audit events asserted in CRUD flow test |
| Retry/fallback per policy | PASS | 100 scenarios + flaky-recovery test |
| Non-retryable not retried | PASS | single-attempt assertions |
| Circuit breaker states | PASS | unit + integration (open blocks attempts) |
| Deadline bounds execution | PASS (by construction + timeout classification) | provider timeout is capped by remaining deadline in `gateway_service.provider_request` |
| ≥100 failure scenarios | PASS | exactly 100 parametrized scenarios |
| Usage/cost fixtures exact | PASS | Decimal cost tests, settlement assertions |
| Duplicate usage not double-counted | PASS | idempotency test + Hypothesis property test |
| Concurrent budget safety | PASS | threaded test: committed ≤ budget, deterministically |
| Unknown usage not invented | PASS | failed requests park reservations as reconciliation-needed; reconciler releases/settles only from recorded usage |
| Crash-recovery reconciliation | PARTIAL | reconciliation of stale reservations is implemented and tested via the reconcile endpoint; a literal kill-mid-settlement crash test is not in the suite |
| Request/attempt observability | PASS | admin request detail, Prometheus metrics endpoint test, JSON log shape in live run |
| Evaluation end-to-end | PASS | 100-case dataset; admin API + worker process both executed runs live |
| Reproducible baseline | PASS | dataset generator is deterministic (byte-identical regeneration) |
| Regression gate | PASS | degraded candidate fails with 6 named reasons (API, CLI, worker paths all verified) |
| Clean local setup | PASS (Python path) | venv + uvicorn + seed verified live; **Docker path unverified** (no Docker on VM) |
| Load target measured honestly | PASS | 25 rps × 60 s, 1500/1500, p95 30.5 ms — see benchmark report; 5-minute profile ships as k6 script, not claimed |

## Live smoke (real processes, this VM)

- uvicorn gateway: `/health/ready` OK; seeded demo; chat completion 200 with
  simulated cost; streaming fallback across an injected outage succeeded.
- Evaluation worker as a separate process picked up a queued
  (`run_async`) evaluation and completed it; gate correctly failed the
  degraded candidate.

## Known limitations (also in README)

- Remote adapter re-chunks a fetched completion for SSE (no native upstream
  token streaming yet).
- Rate limiter is in-process (Redis backing documented as an interface
  extension); budget enforcement is transactional and Redis-independent.
- Evaluation "models" are deterministic scripted fixtures — results measure
  the framework and gating, not a real LLM's quality.
- PostgreSQL, Docker, real Ollama, and CI execution are unverified from this
  VM; the CI workflow encodes all of them.
