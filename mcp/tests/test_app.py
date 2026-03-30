from __future__ import annotations

from fastapi.testclient import TestClient

from orcha_mcp.main import app


def test_healthz_and_metadata() -> None:
    with TestClient(app) as client:
        health = client.get("/healthz")
        assert health.status_code == 200
        assert health.json() == {"status": "ok"}

        metadata = client.get("/metadata")
        assert metadata.status_code == 200
        assert metadata.json()["name"] == app.title
        assert metadata.json()["api_base_url"] == "http://127.0.0.1:8000"
