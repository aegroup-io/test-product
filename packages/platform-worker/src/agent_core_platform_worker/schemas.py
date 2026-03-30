from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field


class RequestedBy(BaseModel):
    type: Literal["user", "system", "service"]
    id: str = Field(min_length=1)


class WorkerJob(BaseModel):
    job_id: UUID
    job_type: str = Field(min_length=1)
    idempotency_key: str = Field(min_length=1)
    requested_by: RequestedBy
    payload: dict[str, Any] = Field(default_factory=dict)
    attempt: int = 1


class WorkerResult(BaseModel):
    job_id: UUID
    job_type: str
    status: Literal["succeeded", "failed"]
    output: dict[str, Any] | None = None
    error: str | None = None
    finished_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
