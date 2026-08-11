"""Emotion engine — Spec Section 3.

Selects ONE primary + optional secondary emotional driver per post. Falls
back to persona defaults, then awareness-stage defaults.
"""

from __future__ import annotations

from .libraries import emotional_drivers


def all_drivers() -> list[str]:
    return list(emotional_drivers()["drivers"].keys())


def is_valid(driver: str) -> bool:
    return driver in emotional_drivers()["drivers"]


def cues_for(driver: str) -> list[str]:
    return list(emotional_drivers()["drivers"].get(driver, {}).get("cues", []))


def select(
    persona_id: str | None,
    awareness_stage: str,
    explicit_primary: str | None = None,
    explicit_secondary: str | None = None,
    preferred: list[str] | None = None,
) -> tuple[str, str]:
    """Return (primary, secondary). secondary may be empty.

    If `preferred` (proven winners) contains a valid driver and no explicit
    primary is supplied, use the first preferred driver as primary.
    """
    lib = emotional_drivers()

    if explicit_primary and is_valid(explicit_primary):
        primary = explicit_primary
    elif preferred:
        pref_valid = [p for p in preferred if is_valid(p)]
        if pref_valid:
            primary = pref_valid[0]
        else:
            persona_default = lib["audience_default_drivers"].get(persona_id or "", {})
            primary = persona_default.get("primary") or _stage_first(awareness_stage) or "confidence"
    else:
        persona_default = lib["audience_default_drivers"].get(persona_id or "", {})
        primary = persona_default.get("primary") or _stage_first(awareness_stage) or "confidence"

    if explicit_secondary and is_valid(explicit_secondary) and explicit_secondary != primary:
        secondary = explicit_secondary
    else:
        persona_default = lib["audience_default_drivers"].get(persona_id or "", {})
        candidate = persona_default.get("secondary") or _stage_second(awareness_stage, primary)
        secondary = candidate if candidate and candidate != primary else ""

    return primary, secondary


def _stage_first(awareness_stage: str) -> str:
    stage_defaults = emotional_drivers()["awareness_default_drivers"].get(awareness_stage, [])
    return stage_defaults[0] if stage_defaults else ""


def _stage_second(awareness_stage: str, primary: str) -> str:
    stage_defaults = emotional_drivers()["awareness_default_drivers"].get(awareness_stage, [])
    for d in stage_defaults:
        if d != primary:
            return d
    return ""
