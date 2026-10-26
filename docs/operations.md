# ModelRail Operations

## Ports

| Service | Port | Notes |
|---|---|---|
| Gateway | 8000 | Public + admin API, `/health/*`, `/metrics` |
| Dashboard | 3000 | Profile `dashboard` only |
| PostgreSQL | 5432 | Volume `postgres_data` |
| Redis | 6379 | Volume `redis_data` (transient state, AOF) |
| Prometheus | 9090 | Profile `observability` |
| Grafana | 3001 | Profile `observability`; dashboards provisioned from `infra/grafana/` |
| Tempo | 3200 | Profile `observability`; local trace storage, 72h retention |
| OTel Collector | 4317 (gRPC), 4318 (HTTP), 8889 (metrics) | Profile `observability` |

## Startup

```bash
cp .env.example .env   # replace every change-me placeholder
make setup             # build images
make up                # minimal stack: gateway, worker, postgres, redis
curl http://localhost:8000/health/ready
make migrate           # Alembic migrations to head
make seed              # local organisation/project/routes (development only)
```

Optional stacks:

```bash
docker compose --profile dashboard up -d
docker compose -f docker-compose.yml -f docker-compose.observability.yml --profile observability up -d
```

Startup order is enforced by healthchecks: gateway and worker wait for
PostgreSQL and Redis to be healthy.

## Health

- `GET /health/live` — process is alive; performs no dependency checks.
- `GET /health/ready` — dependencies required for the configured role are
  reachable. Optional providers (Ollama, remote) do not fail readiness unless
  the deployment explicitly requires them (spec §14.4).

## Shutdown

```bash
make down        # stop containers, keep volumes
make down V=1    # stop and remove volumes (destroys local data)
```

Graceful shutdown: the gateway stops accepting new requests, in-flight
requests complete or hit their deadline, and reservations left unsettled by a
hard kill are recovered by reconciliation on next start (runbook:
budget-reconciliation).

## Volumes and data

- `postgres_data` — authoritative data; back this up, nothing else matters
  for accounting recovery.
- `redis_data` — transient limiter/coordination state; safe to lose.
- `prometheus_data`, `grafana_data`, `tempo_data` — observability only.

## Troubleshooting

| Symptom | First check | Runbook |
|---|---|---|
| Provider errors / breaker open | Grafana overview, provider health | `docs/runbooks/provider-outage.md` |
| Timeouts, deadline errors | Stage latencies in traces | `docs/runbooks/timeouts.md` |
| Unexpected 429s | Which limit fired, per project | `docs/runbooks/rate-limiting.md` |
| Stuck reservations | Reconciliation report | `docs/runbooks/budget-reconciliation.md` |
| Redis down | `redis-cli ping`, readiness | `docs/runbooks/redis-unavailable.md` |
| Database down | `pg_isready`, volume/disk | `docs/runbooks/database-failure.md` |
| High p95 latency | Gateway vs provider split | `docs/runbooks/high-latency.md` |
| Evaluation jobs failing | Worker logs, run detail | `docs/runbooks/failed-evaluations.md` |
