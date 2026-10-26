# ModelRail — Local-First LLM Gateway & AI Reliability Platform (Landing Page)

A multi-section, production-oriented landing page for **ModelRail**, built in a "Quant Brutalist Editorial" design language — stark black-ink-on-ivory (`#111114` ink, `#F3F1EA` ivory, `#FBFAF6` paper) with an electric cobalt accent (`#1F44FF`). Punctuated with hairline rules, section indices `(01)`–`(08)`, monospace meta labels, and oversized Space Grotesk display typography across an engineered editorial grid.

## Key Features

- **Hero & Live Telemetry Card:** Canvas particle mesh with drifting route nodes, real-time SVG latency sparkline, rotating gateway metrics (`0.00%` duplicate retried tokens, `<24.8ms` P95 overhead, `3-State` circuit breakers).
- **Marquee Ticker Strip:** Real-time stream of ModelRail gateway metrics, route states, budget commits, and CI eval gates.
- **Architectural Thesis & Method Grid:** The 4 distributed systems invariants (Intercept & Authorize, Dynamic Policy Routing, Resilient Execution, Settle & Benchmark).
- **Platform Capabilities Accordion:** 4 deep expandable systems covering multi-provider routing (Priority, Cost-Aware, Latency-Aware), two-phase budget reservations, circuit breakers with jitter, and CI evaluation gates.
- **Verified Benchmarks Band:** Count-up metrics highlighting `< 24.8ms` P95 overhead, `183+` passing automated tests, `0.00%` duplicate tokens on retries, and `100%` local-first reproducibility.
- **Deployment Architecture Tiers:** Interactive interactive toggles for Local Edge (Mock / Ollama), Production Compose (Core / Full), and Reliability & Evals (Dev / Held-Out).
- **Empirical Invariant Proofs (Case Files):** Dynamic SVG charts demonstrating circuit breaker fault injection failover and high-concurrency budget race protection.
- **Interactive Developer Quickstart & Gateway Simulator:** Drop-in tabbed request terminal for cURL (Linux/macOS), PowerShell `curl.exe` (escaped), PowerShell `Invoke-RestMethod`, and Python OpenAI SDK, alongside an interactive 5-step lifecycle simulator.
- **Architectural FAQ:** Technical explanations of two-phase budget reservation math, zero-cloud execution, retry accounting, and CI regression gating.
- **100% Self-Contained & Local:** Zero remote font or CDN dependencies (Space Grotesk, Inter, and JetBrains Mono vendored locally as WOFF2).

## Run Locally

Open `index.html` directly in any modern browser, or serve statically with Python:

```sh
python -m http.server 8080 --directory "landing page"
```

Then visit: [http://localhost:8080](http://localhost:8080)
