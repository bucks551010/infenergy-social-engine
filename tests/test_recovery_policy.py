import sys
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from social import engines, memory_intelligence, orchestrator, recovery


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


def test_cross_engine_pool_prefers_evidence_safe_audience_value_over_blocked_commercial_option(monkeypatch):
    genre_id = next(iter(engines.libraries.genres()))

    def candidate(engine, total, question, angle, reality):
        return SimpleNamespace(
            pillar_id="brand_philosophy", genre_id=genre_id,
            topic_path=SimpleNamespace(topic="Power habits", microtopic=engine, angle=angle),
            audience=SimpleNamespace(reader_job="TEACH_ME", reader_job_config={}, segment_id="prepared", segment={}, information_gap="daily routine", curiosity=reality, misconception="", question=question, emotional_driver="confidence", rationale=[]),
            scores={"novelty": 0.9, "platform_fit": 0.8}, total=total,
            score_summary=lambda: "high value",
        )

    pool_by_engine = {
        "A": [candidate("A", 0.92, "Will PowerPulse fit before a trip?", "Establish fit before reserve.", "before a trip")],
        "B": [candidate("B", 0.9, "Which routine depends on the next outlet?", "Map the job before choosing what to protect.", "a normal workday")],
        "C": [candidate("C", 0.62, "What does reliable technology feel like?", "Notice the routine behind the tool.", "an ordinary day")],
    }
    monkeypatch.setattr(engines.opportunity_engine, "generate", lambda engine, **_: pool_by_engine[engine])

    pool = engines.build_competitive_pool(recent={})

    assert len(pool) == 3
    assert pool[0]["engine"] == "B"
    assert pool[0]["product_relevance"] == "NOT_REQUIRED"
    assert pool[0]["known_evidence_burden"] == "LOW"
    assert pool[1]["engine"] == "A"
    assert len({record["opportunity_id"] for record in pool}) == len(pool)


def test_recent_evidence_block_is_attempt_only_exclusion_not_published_exposure(tmp_path):
    history = {
        "posts": [{
            "evidence_remediation": {
                "original_evidence_readiness": {"status": "RESEARCH_REQUIRED"},
                "original_concept": {"question": "Can PowerPulse fit before a trip?", "angle": "Establish fit before reserve."},
            },
            "final_memory": {"final_outcome": "do_not_publish"},
        }]
    }
    path = tmp_path / "post_history.json"
    path.write_text(__import__("json").dumps(history), encoding="utf-8")

    recent = memory_intelligence.recent(str(tmp_path))

    assert "Can PowerPulse fit before a trip?" in recent["attempt_only_exclusions"]
    assert recent["topics"] == []


def test_single_post_batch_uses_global_pool_instead_of_forcing_rotation_engine(monkeypatch, tmp_path):
    selected = []

    def fake_create_post(self, **kwargs):
        selected.append(kwargs.get("preferred_engine"))
        return SimpleNamespace(engine="B")

    monkeypatch.setattr(orchestrator, "_pick_engine", lambda _: "A")
    monkeypatch.setattr(orchestrator.SocialIntelligenceOrchestrator, "create_post", fake_create_post)
    service = orchestrator.SocialIntelligenceOrchestrator(data_dir=str(tmp_path))

    service.create_batch(count=1)
    service.create_batch(count=2)

    assert selected == [None, "A", "A"]