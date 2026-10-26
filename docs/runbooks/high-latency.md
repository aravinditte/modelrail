# Runbook: Elevated request latency

## Symptoms
p95 gateway latency above the documented target, user-visible slowness, but error rate roughly normal.

## Diagnosis
Separate gateway overhead from provider latency using traces and the provider-attempt panel (benchmark-methodology.md defines the measurement); check per-stage spans (auth, budget, routing); check PostgreSQL (slow queries, lock waits on the budget row), Redis latency, and host CPU/memory; check whether latency-aware routing has enough samples or is pinned to one route.

## Mitigation
Remove the bottleneck actually measured: add/adjust indexes via migration if a query is at fault, reduce retries if they inflate tail latency, rebalance route priorities, or scale the gateway process. Do not claim improvement without re-measuring.

## Recovery
Re-run the k6 profile from benchmarks/ and record measured results in benchmarks/results with environment details; confirm dashboard p95 returns to baseline.

## Related
- Architecture: `docs/architecture/overview.md`
- Operations: `docs/operations.md`
- Metrics and traces: Grafana "ModelRail — Overview" dashboard; request and
  attempt detail via `GET /admin/v1/requests/{id}`.
