FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc tesseract-ocr poppler-utils \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install -r requirements.txt

COPY backend/ .

EXPOSE 8000

# SERVICE_ROLE=api  → migrate, optionally seed (RUN_SEED=true), serve uvicorn
# SERVICE_ROLE=worker → Celery worker (no migrations, no HTTP)
CMD ["sh", "-c", "if [ \"$SERVICE_ROLE\" = \"worker\" ]; then \
    exec celery -A app.worker:celery_app worker -l info --concurrency=${CELERY_CONCURRENCY:-2}; \
  else \
    alembic upgrade head && \
    { [ \"$RUN_SEED\" = \"true\" ] && python -m app.seed.run || true; } && \
    exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}; \
  fi"]
