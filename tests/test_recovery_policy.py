import sys
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from social import engines, recovery


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


def test_engine_brief_retains_shortlist_and_honors_selected_opportunity(monkeypatch):
    genre_id = next(iter(engines.libraries.genres()))

    def candidate(rank):
        return SimpleNamespace(
            pillar_id="brand_philosophy",
            genre_id=genre_id,
            topic_path=SimpleNamespace(topic=f"Topic {rank}", microtopic=f"micro-{rank}", angle=f"Angle {rank}"),
            audience=SimpleNamespace(
                reader_job="clarify", reader_job_config={}, segment_id="prepared", segment={},
                information_gap="gap", curiosity=f"Reality {rank}", misconception="", question=f"Question {rank}",
                emotional_driver="confidence", rationale=[],
            ),
            scores={"novelty": 0.8},
            total=float(10 - rank),
            score_summary=lambda: "score summary",
        )

    monkeypatch.setattr(engines.opportunity_engine, "generate", lambda **_: [candidate(rank) for rank in range(1, 7)])
    baseline = engines._shared_brief(
        "C",
        recent={},
        audience_hint=None,
        seasonal_context=None,
        preferred_pillar="brand_philosophy",
        excluded_concepts=[],
        rotation_index=0,
    )
    selected = baseline.opportunity_shortlist[1]
    replacement = engines._shared_brief(
        "C",
        recent={},
        audience_hint=None,
        seasonal_context=None,
        preferred_pillar="brand_philosophy",
        excluded_concepts=[],
        rotation_index=0,
        selected_opportunity_id=selected["opportunity_id"],
    )

    assert len(baseline.opportunity_shortlist) >= 2
    assert replacement.question == selected["question"]
    assert replacement.as_dict()["opportunity_shortlist"] == baseline.opportunity_shortlist