from __future__ import annotations

import json
import subprocess
from pathlib import Path


def test_readiness_drill_script_writes_planned_artifacts(tmp_path: Path) -> None:
    repo_root = Path(__file__).resolve().parents[2]
    output_dir = tmp_path / "readiness-drills"

    subprocess.run(
        [
            "python3",
            "scripts/run_readiness_drills.py",
            "--dry-run",
            "--output-dir",
            str(output_dir),
        ],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )

    payload = json.loads((output_dir / "readiness-drills.json").read_text(encoding="utf-8"))
    assert len(payload["drills"]) == 6
    assert all(entry["result"] == "planned" for entry in payload["drills"])
    markdown = (output_dir / "readiness-drills.md").read_text(encoding="utf-8")
    assert "# Production Readiness Drills" in markdown
    assert "Webhook replay" in markdown
