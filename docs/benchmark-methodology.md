# Benchmark Methodology

> **Honesty rule (spec §17.7, §18, §21): results must be measured. This
> document defines how to measure and provides an empty results template.
> It contains no performance results, and no target below is a claim that
> ModelRail achieves it.**

## What is measured

- **Gateway overhead** = end-to-end latency at the gateway **minus** provider
  latency for the same requests, using the deterministic mock provider with a
  configured fixed latency, so inference time does not pollute the overhead
  figure.
- Throughput, error rate, p50 / p95 / p99 latency (client-observed, k6).
- Host CPU and memory, and database behaviour, observed during the run
  (Grafana/Prometheus, `docker stats`).

## Load profile (initial target profile, spec §17.7)

| Parameter | Value |
|---|---|
| Tool | k6, script `benchmarks/k6-gateway.js` |
| Target request rate | 25 requests/second |
| Concurrent clients | 50 virtual users |
| Duration | 5 minutes sustained (plus ramp) |
| Provider | Deterministic mock provider (fixed configured latency — record it) |
| Initial performance target (to test, not a claim) | p95 gateway overhead below 150 ms |

## How to run

```bash
make up && make migrate && make seed
# Create a project API key via the admin API/dashboard, then:
MODELRAIL_API_KEY=<key> k6 run benchmarks/k6-gateway.js
# Variants: BASE_URL, MODEL_ALIAS, MOCK_LATENCY_MS via -e / environment.
```

Run on a quiet host, note background load, run at least twice, and report the
run you publish in full — do not cherry-pick the better run without saying so.

## Recording a result (template — copy into benchmarks/README.md)

| Field | Value |
|---|---|
| Date | |
| Git commit | |
| Hardware (CPU / RAM) | |
| OS / Docker version | |
| Services and versions (gateway, PostgreSQL, Redis) | |
| Mock provider configured latency | |
| k6 version and exact command | |
| Achieved throughput (req/s) | _measured_ |
| Error rate | _measured_ |
| Client p50 / p95 / p99 | _measured_ |
| Gateway overhead p95 (client p95 minus mock latency, cross-checked with trace stage timings) | _measured_ |
| CPU / memory notes | _measured_ |
| Known limitations of this run | |

## Known limitations of the method

- Mock-provider results say nothing about real provider latency or quality.
- A single-host Compose run shares CPU between client (k6), gateway and
  databases; absolute numbers do not transfer to other hardware.
- p95 overhead computed by subtraction is an approximation; trace stage
  timings are the cross-check.
