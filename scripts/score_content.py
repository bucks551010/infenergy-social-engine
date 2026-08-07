from __future__ import annotations

import re
from typing import Any


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _has_numbers(text: str) -> bool:
    return bool(re.search(r"\b\d+(?:\.\d+)?\b", text or ""))


def _hashtags(text: str) -> int:
    return len(re.findall(r"#[A-Za-z0-9_]+", text or ""))


def score_content(content: dict[str, Any]) -> dict[str, Any]:
    """Compute a 100-point content score using requested weighted components."""

    wp = str(content.get("wp_content", ""))
    fb = str(content.get("fb_caption", ""))
    ig = str(content.get("ig_caption", ""))
    li = str(content.get("li_text", ""))
    funnel_stage = str(content.get("funnel_stage", "EDUCATION")).upper()
    hook = str(content.get("selected_hook", ""))
    cta = str(content.get("selected_cta", ""))
    product_name = str(content.get("product_name", ""))

    hook_strength = 20.0
    if len(hook.split()) < 6:
        hook_strength -= 5
    if not any(x in hook.lower() for x in ("?", "myth", "mistake", "hidden", "why", "how")):
        hook_strength -= 4
    if not _has_numbers(hook) and funnel_stage in ("DESIRE", "TRUST"):
        hook_strength -= 2

    audience_relevance = 15.0
    if "home" not in (fb + " " + ig + " " + wp).lower() and "business" not in (li + " " + wp).lower():
        audience_relevance -= 4

    usefulness = 15.0
    if len(wp) < 1000:
        usefulness -= 5
    if not _has_numbers(wp + fb + ig + li):
        usefulness -= 6

    platform_fit = 15.0
    if _hashtags(li) > 3:
        platform_fit -= 3
    if _hashtags(fb) > 8:
        platform_fit -= 3
    if _hashtags(ig) < 3:
        platform_fit -= 4

    product_message_fit = 10.0
    if product_name and product_name.lower() not in (wp + fb + ig + li).lower():
        product_message_fit -= 4

    specificity = 10.0
    if not _has_numbers(wp + fb + ig + li):
        specificity -= 5

    conversion_potential = 10.0
    if not cta.strip():
        conversion_potential -= 6
    if funnel_stage == "CONVERSION" and not any(x in cta.lower() for x in ("shop", "build", "book", "compare", "see")):
        conversion_potential -= 3

    brand_credibility = 5.0
    if any(x in (wp + fb + ig + li).lower() for x in ("guarantee", "100%", "instant")):
        brand_credibility -= 3

    component_scores = {
        "hook_strength": round(_clamp(hook_strength, 0, 20), 2),
        "audience_relevance": round(_clamp(audience_relevance, 0, 15), 2),
        "usefulness": round(_clamp(usefulness, 0, 15), 2),
        "platform_fit": round(_clamp(platform_fit, 0, 15), 2),
        "product_message_fit": round(_clamp(product_message_fit, 0, 10), 2),
        "specificity": round(_clamp(specificity, 0, 10), 2),
        "conversion_potential": round(_clamp(conversion_potential, 0, 10), 2),
        "brand_credibility": round(_clamp(brand_credibility, 0, 5), 2),
    }

    total = round(sum(component_scores.values()), 2)

    if total >= 82:
        decision = "approve"
    elif total >= 75:
        decision = "regenerate_once"
    else:
        decision = "reject"

    return {
        "total": total,
        "decision": decision,
        "component_scores": component_scores,
    }
