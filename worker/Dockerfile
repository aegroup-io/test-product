FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY packages/platform-worker /app/packages/platform-worker
COPY worker /app/worker

RUN pip install --no-cache-dir -e /app/packages/platform-worker -e /app/worker

CMD ["python", "-m", "orcha_worker.devserver"]
