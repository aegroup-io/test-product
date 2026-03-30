from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agent_core_platform_worker.schemas import WorkerJob


Handler = Callable[[WorkerJob], dict[str, Any] | None]


class HandlerRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, Handler] = {}

    def register(self, job_type: str, handler: Handler) -> None:
        self._handlers[job_type] = handler

    def resolve(self, job_type: str) -> Handler | None:
        return self._handlers.get(job_type)

    def keys(self) -> list[str]:
        return sorted(self._handlers)
