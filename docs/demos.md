# ModelRail demonstrations

Three reproducible demos (spec section 22). All use the deterministic mock
provider — no paid APIs, no external services. Start from a seeded local
instance:

```bash
cp .env.example .env
docker compose up --build -d        # or the local-Python quick start in the README
docker compose exec gateway python -m app.seed    # note the API key it prints
export KEY=<the printed key>
export ADMIN="X-Admin-Token: <your ADMIN_TOKEN from .env>"
```

The seeded aliases are `modelrail-fast` (mock primary → Ollama fallback),
`modelrail-resilient` (mock primary → mock-secondary fallback) and
`modelrail-flex` (two mocks at different prices, for cost routing).

## Demo A: Provider failure and recovery

1. Send a normal request and confirm success:
   `curl -s localhost:8000/v1/chat/completions -H "Authorization: Bearer $KEY" -H 'Content-Type: application/json' -d '{"model":"modelrail-resilient","messages":[{"role":"user","content":"echo: healthy"}]}'`
2. Inject a primary outage: change the content to
   `"[fail:primary=outage] echo: still works"`. The response still succeeds —
   `modelrail.provider` is `mock-secondary` and `modelrail.fallback_reason`
   is `connection:mock`.
3. Open the request in the dashboard (Requests page) or
   `GET /admin/v1/requests/<request_id>`: the attempt timeline shows the
   failed primary attempt and the successful fallback attempt under **one**
   request ID.
4. Repeat the failing request against a single-route alias several times
   (test threshold: 3 in the test config; default 5) and watch the circuit
   breaker open: subsequent requests fail fast with no new provider attempt.
   `/metrics` shows `modelrail_circuit_transitions_total` increasing.
5. Duplicate-usage protection: re-send any successful request with the same
   `Idempotency-Key` header — the same response is replayed and the usage
   total (Usage page) does not change.

Automated equivalents: `tests/resilience/` (100 injected-failure scenarios,
circuit breaker, streaming fallback rules).

## Demo B: Tenant budget enforcement

1. In the dashboard (Projects), create two projects, one API key each, and
   set a small budget (e.g. 0.0005) on the first project's policy.
2. Send concurrent requests with the first project's key (the seeded data and
   `tests/concurrency/` do this with 8 threads): reservations are atomic, so
   committed spend never exceeds the budget; excess requests receive
   `429 budget_exceeded`.
3. The second project's key keeps working — budgets are per-project.
4. On the Usage page, inspect reservations: settled amounts come from
   recorded usage; the failed requests' reservations sit in
   `reconciliation_needed` until `POST /admin/v1/reconcile` resolves them
   (from recorded usage, or released with the request flagged as
   unknown-usage — never with invented numbers).

Automated equivalents: `tests/concurrency/test_concurrency.py`,
`tests/integration/test_api.py::test_chat_records_request_attempt_usage_and_settles_budget`.

## Demo C: LLM quality regression gate

1. Run the baseline: `make eval` (good scripted configuration) and save the
   report.
2. Run the candidate with the deliberately degraded configuration:
   `python -m modelrail_evals.runner --dataset packages/evals/datasets/modelrail-eval-v1.jsonl --mode degraded --out /tmp/candidate.json`
   (PYTHONPATH=packages/evals).
3. Compare: `python -m modelrail_evals.gate --baseline <good.json> --candidate /tmp/candidate.json`
   exits **1** and names the breached thresholds (structured validity,
   macro-F1, instruction pass rate, safety, disclosure).
4. Via the API instead: `POST /admin/v1/evaluations` with
   `{"candidate_model": "mock-degraded", "baseline_model": "mock-good"}` —
   the dashboard Evaluations page shows the same gate failure; with
   `mock-good` as candidate it passes.
5. In CI, the `eval-gate` job runs exactly these comparisons on every push.

Automated equivalents: `tests/evals/` and
`tests/integration/test_api.py::test_admin_evaluation_good_vs_degraded_gate`.
