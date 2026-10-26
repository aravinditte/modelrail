# Build context is the repository root (see docker-compose.yml).
FROM python:3.12-slim
WORKDIR /repo
ENV PYTHONUNBUFFERED=1 PYTHONPATH=/repo/apps/gateway:/repo/packages/evals
COPY apps/gateway/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY alembic.ini ./alembic.ini
COPY migrations ./migrations
COPY apps ./apps
COPY packages ./packages
COPY ["landing page", "./landing page"]
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
