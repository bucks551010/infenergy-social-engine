"""Awareness engine — Spec Section 5.

Classifies content into one of five awareness stages and exposes the
prioritize / avoid / preferred lists that constrain downstream choices.
"""

from __future__ import annotations

from typing import Any

from .libraries import awareness_levels

STAGES = ("UNAWARE", "PROBLEM_AWARE", "SOLUTION_AWARE", "PRODUCT_AWARE", "MOST_AWARE")

# Map the existing funnel taxonomy to the awareness taxonomy for continuity
# with campaign_runtime.py. When a run only has funnel_stage, this is the
# default awareness bucket.
FUNNEL_TO_AWARENESS_DEFAULT = {
    "ATTENTION": "PROBLEM_AWARE",
    "EDUCATION": "SOLUTION_AWARE",
    "DESIRE": "PRODUCT_AWARE",
    "TRUST": "PRODUCT_AWARE",
    "CONVERSION": "MOST_AWARE",
}


def stage_config(stage: str) -> dict[str, Any]:
    levels = awareness_levels()
    return levels.get(stage, levels["PROBLEM_AWARE"])


def classify_from_funnel(funnel_stage: str) -> str:
    return FUNNEL_TO_AWARENESS_DEFAULT.get((funnel_stage or "").upper(), "PROBLEM_AWARE")


def classify(
    funnel_stage: str,
    audience_awareness_hint: str | None = None,
    persona_default: str | None = None,
) -> str:
    """Pick the strongest awareness signal available.

    Priority: explicit hint > persona default > funnel-derived default.
    """
    if audience_awareness_hint and audience_awareness_hint.upper() in STAGES:
        return audience_awareness_hint.upper()
    if persona_default and persona_default.upper() in STAGES:
        return persona_default.upper()
    return classify_from_funnel(funnel_stage)


def preferred_copy_structures(stage: str) -> list[str]:
    return list(stage_config(stage).get("preferred_copy_structures", []))


def preferred_hook_categories(stage: str) -> list[str]:
    return list(stage_config(stage).get("preferred_hook_categories", []))


def preferred_cta_style(stage: str) -> str:
    return stage_config(stage).get("preferred_cta_style", "awareness")


def prioritize(stage: str) -> list[str]:
    return list(stage_config(stage).get("prioritize", []))


def avoid(stage: str) -> list[str]:
    return list(stage_config(stage).get("avoid", []))
