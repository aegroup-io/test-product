FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends git ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY . /app

RUN pip install --no-cache-dir -e /app/packages/platform-api -e /app/api

EXPOSE 8080

CMD ["uvicorn", "orcha_api.main:app", "--host", "0.0.0.0", "--port", "8080"]
