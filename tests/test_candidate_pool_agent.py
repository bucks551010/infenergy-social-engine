import os
import sys


_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO, "scripts"))

from agents import candidate_pool
from agents.dispatcher import available_agents


def test_candidate_pool_is_available_through_existing_agent_dispatcher():
    assert "candidate_pool" in available_agents()


def test_content_forensic_is_available_through_existing_agent_dispatcher():
    assert "content_forensic" in available_agents()


def test_candidate_pool_inspect_reports_empty_pool(tmp_path):
    report = candidate_pool.run(str(tmp_path), action="inspect")

    assert report["pool_depth"] == 0
    assert report["candidates"] == []
    assert report["latest_batch_report"] is None