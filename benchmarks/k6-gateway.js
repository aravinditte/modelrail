// ModelRail — k6 load test for the gateway (spec §17.7).
// Profile: ramp to 50 VUs, 5 minutes sustained, ~25 req/s at the mock
// provider's configured latency (pace with sleep / arrival-rate executors
// in your environment if you need an exact rate).
// This script measures; it asserts no results. Thresholds below encode the
// *initial target profile* from the spec — a failed threshold is a result
// to publish honestly, not a script bug.
// Usage:
//   MODELRAIL_API_KEY=<key> k6 run benchmarks/k6-gateway.js
//   Optional env: BASE_URL (default http://localhost:8000),
//                 MODEL_ALIAS (default mock-fast)
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate, Trend } from 'k6/metrics';

const errorRate = new Rate('modelrail_error_rate');
const gatewayLatency = new Trend('modelrail_request_duration', true);

export const options = {
  stages: [
    { duration: '1m', target: 50 },  // ramp to 50 concurrent clients
    { duration: '5m', target: 50 },  // sustained load
    { duration: '1m', target: 0 },   // ramp down
  ],
  thresholds: {
    // Target profile only (spec §17.7): report actuals either way.
    http_req_failed: ['rate<0.01'],
    http_req_duration: ['p(95)<500'], // includes mock latency; see methodology
  },
};

const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const MODEL_ALIAS = __ENV.MODEL_ALIAS || 'mock-fast';
const API_KEY = __ENV.MODELRAIL_API_KEY || '';

export default function () {
  const payload = JSON.stringify({
    model: MODEL_ALIAS,
    messages: [{ role: 'user', content: 'Benchmark ping: reply with ok.' }],
    max_tokens: 16,
  });
  const res = http.post(`${BASE_URL}/v1/chat/completions`, payload, {
    headers: {
      'Content-Type': 'application/json',
      Authorization: `Bearer ${API_KEY}`,
    },
    tags: { name: 'chat_completions' },
  });
  const ok = check(res, { 'status is 200': (r) => r.status === 200 });
  errorRate.add(!ok);
  gatewayLatency.add(res.timings.duration);
  sleep(1); // pacing: with 50 VUs this approximates the 25 rps profile when
            // mean latency is ~1s; adjust to your measured latency and
            // record the achieved rate — do not assume it.
}

export function handleSummary(data) {
  return {
    stdout: JSON.stringify(
      {
        note: 'Record these measured values in benchmarks/README.md with the full environment template. Do not publish targets as results.',
        http_req_duration_p95: data.metrics.http_req_duration?.values?.['p(95)'],
        http_req_duration_p50: data.metrics.http_req_duration?.values?.['p(50)'],
        http_reqs: data.metrics.http_reqs?.values?.count,
        error_rate: data.metrics.modelrail_error_rate?.values?.rate,
      },
      null,
      2,
    ),
  };
}
