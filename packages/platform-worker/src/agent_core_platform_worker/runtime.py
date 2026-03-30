from __future__ import annotations

import json
from pathlib import Path

from agent_core_platform_worker.handlers import create_default_registry
from agent_core_platform_worker.registry import HandlerRegistry
from agent_core_platform_worker.schemas import WorkerJob, WorkerResult


def load_job(job_file: Path) -> WorkerJob:
    return WorkerJob.model_validate_json(job_file.read_text(encoding="utf-8"))


def run_job(job: WorkerJob, registry: HandlerRegistry | None = None) -> WorkerResult:
    resolved_registry = registry or create_default_registry()
    handler = resolved_registry.resolve(job.job_type)
    if handler is None:
        return WorkerResult(
            job_id=job.job_id,
            job_type=job.job_type,
            status="failed",
            error=f"Unknown job type: {job.job_type}",
        )
    try:
        output = handler(job) or {}
        return WorkerResult(
            job_id=job.job_id,
            job_type=job.job_type,
            status="succeeded",
            output=output,
        )
    except Exception as exc:
        return WorkerResult(
            job_id=job.job_id,
            job_type=job.job_type,
            status="failed",
            error=str(exc),
        )


def run_job_file(job_file: Path, registry: HandlerRegistry | None = None) -> WorkerResult:
    return run_job(load_job(job_file), registry=registry)


def format_result(result: WorkerResult) -> str:
    return json.dumps(result.model_dump(mode="json"), indent=2) + "\n"
