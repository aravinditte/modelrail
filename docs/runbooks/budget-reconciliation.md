# Runbook: Budget reconciliation failures

## Symptoms
Reservations stuck in reconciliation-needed state, reconciliation job reporting discrepancies, or project spend not matching usage totals.

## Diagnosis
Run/inspect the reconciliation job output: stale reservations, incomplete settlements, duplicate usage records, unknown-usage requests; compare usage-event totals (by unique `event_key`) with settled reservation amounts per project; check for gateway/worker crashes during settlement in logs (request IDs correlate).

## Mitigation
Do not edit balances by hand and do not invent usage: settle from recorded provider-reported usage where it exists; release reservations the reconciler proves had no billable attempt; leave genuinely unknown usage flagged as unknown and visible in the usage view.

## Recovery
Re-run reconciliation until it reports clean (or only explicitly-flagged unknowns remain); verify a sample of requests end-to-end (request → attempts → usage events → reservation); record the incident and any code fix — crash-during-settlement is a covered resilience test (spec §17.5).

## Related
- Architecture: `docs/architecture/overview.md`
- Operations: `docs/operations.md`
- Metrics and traces: Grafana "ModelRail — Overview" dashboard; request and
  attempt detail via `GET /admin/v1/requests/{id}`.
