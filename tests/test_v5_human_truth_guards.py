from __future__ import annotations

import os
import sys
import tempfile
import types


_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO, "scripts"))

from run_engine import _v5_semantic_visual_errors
from social.claim_governance import assess_visual_prompt
from social.quality_intelligence import human_truth_gate
from social.living_intelligence import load, propose_static_update
from social.visual_provider import GeminiVisualProvider
from social.visual_intelligence import build_v5_art_directions, compile_v5_scene_prompt


def _direction() -> dict:
    return build_v5_art_directions(
        strategy={"audience": "caregiver", "human_need": "continuity", "customer_moment": "care planning"},
        reader_job="GIVE_ME_A_REFERENCE",
        genre_id="checklist",
        platform="instagram_feed",
    )[0]


def test_human_truth_gate_rejects_fear_leverage() -> None:
    result = human_truth_gate(
        hook="Fear is coming",
        body="The storm will be terrible.",
        takeaway="Buy now.",
        strategy={},
    )

    assert not result["ready"]
    assert result["failures"]


def test_v5_prompt_gate_rejects_unsupported_whole_home_implication() -> None:
    direction = _direction()
    prompt = compile_v5_scene_prompt(direction)

    result = assess_visual_prompt(direction, prompt + " Show the product powering an entire house.", has_product_reference=False)

    assert not result["ready"]
    assert "unsupported_visual_implication:whole_home" in result["failures"]


def test_v5_direction_scores_recent_scenes_lower_for_novelty() -> None:
    directions = build_v5_art_directions(
        strategy={"audience": "caregiver", "human_need": "continuity", "customer_moment": "care planning"},
        reader_job="GIVE_ME_A_REFERENCE",
        genre_id="checklist",
        platform="instagram_feed",
        recent_scenes=["kitchen"],
    )

    assert directions == sorted(directions, key=lambda item: item["score"], reverse=True)
    assert all("score_components" in item for item in directions)


def test_failed_v5_semantic_qa_blocks_active_platform() -> None:
    content = {
        "generated_visuals": {
            "visual_generation": {"instagram": {"v5_qa": {"acceptable": False, "has_text": True}}}
        }
    }

    assert _v5_semantic_visual_errors(content, {"instagram": True}) == ["instagram_v5_semantic_qa:has_text,unacceptable"]


def test_static_proposal_stays_pending_owner_approval() -> None:
    data_dir = tempfile.mkdtemp()
    proposal = propose_static_update(data_dir, proposal_type="claim_review", rationale="new first-party evidence needs review", evidence=[{"source": "first_party"}])

    assert proposal["status"] == "PENDING_OWNER_APPROVAL"
    assert load(data_dir)["static_proposals"][0]["rationale"] == "new first-party evidence needs review"


def test_gemini_provider_tries_next_governed_v5_direction(monkeypatch) -> None:
    calls: list[str] = []

    def generate_visuals(_content, plan):
        calls.append(plan["gemini_image_prompt"])
        return {"fallback_reasons": {"instagram": "primary_failed"}} if len(calls) == 1 else {"instagram": "alternate.png"}

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setitem(sys.modules, "social_visuals", types.SimpleNamespace(generate_visuals=generate_visuals))
    result = GeminiVisualProvider().generate(
        art_direction={
            "post_id": "p1",
            "v5_direction": {"scene": "primary"},
            "v5_scene_prompt": "primary prompt",
            "v5_fallback_candidates": [{"direction": {"scene": "alternate"}, "prompt": "alternate prompt", "prompt_governance": {"ready": True}}],
        },
        positive_prompt="primary prompt",
        negative_prompt="",
        platform="instagram_feed",
    )

    assert result.kind == "generated_image"
    assert result.asset_path == "alternate.png"
    assert calls == ["primary prompt", "alternate prompt"]
    assert result.provider_meta["fallback_ladder"] == [{"kind": "primary", "reason": "primary_failed"}]