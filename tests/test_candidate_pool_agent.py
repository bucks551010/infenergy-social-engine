import os
import sys


_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO, "scripts"))

from agents.dispatcher import available_agents


def test_candidate_pool_is_available_through_existing_agent_dispatcher():
    assert "candidate_pool" in available_agents()