# ADR 0008: Structured logging, redaction and retention defaults

## Status
Accepted (initial release).

## Context
Operators need correlatable logs/traces without leaking prompts, completions, API keys or provider credentials (spec §14.3, §16.1, §16.5).

## Decision
Emit structured JSON logs with timestamp, severity, service, request ID, trace ID, attempt ID where relevant, error code, duration and outcome. Never log authorisation headers, plaintext keys, provider secrets, or prompt/completion content by default; PII redaction is an explicit, tested option. Local default retention: application logs via the container runtime (rotate; do not persist prompt content), Tempo traces 72h (see infra/tempo/tempo.yml), Prometheus metrics per local volume. Any change to retention or content logging requires a config change that is visible in review.

## Consequences
Debugging and trace correlation work end-to-end (one request ID across logs, traces, attempts) while the default posture is safe to demo and share. Cost: some production incidents are harder to reconstruct without payloads; mitigated by rich metadata, error classification and attempt timelines.
