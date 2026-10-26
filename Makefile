# ModelRail — developer commands (spec §4.6, §20).
COMPOSE ?= docker compose
OBS := -f docker-compose.yml -f docker-compose.observability.yml
PY ?= python
export PYTHONPATH := apps/gateway:packages/evals

.PHONY: setup up down test test-unit eval eval-gate migrate seed demo logs site

site: ## Serve the landing page locally on port 8080
	$(PY) -m http.server 8080 --directory "landing page"

setup: ## Copy .env.example to .env (if needed) and build all images
	@test -f .env || cp .env.example .env
	$(COMPOSE) build

up: ## Start the minimal stack (gateway, worker, postgres, redis)
	$(COMPOSE) up --build -d
	@echo "Gateway: http://localhost:8000/health/ready"

down: ## Stop the stack (add V=1 to also remove volumes: make down V=1)
	$(COMPOSE) $(OBS) --profile dashboard --profile observability down $(if $(V),-v,)

test: ## Run the full test suite
	$(PY) -m pytest tests -q

test-unit: ## Run unit tests only
	$(PY) -m pytest tests/unit tests/evals -q

eval: ## Run the evaluation suite (deterministic scripted model, good mode)
	$(PY) -m modelrail_evals.runner --dataset packages/evals/datasets/modelrail-eval-v1.jsonl --mode good --out reports/eval-good.json

eval-gate: ## Prove the regression gate: good/good passes, good/degraded fails
	@mkdir -p reports
	$(PY) -m modelrail_evals.runner --dataset packages/evals/datasets/modelrail-eval-v1.jsonl --mode good --out reports/eval-baseline.json
	$(PY) -m modelrail_evals.runner --dataset packages/evals/datasets/modelrail-eval-v1.jsonl --mode degraded --out reports/eval-candidate.json
	$(PY) -m modelrail_evals.gate --baseline reports/eval-baseline.json --candidate reports/eval-baseline.json
	@if $(PY) -m modelrail_evals.gate --baseline reports/eval-baseline.json --candidate reports/eval-candidate.json; then echo "FAIL: gate passed for the degraded candidate"; exit 1; else echo "OK: gate correctly failed for the degraded candidate"; fi

migrate: ## Apply Alembic migrations (local DATABASE_URL)
	$(PY) -m alembic upgrade head

seed: ## Seed demo org/project/routes and print a demo API key (local)
	$(PY) -m app.seed

demo: ## Smoke demo against the mock provider (gateway must be up, MODELRAIL_API_KEY set)
	curl -s http://localhost:8000/health/ready
	@echo
	@test -n "$$MODELRAIL_API_KEY" || (echo "MODELRAIL_API_KEY is not set (run: make seed)"; exit 1)
	curl -s http://localhost:8000/v1/chat/completions -H "Authorization: Bearer $$MODELRAIL_API_KEY" -H "Content-Type: application/json" -d '{"model":"modelrail-fast","messages":[{"role":"user","content":"echo: Hello from ModelRail"}]}'
	@echo

logs: ## Tail logs for all services (SVC=gateway to tail one service)
	$(COMPOSE) logs -f $(SVC)
