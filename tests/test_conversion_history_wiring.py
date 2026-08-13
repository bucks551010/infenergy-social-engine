"""Regression: post_history.json must carry conversion-learning fields.

Locks in the audit fix where run_engine.py's history append blocks never
persisted strategic_brief / CQS / brief_adherence, silently breaking the
Phase E performance-memory feedback loop (winning_hints always empty).
"""
from __future__ import annotations

import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(_HERE)
sys.path.insert(0, os.path.join(_REPO, "scripts"))

from conversion import performance_memory as pm  # noqa: E402
import run_engine  # noqa: E402


def test_conversion_learning_fields_extracts_nested_brief():
    content = {
        "strategic_brief": {"logic_principle": "contrapositive", "copy_framework": "PAS"},
        "conversion_quality_score": {"total": 88.0, "band": "strong"},
        "conversion_brief_adherence": {"adherence_pct": 71.4},
        "conversion_variant_id": "abc123",
    }
    fields = run_engine._conversion_learning_fields(content)
    assert fields["strategic_brief"] == content["strategic_brief"]
    assert fields["logic_principle"] == "contrapositive"
    assert fields["copy_framework"] == "PAS"
    assert fields["conversion_quality_score"] == content["conversion_quality_score"]
    assert fields["conversion_brief_adherence"] == content["conversion_brief_adherence"]
    assert fields["conversion_variant_id"] == "abc123"


def test_conversion_learning_fields_safe_when_brief_missing():
    fields = run_engine._conversion_learning_fields({})
    assert fields["strategic_brief"] is None
    assert fields["logic_principle"] == ""
    assert fields["copy_framework"] == ""
    assert fields["conversion_variant_id"] == ""


def test_history_record_shaped_like_run_engine_feeds_performance_memory(tmp_path):
    """End-to-end contract: a history entry built the way run_engine.py
    now builds it must be usable by performance_memory.winning_hints."""
    content = {
        "post_id": "p1",
        "strategic_brief": {
            "logic_principle": "result_traceability",
            "copy_framework": "PROOF-LED",
            "emotional_driver_primary": "preparedness",
            "audience_id": "prepper_pete",
            "awareness_stage": "MOST_AWARE",
        },
        "conversion_quality_score": {"total": 91.0},
        "conversion_brief_adherence": {"adherence_pct": 88.0},
        "conversion_variant_id": "variant-xyz",
    }
    record = {
        "post_id": content.get("post_id", ""),
        "hook": content.get("selected_hook", ""),
        **run_engine._conversion_learning_fields(content),
    }
    history_dir = str(tmp_path)
    os.makedirs(history_dir, exist_ok=True)
    with open(os.path.join(history_dir, "post_history.json"), "w", encoding="utf-8") as f:
        json.dump({"posts": [record]}, f)

    hints = pm.winning_hints(data_dir=history_dir)
    assert "result_traceability" in hints["logic_principle"]
    assert "PROOF-LED" in hints["copy_framework"]
    assert "preparedness" in hints["emotional_driver_primary"]
    assert "prepper_pete" in hints["audience_id"]
    assert "MOST_AWARE" in hints["awareness_stage"]


def test_generate_end_to_end_exposes_hints_and_experiment(tmp_path, monkeypatch):
    """Full loop: seed history with a clear winner/loser, call generate(), and
    confirm the strategist's bias decisions are visible on the final payload
    (regression for the generate_posts.py key-whitelist that used to drop
    experiment/winning_hints_applied/losing_hints_applied)."""
    history_dir = str(tmp_path)
    os.makedirs(history_dir, exist_ok=True)
    history = {"posts": [
        {"strategic_brief": {"logic_principle": "double_implication"}, "conversion_quality_score": {"total": 10.0}},
        {"strategic_brief": {"logic_principle": "double_implication"}, "conversion_quality_score": {"total": 15.0}},
        {"strategic_brief": {"logic_principle": "contrapositive"}, "conversion_quality_score": {"total": 95.0}},
        {"strategic_brief": {"logic_principle": "contrapositive"}, "conversion_quality_score": {"total": 92.0}},
    ]}
    with open(os.path.join(history_dir, "post_history.json"), "w", encoding="utf-8") as f:
        json.dump(history, f)

    monkeypatch.setenv("DATA_DIR", history_dir)
    import importlib
    import generate_posts as gp
    importlib.reload(gp)
    try:
        content = gp.generate("morning", funnel_stage_override="CONVERSION", pipeline_override="legacy")
        strategist = content.get("conversion_strategist", {})
        assert strategist.get("winning_hints_applied", {}).get("logic_principle") == ["contrapositive"]
        assert strategist.get("losing_hints_applied", {}).get("logic_principle") == ["double_implication"]
        assert strategist.get("experiment", {}).get("variant_id")
        assert content.get("conversion_variant_id")
    finally:
        monkeypatch.delenv("DATA_DIR", raising=False)
        importlib.reload(gp)
