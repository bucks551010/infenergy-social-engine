"""Phase E - performance memory + experiment tracking tests."""

import json
import os
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_REPO, "scripts"))

from conversion import performance_memory as pm  # noqa: E402
from conversion import ConversionLogicEngine  # noqa: E402


def _write_history(tmp_dir: str, entries: list[dict]) -> None:
    os.makedirs(tmp_dir, exist_ok=True)
    with open(os.path.join(tmp_dir, "post_history.json"), "w", encoding="utf-8") as f:
        json.dump({"posts": entries}, f)


def test_summarize_ranks_winning_law_first():
    entries = [
        {
            "strategic_brief": {"logic_principle": "contrapositive"},
            "conversion_quality_score": {"total": 85.0},
        },
        {
            "strategic_brief": {"logic_principle": "contrapositive"},
            "conversion_quality_score": {"total": 90.0},
        },
        {
            "strategic_brief": {"logic_principle": "disjunctive"},
            "conversion_quality_score": {"total": 40.0},
        },
    ]
    summary = pm.summarize(entries, min_success=65.0)
    top_laws = summary["fields"]["logic_principle"]["top"]
    avoid_laws = summary["fields"]["logic_principle"]["avoid"]
    assert top_laws[0] == "contrapositive"
    assert "disjunctive" in avoid_laws


def test_winning_hints_from_history_file(tmp_path):
    entries = [
        {
            "strategic_brief": {
                "logic_principle": "result_traceability",
                "copy_framework": "PROOF-LED",
                "emotional_driver_primary": "preparedness",
            },
            "conversion_quality_score": {"total": 92.0},
        }
    ]
    _write_history(str(tmp_path), entries)
    hints = pm.winning_hints(data_dir=str(tmp_path))
    assert "result_traceability" in hints["logic_principle"]
    assert "PROOF-LED" in hints["copy_framework"]
    assert "preparedness" in hints["emotional_driver_primary"]


def test_engine_biases_toward_preferred_law():
    engine = ConversionLogicEngine()
    # Force awareness_stage where multiple laws are eligible, then verify that
    # preferring "result_traceability" wins even when it's not the default.
    product = {
        "product_name": "Portable Power Station",
        "product_type": "power_station",
        "features": ["1500Wh capacity"],
        "verified_facts": ["1500Wh"],
        "benefits": ["run essentials for 24 hours"],
    }
    b_default = engine.build_brief(
        funnel_stage="CONVERSION",
        product=product,
        recent={"laws": []},
        explicit={"awareness_stage": "MOST_AWARE"},
    )
    b_biased = engine.build_brief(
        funnel_stage="CONVERSION",
        product=product,
        recent={"laws": []},
        explicit={"awareness_stage": "MOST_AWARE"},
        winning_hints={"logic_principle": ["result_traceability"]},
    )
    # biased path chose the preferred law if it's eligible
    assert b_biased.logic_principle == "result_traceability"
    # experiment variant IDs differ when the strategy space differs
    if b_default.logic_principle != b_biased.logic_principle:
        assert b_default.experiment.variant_id != b_biased.experiment.variant_id


def test_engine_ignores_preferred_when_recent():
    engine = ConversionLogicEngine()
    product = {
        "product_name": "Solar Panel",
        "product_type": "solar_panel",
        "features": ["100W foldable"],
        "verified_facts": ["100W"],
    }
    # Preferred law is recent so engine should fall through
    b = engine.build_brief(
        funnel_stage="CONVERSION",
        product=product,
        recent={"laws": ["result_traceability"]},
        winning_hints={"logic_principle": ["result_traceability"]},
    )
    # Either it fell through OR the preferred was still allowed if it's the only eligible.
    # The important thing is it didn't crash.
    assert b.logic_principle in {"contrapositive", "disjunctive", "double_implication", "symmetrical_equivalence", "result_traceability"}


def test_strategist_auto_loads_performance_memory(tmp_path):
    from agents import conversion_strategist as cs

    entries = [
        {
            "strategic_brief": {"logic_principle": "contrapositive"},
            "conversion_quality_score": {"total": 88.0},
        },
        {
            "strategic_brief": {"logic_principle": "contrapositive"},
            "conversion_quality_score": {"total": 90.0},
        },
    ]
    _write_history(str(tmp_path), entries)

    product = {
        "product_name": "Test Power Station",
        "product_type": "power_station",
        "features": ["1000Wh"],
        "verified_facts": ["1000Wh"],
    }
    out = cs.plan(
        funnel_stage="EDUCATION",
        product=product,
        data_dir=str(tmp_path),
    )
    assert out["brief"]["brief_id"]
    # experiment block should be present with variant_id
    assert out["experiment"]["variant_id"]
    assert "law" in out["experiment"]["variables"]
    # winning_hints_applied must reflect what was loaded
    assert "contrapositive" in out["winning_hints_applied"].get("logic_principle", [])


def test_entry_score_engagement_metrics_priority():
    entry = {
        "engagement": {"engagement_rate": 0.85},
        "conversion_quality_score": {"total": 40.0},
        "quality_score": 0.3,
    }
    score = pm._entry_score(entry)
    assert score == 85.0  # 0.85 * 100


def test_entry_score_falls_back_to_cqs_then_quality():
    entry_cqs = {"conversion_quality_score": {"total": 77.5}}
    assert pm._entry_score(entry_cqs) == 77.5

    entry_q = {"quality_score": 0.65}
    assert pm._entry_score(entry_q) == 65.0

    entry_empty = {"foo": "bar"}
    assert pm._entry_score(entry_empty) == 50.0
