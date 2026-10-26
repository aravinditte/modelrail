# ADR 0001: Modular monolith over microservices

## Status
Accepted (initial release).

## Context
ModelRail needs gateway, auth, routing, metering and admin APIs plus an evaluation worker, built and operated by a small team, local-first (spec §3.1, §2.2).

## Decision
Implement one FastAPI backend application with strict internal module boundaries (api / core / domain / providers / services / db / telemetry), plus two separate processes: the evaluation worker and the Next.js dashboard. PostgreSQL is shared authoritative state.

## Consequences
Local development and Docker Compose stay simple; domain logic is testable without a network of services; module boundaries preserve a later extraction path for the worker or provider execution. Cost: scaling is per-process rather than per-service, and boundary discipline must be enforced in review and tests rather than by deployment topology.
