# ADR 0003: Budget concurrency: atomic reservation under row lock

## Status
Accepted (initial release).

## Context
Concurrent requests from one project must never collectively over-allocate the project budget (spec §1.2, §10.2). An application-level check-then-write sequence has a race window.

## Decision
Reserve budget inside a PostgreSQL transaction using an atomic conditional update / SELECT ... FOR UPDATE on the project budget row, with Decimal amounts. The reservation records reserved vs settled amounts and a reconciliation status. Settlement is idempotent; a reservation cannot be settled twice (property-tested, spec §17.6). Stale or crash-interrupted reservations are recovered by the reconciliation job, never silently dropped.

## Consequences
Over-allocation is prevented by the database, not by timing luck, and the invariant is directly testable under concurrency. Cost: the budget row is a contention point for a single very hot project; accepted for correctness at portfolio scale and documented as a scaling limit.
