from __future__ import annotations

import argparse
from pathlib import Path

from agent_core_platform_worker.runtime import format_result, run_job_file


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run a single starter-stack worker job.")
    parser.add_argument("--job-file", type=Path, required=True, help="Path to a JSON job payload.")
    args = parser.parse_args(argv)

    result = run_job_file(args.job_file.resolve())
    print(format_result(result), end="")
    return 0 if result.status == "succeeded" else 1


if __name__ == "__main__":
    raise SystemExit(main())
