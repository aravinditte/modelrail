# ADR 0004: Bounded retries, circuit breakers and policy-gated fallback

## Status
Accepted (initial release).

## Context
Providers fail transiently (timeouts, 429s, 5xx) and persistently (auth, outages). Unbounded retries amplify outages; retrying non-retryable errors wastes the request deadline (spec §9).

## Decision
Retries use exponential backoff with jitter, a maximum attempt count, Retry-After handling, and one overall logical-request deadline that bounds all attempts. Errors are classified; auth, malformed-request and authorisation failures are never retried. Each provider has a circuit breaker (closed/open/half-open with failure threshold, open duration, probe and recovery criteria, and transition metrics). Fallback to another route is allowed only when the destination is authorised, supports the required capabilities, the error class permits it, the deadline permits it, and no streaming content has been emitted.

## Consequences
Failure behaviour is predictable, demonstrable in fault-injection tests (Demos A), and visible in metrics. Cost: more configuration surface (thresholds, windows) that must be documented and given safe defaults.
