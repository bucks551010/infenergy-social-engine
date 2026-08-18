import os
import sys
import json


_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO, "scripts"))

from agents import candidate_pool
from agents import content_forensic
from agents.dispatcher import available_agents


def test_candidate_pool_is_available_through_existing_agent_dispatcher():
    assert "candidate_pool" in available_agents()


def test_content_forensic_is_available_through_existing_agent_dispatcher():
    assert "content_forensic" in available_agents()


def test_content_forensic_latest_returns_isolated_report(tmp_path):
    output_dir = tmp_path / "diagnostics" / "content_generation_10_run_20260818T000000Z"
    output_dir.mkdir(parents=True)
    report = {"metadata": {"image_provider_calls": 0, "publisher_calls": 0, "production_state_contaminated": False}, "aggregate": {"total_decisions": 10}}
    (output_dir / "content_generation_10_run.json").write_text(json.dumps(report), encoding="utf-8")
    (output_dir / "content_generation_10_run.md").write_text("# report\n", encoding="utf-8")

    result = content_forensic.run(str(tmp_path), action="latest")

    assert result["status"] == "completed"
    assert result["aggregate"]["total_decisions"] == 10
    assert result["safety"]["images_generated"] == 0


def test_candidate_pool_inspect_reports_empty_pool(tmp_path):
    report = candidate_pool.run(str(tmp_path), action="inspect")

    assert report["pool_depth"] == 0
    assert report["candidates"] == []
    assert report["latest_batch_report"] is None