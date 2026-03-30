from __future__ import annotations

import os

from fastapi import FastAPI

from .product_defaults import API_BASE_URL, APP_NAME


os.environ.setdefault("AGENT_CORE_MCP_NAME", APP_NAME)
os.environ.setdefault("AGENT_CORE_API_BASE_URL", API_BASE_URL)

app = FastAPI(title=os.getenv("AGENT_CORE_MCP_NAME", APP_NAME), version="0.1.0")


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/metadata")
def metadata() -> dict[str, str]:
    return {
        "name": os.getenv("AGENT_CORE_MCP_NAME", APP_NAME),
        "api_base_url": os.getenv("AGENT_CORE_API_BASE_URL", API_BASE_URL),
    }
