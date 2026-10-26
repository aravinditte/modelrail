# Compose Profiles and Configurations

ModelRail provides Docker Compose configurations and profiles for reproducible local execution (spec §5, §20).

## Profiles

1. **Minimal Development (Default):**
   - Services: `gateway`, `worker`, `postgres`, `redis`
   - Command: `docker compose up --build -d`

2. **Dashboard Interface:**
   - Services: adds Next.js `dashboard` UI on port 3000
   - Command: `docker compose --profile dashboard up -d`

3. **Test Execution:**
   - Services: executes the full `pytest` suite against PostgreSQL and Redis
   - Command: `docker compose --profile test up --abort-on-container-exit`
   - Overlay: `docker compose -f docker-compose.yml -f infra/compose/docker-compose.test.yml --profile test up`

4. **Full Observability:**
   - Services: adds `prometheus`, `grafana`, `tempo`, `otel-collector`
   - Command: `docker compose -f docker-compose.yml -f docker-compose.observability.yml --profile observability up -d`

5. **Optional Local Inference (Ollama):**
   - Services: adds local `ollama` container on port 11434 with persistent model volume
   - Command: `docker compose --profile ollama up -d`
   - Overlay: `docker compose -f docker-compose.yml -f infra/compose/docker-compose.ollama.yml --profile ollama up -d`
