import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from social import recovery


def test_duplicate_wins_over_presentation_repair():
    assert recovery.classify_failure([
        "duplicate_product_within_window",
        "linkedin_final_presentation_not_ready",
    ]) == recovery.STRATEGY_REPLACEMENT_REQUIRED


def test_presentation_only_is_repairable():
    assert recovery.classify_failure(["linkedin_final_presentation_not_ready"]) == recovery.PRESENTATION_REPAIRABLE


def test_replacement_respects_rank_and_prefilters_duplicate_product():
    shortlist = [
        {"rank": 1, "product_id": "PPP-200", "topic": "A"},
        {"rank": 2, "product_id": "PPP-200", "topic": "B"},
        {"rank": 3, "product_id": "OTHER", "topic": "C"},
    ]
    selected, considered = recovery.select_replacement(shortlist, excluded_product_ids={"PPP-200"})

    assert selected["rank"] == 3
    assert considered[0]["reason"] == "duplicate_product_within_window"
    assert considered[-1]["result"] == "selected"


def test_replacement_is_bounded_to_candidate_b():
    shortlist = [{"rank": 1}, {"rank": 2, "topic": "replacement"}, {"rank": 3, "topic": "third"}]
    selected, _ = recovery.select_replacement(shortlist)

    assert selected["rank"] == 2