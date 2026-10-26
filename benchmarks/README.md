# Benchmarks

Load tests for ModelRail. **Methodology:** `docs/benchmark-methodology.md`.
**Script:** `k6-gateway.js` (25 rps / 50 VU / 5 min profile against the
deterministic mock provider; p95 gateway-overhead target of 150 ms is a
target to test, per spec §17.7).

## Measured Results

Each row corresponds to an independently documented benchmark report in `docs/benchmark-results/`, detailing the hardware profile, runtime, commit, database configuration, offer profile, and limitations.

| Date | Commit | Environment | Offer Profile | Measured Throughput | p50 | p95 | Error Rate | Report Link |
|---|---|---|---|---|---|---|---|---|
| 2026-10-26 | `5346775` | Local VM, Python 3.12, SQLite WAL, Mock 0ms | 25 req/s x 60s (1500 reqs, max 50 concurrent) | 25 req/s (1500/1500) | 15.1 ms | 30.5 ms | 0.0% | [2026-10-26-local-vm.md](../docs/benchmark-results/2026-10-26-local-vm.md) |

Do not enter target numbers in this table. Only measured runs belong here.
