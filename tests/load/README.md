# Load Testing

This directory provides automated load tests and test profiles for ModelRail (spec §5, §17.7).

## Specification Targets (§17.7)

- **Throughput target:** 25 requests per second
- **Concurrency target:** 50 concurrent clients
- **Profile duration:** 5 minutes sustained load
- **Latency target:** p95 gateway overhead < 150 ms (measured against 0 ms mock provider)
- **Honesty requirement:** targets are tested and published honestly, never claimed without measurement.

## Test Artifacts

1. **`test_load.py`:** Automated pytest suite exercising the gateway under concurrent load (multi-threaded/async request bursts) against the deterministic mock provider. Asserts response status, latency thresholds, and accounting consistency.
2. **`benchmarks/k6-gateway.js`:** The full 5-minute sustained k6 load test script.
3. **`docs/benchmark-methodology.md`:** Detailed benchmark methodology, hardware profiles, and reporting templates.
4. **`docs/benchmark-results/`:** Version-controlled published benchmark run reports.
