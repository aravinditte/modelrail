# Runbook: Failed evaluation jobs

## Symptoms
Evaluation runs stuck in running/failed, worker logs erroring, or a regression gate failing unexpectedly in CI.

## Diagnosis
Get the run from `/admin/v1/evaluations/{id}`: dataset version, fixtures, config version, per-case failures; check worker health and job deadline; distinguish three cases — infrastructure failure (worker/DB/provider), genuine quality regression (metrics moved), and gate/fixture misconfiguration (degraded fixture expected to fail; good/good expected to pass, spec §13.4). Reproduce locally with `make eval`.

## Mitigation
For infrastructure failure: fix the cause and re-run the same versioned configuration — do not change the dataset to make it pass. For a genuine regression: block the release per the gate; that is the system working. For misconfiguration: fix the gate config and re-run both good/good and good/degraded in CI.

## Recovery
Confirm a clean baseline run reproduces the recorded report for the deterministic mock fixture; record the outcome (regression found vs infrastructure) in the evaluation report notes.

## Related
- Architecture: `docs/architecture/overview.md`
- Operations: `docs/operations.md`
- Metrics and traces: Grafana "ModelRail — Overview" dashboard; request and
  attempt detail via `GET /admin/v1/requests/{id}`.
