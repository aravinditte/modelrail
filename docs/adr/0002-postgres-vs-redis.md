# ADR 0002: PostgreSQL is authoritative; Redis is transient only

## Status
Accepted (initial release).

## Context
The platform needs durable accounting (budgets, usage, requests) and fast transient coordination (rate-limit counters, concurrency, caching) (spec §3.2, §11).

## Decision
PostgreSQL owns every record that must survive a crash or be audited: organisations, projects, keys, routes, policies, requests, attempts, usage events, reservations, audit events, evaluations. Redis owns only rebuildable state: rate-limit windows, concurrency counters, short-lived caches. Budget enforcement must never depend solely on Redis — if Redis is unavailable, budget checks fall back to PostgreSQL and rate limiting follows the documented failure behaviour in the rate-limiting runbook.

## Consequences
Accounting correctness does not depend on an in-memory store; a Redis flush loses no money-relevant data. Cost: some limit checks pay a database round-trip on the Redis-down path, and two stores must be operated and health-checked.
