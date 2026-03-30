from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

from agent_core_platform_worker.live_runner import poll_and_process_runner_launches
from agent_core_platform_worker.runtime import format_result, run_job_file


def ensure_job_directories(job_root: Path) -> tuple[Path, Path, Path]:
    queued = job_root / "queued"
    completed = job_root / "completed"
    failed = job_root / "failed"
    queued.mkdir(parents=True, exist_ok=True)
    completed.mkdir(parents=True, exist_ok=True)
    failed.mkdir(parents=True, exist_ok=True)
    return queued, completed, failed


def _failure_payload(*, job_file: Path, error: Exception) -> dict[str, Any]:
    return {
        "job_file": str(job_file),
        "status": "failed",
        "error": str(error),
    }


def process_pending_jobs(job_root: Path) -> list[Path]:
    queued, completed, failed = ensure_job_directories(job_root)
    written_results: list[Path] = []
    for job_file in sorted(queued.glob("*.json")):
        try:
            result = run_job_file(job_file)
            destination_dir = completed if result.status == "succeeded" else failed
            payload = format_result(result)
        except Exception as exc:  # pragma: no cover - exercised via integration smoke
            destination_dir = failed
            payload = json.dumps(_failure_payload(job_file=job_file, error=exc), indent=2) + "\n"
        destination = destination_dir / f"{job_file.stem}.result.json"
        destination.write_text(payload, encoding="utf-8")
        job_file.unlink(missing_ok=True)
        written_results.append(destination)
    return written_results


def process_live_runner_launches() -> int:
    try:
        return poll_and_process_runner_launches()
    except Exception as exc:  # pragma: no cover - defensive guard for local loop resilience
        print(f"live runner poll failed: {exc}", file=sys.stderr)
        return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the local worker devserver.")
    parser.add_argument(
        "--job-root",
        type=Path,
        default=Path(os.getenv("AGENT_CORE_LOCAL_JOB_ROOT", "./artifacts/local-jobs")),
        help="Directory containing queued/, completed/, and failed/ worker job folders.",
    )
    parser.add_argument(
        "--poll-interval",
        type=float,
        default=float(os.getenv("AGENT_CORE_WORKER_POLL_INTERVAL", "1.0")),
        help="Polling interval in seconds when running continuously.",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Process the current queued jobs once and exit.",
    )
    args = parser.parse_args(argv)

    job_root = args.job_root.resolve()
    if args.once:
        process_pending_jobs(job_root)
        process_live_runner_launches()
        return 0

    while True:
        process_pending_jobs(job_root)
        process_live_runner_launches()
        time.sleep(max(args.poll_interval, 0.1))


if __name__ == "__main__":
    raise SystemExit(main())
