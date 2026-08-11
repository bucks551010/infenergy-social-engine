"""Logic-law engine — Spec Section 2, Laws 1-5.

Selects one law per post based on awareness stage + audience + product signals,
then exposes the narrative template and guardrails the copy engine must follow.
"""

from __future__ import annotations

from typing import Any

from .libraries import logic_laws

LAW_IDS = ("contrapositive", "disjunctive", "double_implication", "symmetrical_equivalence", "result_traceability")


def all_laws() -> list[str]:
    return list(logic_laws().keys())


def law(name: str) -> dict[str, Any]:
    laws = logic_laws()
    return laws.get(name, laws["result_traceability"])


def eligible_for_stage(awareness_stage: str) -> list[str]:
    return [name for name, cfg in logic_laws().items() if awareness_stage in cfg.get("when_to_use", [])]


def select(
    awareness_stage: str,
    recent_law_ids: list[str] | None = None,
    explicit: str | None = None,
    product_has_verified_specs: bool = True,
    preferred: list[str] | None = None,
) -> str:
    """Choose a law. Prefer diversity over the last few posts.

    - If `explicit` is a valid law, honor it.
    - Prefer laws eligible for the awareness stage.
    - Avoid laws used in the last 3 posts if possible.
    - If product lacks verified specs, avoid double_implication and result_traceability.
    - If `preferred` (proven winners) contains an eligible non-recent law, prefer that.
    """
    if explicit and explicit in LAW_IDS:
        return explicit

    eligible = eligible_for_stage(awareness_stage) or list(LAW_IDS)

    if not product_has_verified_specs:
        eligible = [law for law in eligible if law not in ("double_implication", "result_traceability")] or eligible

    recent = set(recent_law_ids or [])
    fresh = [law for law in eligible if law not in recent]

    if preferred:
        pref_fresh = [law for law in preferred if law in fresh]
        if pref_fresh:
            return pref_fresh[0]
        pref_any = [law for law in preferred if law in eligible]
        if pref_any:
            return pref_any[0]

    pool = fresh or eligible
    return pool[0]


def narrative_template(law_name: str) -> list[str]:
    return list(law(law_name).get("narrative_template", []))


def guardrails(law_name: str) -> list[str]:
    return list(law(law_name).get("guardrails", []))


def visual_strategy(law_name: str) -> str:
    return law(law_name).get("visual_strategy", "")


def best_copy_structures(law_name: str) -> list[str]:
    return list(law(law_name).get("best_copy_structures", []))
