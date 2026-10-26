# Runbook: Redis unavailable

## Symptoms
`/health/ready` degraded or rate-limit errors spiking; Redis healthcheck failing; gateway logs showing Redis connection errors.

## Diagnosis
Check the `redis` container/service health and `redis-cli ping`; check memory/eviction and network between gateway and Redis; determine which features are affected: rate-limit counters and transient coordination degrade per ADR-0002 — PostgreSQL-backed budget enforcement continues.

## Mitigation
Restart/repair Redis (data is transient/append-only cache state; losing it must not lose accounting data); if Redis will be down for a while, expect limiter behaviour per policy config and communicate reduced rate-limit fidelity to operators — never compensate by disabling budget checks.

## Recovery
Confirm healthchecks pass and limiter counters resume; verify no budget or usage discrepancies appeared during the outage (run reconciliation); review whether readiness semantics matched operator expectations.

## Related
- Architecture: `docs/architecture/overview.md`
- Operations: `docs/operations.md`
- Metrics and traces: Grafana "ModelRail — Overview" dashboard; request and
  attempt detail via `GET /admin/v1/requests/{id}`.
