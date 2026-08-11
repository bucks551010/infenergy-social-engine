"""Conversion Quality Score — Spec Section 23.

18-factor 0-10 rubric normalized to 0-100. Complements (does NOT replace)
the existing 8-factor scorer in scripts/score_content.py. Both scores are
kept — score_content is the operational gate; CQS is the strategy audit.
"""

from __future__ import annotations

import re
from typing import Any

CRITERIA = (
    "hook_strength",
    "audience_relevance",
    "problem_clarity",
    "desire_strength",
    "feature_to_benefit_clarity",
    "mechanism_clarity",
    "emotional_resonance",
    "proof_strength",
    "credibility",
    "differentiation",
    "visual_stopping_power",
    "visual_hierarchy",
    "copy_design_alignment",
    "offer_strength",
    "cta_clarity",
    "platform_fit",
    "brand_consistency",
    "originality",
)

MAX_POINTS = 10.0 * len(CRITERIA)


def score(
    caption: str,
    hook: str,
    cta: str,
    brief_dict: dict[str, Any],
    hook_scores: dict[str, float] | None = None,
    visual_prompt: str = "",
    recent_captions: list[str] | None = None,
    verified_facts: list[str] | None = None,
) -> dict[str, Any]:
    """Return {'total': 0-100, 'component_scores': dict, 'band': str}."""
    persuasion = brief_dict.get("persuasion", {}) or {}
    scores: dict[str, float] = {}

    # 1. hook_strength: reuse hook engine total (0-80) rescaled to 0-10
    if hook_scores and "total" in hook_scores:
        scores["hook_strength"] = min(round(hook_scores["total"] / 8.0, 2), 10.0)
    else:
        scores["hook_strength"] = 5.0 if hook else 0.0

    # 2. audience_relevance
    aud = brief_dict.get("audience_id") or ""
    scores["audience_relevance"] = 7.0 if aud else 3.0

    # 3-4. problem_clarity + desire_strength: check persuasion block populated
    scores["problem_clarity"] = _fullness_score(persuasion.get("problem"))
    scores["desire_strength"] = _fullness_score(persuasion.get("desire"))

    # 5. feature_to_benefit_clarity
    if persuasion.get("feature") and persuasion.get("benefit"):
        scores["feature_to_benefit_clarity"] = 8.0
    elif persuasion.get("benefit"):
        scores["feature_to_benefit_clarity"] = 5.0
    else:
        scores["feature_to_benefit_clarity"] = 2.0

    # 6. mechanism_clarity
    scores["mechanism_clarity"] = _fullness_score(persuasion.get("mechanism"))

    # 7. emotional_resonance: primary driver present + a cue word in caption
    primary = brief_dict.get("emotional_driver_primary") or ""
    scores["emotional_resonance"] = 8.0 if primary else 4.0

    # 8. proof_strength
    proof = persuasion.get("proof") or ""
    if proof and any(w in (caption or "").lower() for w in proof.lower().split()[:4]):
        scores["proof_strength"] = 8.0
    elif proof:
        scores["proof_strength"] = 5.0
    else:
        scores["proof_strength"] = 2.0

    # 9. credibility: penalize red-flag words
    cred = 10.0
    red_flags = ("guaranteed", "100%", "instant", "revolutionary", "unlimited", "fastest")
    for f in red_flags:
        if f in (caption or "").lower():
            cred -= 2.5
    scores["credibility"] = max(cred, 0.0)

    # 10. differentiation
    if persuasion.get("transformation_from") and persuasion.get("transformation_to"):
        scores["differentiation"] = 8.0
    else:
        scores["differentiation"] = 5.0

    # 11-13. visuals
    if visual_prompt:
        scores["visual_stopping_power"] = 7.0
        scores["visual_hierarchy"] = 7.0 if len(visual_prompt) >= 40 else 4.0
        # copy/design alignment: shared logic principle name appears in visual prompt
        law = (brief_dict.get("logic_principle") or "").replace("_", " ")
        scores["copy_design_alignment"] = 8.0 if law and law in visual_prompt.lower() else 5.0
    else:
        scores["visual_stopping_power"] = 3.0
        scores["visual_hierarchy"] = 3.0
        scores["copy_design_alignment"] = 3.0

    # 14. offer_strength: presence of concrete outcome, no hype
    if persuasion.get("outcome"):
        scores["offer_strength"] = 7.0
    else:
        scores["offer_strength"] = 4.0

    # 15. cta_clarity
    if cta and 2 <= len(cta.split()) <= 8:
        scores["cta_clarity"] = 8.0
    elif cta:
        scores["cta_clarity"] = 5.0
    else:
        scores["cta_clarity"] = 0.0

    # 16. platform_fit — approximated by caption length window
    length = len(caption or "")
    scores["platform_fit"] = 8.0 if 200 <= length <= 1500 else 5.0

    # 17. brand_consistency
    scores["brand_consistency"] = 8.0

    # 18. originality: penalize overlap with recent captions
    org = 10.0
    for rc in (recent_captions or [])[:5]:
        if _overlap(caption, rc) > 0.5:
            org -= 3.0
    scores["originality"] = max(org, 0.0)

    total_points = sum(scores.values())
    normalized = round((total_points / MAX_POINTS) * 100.0, 1)
    return {
        "total": normalized,
        "component_scores": scores,
        "band": band(normalized),
        "max_points": MAX_POINTS,
    }


def band(total: float) -> str:
    if total >= 90:
        return "exceptional"
    if total >= 85:
        return "strong"
    if total >= 80:
        return "acceptable"
    return "improve"


def _fullness_score(text: str | None) -> float:
    if not text:
        return 2.0
    length = len(text)
    if length >= 40:
        return 8.0
    if length >= 15:
        return 5.0
    return 3.0


def _overlap(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    ta = set(re.findall(r"[a-zA-Z]{4,}", a.lower()))
    tb = set(re.findall(r"[a-zA-Z]{4,}", b.lower()))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / max(len(ta | tb), 1)
