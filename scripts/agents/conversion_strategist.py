"""ConversionStrategist agent — Spec Sections 9, 19, 42, 44.

This is the copywriting agent: it owns the strategic decisions that shape
every generated post. It calls the ConversionLogicEngine to build a
StrategicBrief, snapshots it, and hands it to downstream generation phases
in scripts/generate_posts.py.

Contract:
    plan(inputs) -> {"brief": StrategicBrief.to_dict(), "hook_targets": [...],
                     "structure_beats": [...], "guardrails": [...],
                     "objection_reframe": str, "law_narrative_template": [...]}

The output shape is stable so downstream code and tests can rely on it.
"""

from __future__ import annotations

from typing import Any

from ._base import utc_now, write_snapshot
from conversion import ConversionLogicEngine, StrategicBrief
from conversion import copy_structures as copy_structures_mod
from conversion import logic_laws as logic_laws_mod
from conversion import objections as objections_mod
from conversion import awareness as awareness_mod
from conversion import emotions as emotions_mod
from conversion import performance_memory as performance_memory_mod

AGENT_NAME = "conversion_strategist"


def plan(
    *,
    funnel_stage: str,
    product: dict[str, Any] | None = None,
    audience_hint: str | None = None,
    campaign_goal: str = "",
    platform_priority: list[str] | None = None,
    recent: dict[str, list[str]] | None = None,
    explicit: dict[str, str] | None = None,
    data_dir: str | None = None,
    winning_hints: dict[str, list[str]] | None = None,
) -> dict[str, Any]:
    """Produce the strategic brief and downstream execution hints.

    When `winning_hints` is None and `data_dir` is provided, performance_memory
    is auto-loaded so the engine can exploit historically successful combos
    while still respecting recency-based diversity (spec Section 27).
    """

    if winning_hints is None and data_dir:
        try:
            winning_hints = performance_memory_mod.winning_hints(data_dir=data_dir)
        except Exception:
            winning_hints = {}

    engine = ConversionLogicEngine()
    brief: StrategicBrief = engine.build_brief(
        funnel_stage=funnel_stage,
        product=product,
        audience_hint=audience_hint,
        campaign_goal=campaign_goal,
        platform_priority=platform_priority,
        recent=recent,
        explicit=explicit,
        winning_hints=winning_hints,
    )

    law = brief.logic_principle
    structure = brief.copy_framework
    awareness = brief.awareness_stage

    payload = {
        "agent": AGENT_NAME,
        "generated_at": utc_now(),
        "brief": brief.to_dict(),
        "summary": brief.summary(),
        "hook_targets": {
            "category_hint": brief.experiment.variables.get("hook_category_hint"),
            "preferred_categories": awareness_mod.preferred_hook_categories(awareness),
            "primary_emotion": brief.emotional_driver_primary,
            "emotion_cues": emotions_mod.cues_for(brief.emotional_driver_primary),
        },
        "structure_beats": copy_structures_mod.beats(structure),
        "law_narrative_template": logic_laws_mod.narrative_template(law),
        "law_guardrails": logic_laws_mod.guardrails(law),
        "objection_reframe": {
            "reframe_pattern": brief.persuasion.objection,
            "supporting_proof_types": objections_mod.supporting_proof_types(
                _resolve_objection_name(brief.persuasion.objection)
            ),
        },
        "downstream_instructions": _downstream_instructions(brief),
        "winning_hints_applied": winning_hints or {},
        "experiment": {
            "variant_id": brief.experiment.variant_id,
            "variables": dict(brief.experiment.variables),
        },
    }

    if data_dir:
        try:
            write_snapshot(data_dir, AGENT_NAME, payload)
        except Exception:
            pass

    return payload


def _resolve_objection_name(reframe_text: str) -> str:
    """The persuasion.objection field carries the reframe pattern, not the name.
    Re-derive the objection name from the library by matching the pattern text.
    """
    from conversion.libraries import objection_library
    for name, cfg in objection_library()["objections"].items():
        if cfg.get("reframe_pattern") == reframe_text:
            return name
    return "necessity"


def _downstream_instructions(brief: StrategicBrief) -> dict[str, Any]:
    """Instructions the generation phases MUST follow when they consume the brief.

    Emits BOTH the descriptive keys (must_include_in_caption / must_avoid_in_caption)
    and shorter aliases (must_include / must_avoid) that downstream code uses.
    """
    must_include = [
        f"the persona pain: {brief.persuasion.problem}",
        f"the desired outcome: {brief.persuasion.desire}",
        f"a proof point: {brief.persuasion.proof}",
    ]
    must_avoid = [
        "manufactured urgency (unless verified promotion window)",
        "fabricated statistics",
        "invented testimonials",
        "banned openers",
    ]
    return {
        "must_include_in_caption": must_include,
        "must_avoid_in_caption": must_avoid,
        "must_include": must_include,
        "must_avoid": must_avoid,
        "narrative_order": brief.copy_framework,
        "visual_alignment": {
            "logic_principle": brief.logic_principle,
            "template_family": brief.creative_type,
            "transformation": f"{brief.persuasion.transformation_from} -> {brief.persuasion.transformation_to}",
        },
        "cta_pinned": brief.copy.cta,
    }
