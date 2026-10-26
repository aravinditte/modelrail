# Runbook: Provider outage

## Symptoms
Requests failing with `provider_unavailable`, rising provider error rate and circuit-breaker transitions on the Grafana overview; one provider's attempts failing while others succeed.

## Diagnosis
Filter `/admin/v1/requests` by provider and error code; check the provider's `health_check` result and circuit-breaker state in metrics; check the provider directly (Ollama process/endpoint, remote status page) without changing ModelRail config; confirm the failures are not auth errors (those are non-retryable and indicate credentials, not an outage).

## Mitigation
Let the circuit breaker and fallback policy work: verify fallback routes are eligible and authorised for affected aliases; if the provider is the only route, communicate `no_eligible_route`/provider errors to callers rather than disabling budget or auth checks; optionally disable the route (`PUT /admin/v1/models/{id}`, `enabled=false`) to stop probe traffic.

## Recovery
When the provider recovers, watch half-open probes succeed and the breaker close; re-enable the route if it was disabled; review attempt timelines for the outage window and confirm usage records mark uncertain usage as unknown rather than zero/invented.

## Related
- Architecture: `docs/architecture/overview.md`
- Operations: `docs/operations.md`
- Metrics and traces: Grafana "ModelRail — Overview" dashboard; request and
  attempt detail via `GET /admin/v1/requests/{id}`.
