"""Phase F - unified visual brief tests."""
from __future__ import annotations

import os
import sys

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)
if os.path.join(_REPO, "scripts") not in sys.path:
    sys.path.insert(0, os.path.join(_REPO, "scripts"))

import importlib

gp = importlib.import_module("generate_posts")


def _make_run_context(law="contrapositive"):
    return {
        "strategic_brief": {
            "logic_principle": law,
            "design": {
                "visual_direction": "photo-real hero shot with a rugged outdoor palette",
                "template": "problem_reframe_hero",
            },
            "persuasion": {
                "transformation_from": "power outage during a storm",
                "transformation_to": "lights stay on for 24 hours",
                "proof": "1500Wh verified capacity",
            },
        },
        "conversion_strategist": {
            "law_narrative_template": [
                "Show the storm setting",
                "Show the outage moment",
                "Reveal the power station",
                "Show the family lit and warm",
                "End with pinned CTA",
            ],
            "downstream_instructions": {
                "cta_pinned": "Order the 1500Wh station today",
            },
        },
    }


def test_apply_strategic_brief_to_visual_injects_direction_and_prompt_prefix():
    vp = {
        "visual_objective": "clean product shot",
        "gemini_image_prompt": "A power station on a wooden table, warm indoor light.",
    }
    out = gp._apply_strategic_brief_to_visual(vp, _make_run_context(), product={"product_name": "PS"})
    assert "photo-real hero shot" in out["visual_objective"]
    assert out["gemini_image_prompt"].startswith("[contrapositive visual strategy]")
    assert out["strategic_visual_direction"].startswith("photo-real")
    assert out["strategic_template_family"] == "problem_reframe_hero"


def test_apply_strategic_brief_to_visual_builds_storyboard_from_narrative_template():
    vp = {"visual_objective": "", "gemini_image_prompt": "scene"}
    out = gp._apply_strategic_brief_to_visual(vp, _make_run_context(), product=None)
    storyboard = out["strategic_carousel_storyboard"]
    assert len(storyboard) == 7
    assert storyboard[0]["role"] == "COVER"
    assert storyboard[1]["beat"].startswith("Show the storm")
    # slide 1 seeded with transformation_from
    assert "storm" in storyboard[1]["on_image_text_hint"].lower()
    # last slide holds pinned CTA
    assert "1500wh" in storyboard[-1]["on_image_text_hint"].lower()
    assert storyboard[-1]["role"] == "FINALE"
    assert storyboard[-1]["logo_url"].startswith("https://infenergypower.com/")


def test_apply_strategic_brief_to_visual_falls_back_when_no_narrative():
    rc = _make_run_context()
    rc["conversion_strategist"]["law_narrative_template"] = []
    out = gp._apply_strategic_brief_to_visual({"visual_objective": "", "gemini_image_prompt": ""}, rc, product=None)
    storyboard = out["strategic_carousel_storyboard"]
    assert len(storyboard) == 7
    for slide in storyboard:
        assert slide["beat"].strip()


def test_apply_strategic_brief_no_op_when_brief_missing():
    vp = {"visual_objective": "orig", "gemini_image_prompt": "prompt"}
    out = gp._apply_strategic_brief_to_visual(vp, {}, product=None)
    assert out is vp
    assert "strategic_brief_alignment" not in out


def test_phase_f_gate_emitted_when_brief_present():
    run_context = _make_run_context()
    content = {
        "visual_plan": {
            "visual_objective": "photo-real hero shot with a rugged outdoor palette scene",
            "gemini_image_prompt": "[contrapositive visual strategy] a family",
            "strategic_brief_alignment": {
                "logic_principle": "contrapositive",
                "template_family": "problem_reframe_hero",
                "visual_direction_present": True,
                "law_signal_in_prompt": True,
                "storyboard_slides": 5,
            },
        }
    }
    gates: list[dict] = []
    out = gp._run_phase_f_visual_alignment(content, run_context, gates)
    ids = [g["gate_id"] for g in gates]
    assert "phase_f_visual_alignment" in ids
    gate = next(g for g in gates if g["gate_id"] == "phase_f_visual_alignment")
    assert gate["passed"] is True
    assert out["conversion_visual_alignment"]["alignment_pct"] == 100.0


def test_phase_f_gate_warns_on_low_alignment():
    run_context = _make_run_context()
    content = {
        "visual_plan": {
            "strategic_brief_alignment": {
                "logic_principle": "contrapositive",
                "template_family": "",
                "visual_direction_present": False,
                "law_signal_in_prompt": False,
                "storyboard_slides": 0,
            },
        }
    }
    gates: list[dict] = []
    gp._run_phase_f_visual_alignment(content, run_context, gates)
    gate = next(g for g in gates if g["gate_id"] == "phase_f_visual_alignment")
    assert gate["passed"] is False
    assert gate["severity"] == "warning"


def test_phase_f_gate_disabled_when_no_brief():
    gates: list[dict] = []
    gp._run_phase_f_visual_alignment({"visual_plan": {}}, {}, gates)
    gate = next(g for g in gates if g["gate_id"] == "phase_f_visual_alignment")
    assert gate["passed"] is True
    assert gate["details"]["enabled"] is False


def test_reapplying_after_conference_overwrite_restores_law_signal():
    """Regression: the agent conference can replace visual_plan['gemini_image_prompt']
    after the first injection. Re-calling _apply_strategic_brief_to_visual (as
    generate_posts.py now does post-conference) must re-assert the law prefix
    instead of leaving stale/incorrect alignment metadata."""
    rc = _make_run_context()
    vp = {"visual_objective": "", "gemini_image_prompt": "original scene"}
    vp = gp._apply_strategic_brief_to_visual(vp, rc, product=None)
    assert vp["gemini_image_prompt"].startswith("[contrapositive visual strategy]")

    # Simulate the agent conference replacing the prompt outright.
    vp["gemini_image_prompt"] = "a brand new scene with no law reference"
    vp = gp._apply_strategic_brief_to_visual(vp, rc, product=None)
    assert vp["gemini_image_prompt"].startswith("[contrapositive visual strategy]")
    assert vp["strategic_brief_alignment"]["law_signal_in_prompt"] is True


def test_reapplying_is_idempotent_when_prompt_unchanged():
    rc = _make_run_context()
    vp = {"visual_objective": "", "gemini_image_prompt": "scene"}
    vp = gp._apply_strategic_brief_to_visual(vp, rc, product=None)
    first_prompt = vp["gemini_image_prompt"]
    first_objective = vp["visual_objective"]
    vp = gp._apply_strategic_brief_to_visual(vp, rc, product=None)
    assert vp["gemini_image_prompt"] == first_prompt
    assert vp["visual_objective"] == first_objective

