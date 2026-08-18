"""Railway entry point for an isolated ten-decision content forensic."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from typing import Any


def _latest_report(data_dir: str) -> dict:
    diagnostics_dir = os.path.join(data_dir, "diagnostics")
    try:
        runs = sorted(
            [name for name in os.listdir(diagnostics_dir) if name.startswith("content_generation_10_run_")],
            reverse=True,
        )
    except OSError:
        runs = []
    if not runs:
        return {"error": "content_forensic_report_not_found"}
    output_dir = os.path.join(diagnostics_dir, runs[0])
    try:
        with open(os.path.join(output_dir, "content_generation_10_run.json"), encoding="utf-8") as handle:
            report = json.load(handle)
        with open(os.path.join(output_dir, "content_generation_10_run.md"), encoding="utf-8") as handle:
            markdown = handle.read()
    except (OSError, json.JSONDecodeError) as exc:
        return {"error": f"content_forensic_report_unreadable:{exc}", "output_dir": output_dir}
    return {
        "status": "completed",
        "output_dir": output_dir,
        "aggregate": report.get("aggregate", {}),
        "safety": {
            "images_generated": report.get("metadata", {}).get("image_provider_calls", 0),
            "publisher_calls": report.get("metadata", {}).get("publisher_calls", 0),
            "production_state_contaminated": report.get("metadata", {}).get("production_state_contaminated"),
        },
        "markdown_report": markdown,
        "json_report": report,
    }


def run(data_dir: str, count: int = 10, action: str = "run", **_: Any) -> dict:
    if str(action).strip().lower() in {"latest", "report", "read"}:
        return _latest_report(data_dir)
    if int(count) != 10:
        return {"error": "content_forensic_requires_exactly_10_runs"}
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    output_dir = os.path.join(data_dir, "diagnostics", f"content_generation_10_run_{stamp}")
    state_dir = os.path.join(output_dir, "isolated_state")
    os.makedirs(output_dir, exist_ok=True)
    shutil.copytree(data_dir, state_dir, ignore=shutil.ignore_patterns("diagnostics"), dirs_exist_ok=True)
    runner = os.path.join(os.path.dirname(os.path.dirname(__file__)), "forensics", "content_generation_experiment.py")
    env = os.environ.copy()
    env["DATA_DIR"] = state_dir
    completed = subprocess.run(
        [sys.executable, runner, "--state-dir", state_dir, "--output-dir", output_dir, "--count", "10"],
        cwd=os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        env=env,
        capture_output=True,
        text=True,
        timeout=1800,
        check=False,
    )
    if completed.returncode != 0:
        return {
            "error": "content_forensic_runner_failed",
            "output_dir": output_dir,
            "output_tail": ((completed.stdout or "") + "\n" + (completed.stderr or ""))[-5000:],
        }
    payload_path = os.path.join(output_dir, "content_generation_10_run.json")
    try:
        with open(payload_path, encoding="utf-8") as handle:
            report = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        return {"error": f"content_forensic_report_missing:{exc}", "output_dir": output_dir}
    return {
        "status": "completed",
        "output_dir": output_dir,
        "json_report": payload_path,
        "markdown_report": os.path.join(output_dir, "content_generation_10_run.md"),
        "aggregate": report.get("aggregate", {}),
        "safety": {
            "images_generated": report.get("metadata", {}).get("image_provider_calls", 0),
            "image_generation_boundary_intercepts": report.get("metadata", {}).get("image_generation_boundary_intercepts", 0),
            "publisher_calls": report.get("metadata", {}).get("publisher_calls", 0),
            "production_state_contaminated": report.get("metadata", {}).get("production_state_contaminated"),
        },
    }