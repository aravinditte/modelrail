# ADR 0007: Evaluation metrics are task-specific, with regression gates

## Status
Accepted (initial release).

## Context
A single string-equality score cannot judge extraction, instruction-following, classification and refusal behaviour, and unversioned evaluations cannot be reproduced (spec §13).

## Decision
Use task-specific deterministic metrics: JSON schema validity + field-level match + required-field completeness for extraction; constraint satisfaction and schema compliance for instruction-following; accuracy/precision/recall/macro-F1 for classification; expected-refusal and disclosure checks for safety cases; plus success/error rate, p50/p95 latency, tokens and estimated cost for every run. Dataset, cases, prompts, provider/model, evaluation code, metric definitions and pricing are all versioned and recorded on every report. Release gates compare candidate vs baseline against configurable thresholds; a deliberately degraded fixture must fail the gate in CI.

## Consequences
Quality claims become reproducible and regressions can block a release (Demo C). Cost: maintaining 100+ versioned cases and metric implementations is ongoing work, and automated safety metrics are labelled as risk reduction, not proof (spec §16.5).
