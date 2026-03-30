from __future__ import annotations

from typing import Any

import httpx

from agent_core_platform_worker.config import load_config
from agent_core_platform_worker.registry import HandlerRegistry
from agent_core_platform_worker.schemas import WorkerJob


def _api_probe(job: WorkerJob) -> dict[str, Any]:
    payload = job.payload
    url = str(payload.get("url") or f"{load_config().api_base_url.rstrip('/')}/health")
    method = str(payload.get("method") or "GET").upper()
    expected_status = int(payload.get("expected_status") or 200)
    response = httpx.request(method, url, timeout=load_config().request_timeout_seconds)
    if response.status_code != expected_status:
        raise RuntimeError(f"Expected {expected_status}, received {response.status_code}")
    return {
        "url": url,
        "status_code": response.status_code,
        "body_preview": response.text[:200],
    }


def _settings_snapshot(job: WorkerJob) -> dict[str, Any]:
    settings = job.payload.get("settings") or []
    if not isinstance(settings, list):
        raise RuntimeError("settings payload must be a list")
    keys = [item.get("key") for item in settings if isinstance(item, dict) and item.get("key")]
    scopes = sorted(
        {
            str(item.get("scope_type"))
            for item in settings
            if isinstance(item, dict) and item.get("scope_type")
        }
    )
    return {
        "setting_count": len(settings),
        "keys": sorted(str(key) for key in keys),
        "scopes": scopes,
    }


def create_default_registry() -> HandlerRegistry:
    registry = HandlerRegistry()
    registry.register("platform.api_probe", _api_probe)
    registry.register("platform.settings_snapshot", _settings_snapshot)
    return registry
