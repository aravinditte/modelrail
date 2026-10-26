# Runbook: Repeated timeouts

## Symptoms
`provider_timeout`/`deadline_exceeded` errors, p95 provider latency climbing, retries consuming the overall request deadline.

## Diagnosis
Break latency down by stage in traces (auth, policy, budget, provider attempt); check mock/Ollama/remote latency separately — gateway overhead vs inference latency (benchmark methodology); look for retry amplification (attempts per logical request); check provider host load and network path.

## Mitigation
Confirm timeout configuration is coherent: connect < request < overall deadline (`.env` values); reduce `RETRY_MAX_ATTEMPTS` for the affected policy if retries are exhausting deadlines; route latency-aware policies away from the slow route or lower its priority.

## Recovery
Verify p95 and timeout rate return to baseline on the dashboard; if a config change was made, note the config version on the affected routes; add/adjust alerts if detection was slow.

## Related
- Architecture: `docs/architecture/overview.md`
- Operations: `docs/operations.md`
- Metrics and traces: Grafana "ModelRail — Overview" dashboard; request and
  attempt detail via `GET /admin/v1/requests/{id}`.
