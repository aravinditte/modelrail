# Build context is the repository root (see docker-compose.yml).
FROM python:3.12-slim
WORKDIR /repo
ENV PYTHONUNBUFFERED=1 MODELRAIL_GATEWAY_DIR=apps/gateway MODELRAIL_REPO_ROOT=.
COPY apps/gateway/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY apps ./apps
COPY packages ./packages
CMD ["python", "apps/evaluation-worker/worker/main.py"]
