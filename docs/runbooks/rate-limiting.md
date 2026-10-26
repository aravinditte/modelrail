# Runbook: Unexpected rate limiting

## Symptoms
Clients receiving `429 rate_limit_exceeded` at volumes they believe are within limits, or one project throttling another's traffic.

## Diagnosis
Identify which limit fired (requests/min, tokens/min, concurrency) from the error body and metrics by project; check the project's policy values in `/admin/v1/policies`; check Redis health — limiter behaviour on Redis failure is documented in ADR-0002/redis-unavailable runbook and must not silently become permissive for budget-sensitive limits; look for a retry storm or a leaked key generating the traffic (key `last_used_at`, request volume by key prefix).

## Mitigation
Raise the specific policy limit if the traffic is legitimate; revoke the key if it is leaked/abused; shed load at the client with backoff honouring `Retry-After`.

## Recovery
Confirm rejection rate returns to expected levels for that project only; audit-event review for any policy/key changes made; document the new limits in the project policy.

## Related
- Architecture: `docs/architecture/overview.md`
- Operations: `docs/operations.md`
- Metrics and traces: Grafana "ModelRail — Overview" dashboard; request and
  attempt detail via `GET /admin/v1/requests/{id}`.
