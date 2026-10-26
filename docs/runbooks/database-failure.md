# Runbook: Database connectivity failure

## Symptoms
`/health/ready` failing, `500`s on authenticated endpoints, gateway/worker logs with PostgreSQL connection errors. The gateway must fail closed: no inference without auth, policy and budget records.

## Diagnosis
Check the `postgres` container and `pg_isready`; check disk/volume health (`postgres_data`), connection counts and long transactions; check whether a migration is mid-flight; verify credentials in `.env` match the database (without printing secrets into tickets/logs).

## Mitigation
Restore PostgreSQL first; only then restart gateway/worker if their pools do not recover; if restoring from backup, note the point-in-time — requests/usage after that point are lost and must be declared, not reconstructed from logs.

## Recovery
Run migrations to head if needed; run budget reconciliation (crash-interrupted settlements are expected after a DB outage); verify health, a mock-provider request, and usage persistence end-to-end before declaring recovery.

## Related
- Architecture: `docs/architecture/overview.md`
- Operations: `docs/operations.md`
- Metrics and traces: Grafana "ModelRail — Overview" dashboard; request and
  attempt detail via `GET /admin/v1/requests/{id}`.
