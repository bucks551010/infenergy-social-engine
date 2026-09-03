from __future__ import annotations

import re
from typing import Any

from consumer_life import validate_consumer_receipt

try:
    from campaign_runtime import has_explicit_cta_keyword
except Exception:  # pragma: no cover
    def has_explicit_cta_keyword(text: str) -> bool:
        low = str(text or "").lower()
        return any(
            k in low
            for k in (
                "shop",
                "buy",
                "build",
                "book",
                "compare",
                "see",
                "review",
                "get",
                "start",
                "message",
                "comment",
                "schedule",
                "call",
                "contact",
                "quote",
                "assessment",
                "checkout",
                "order",
            )
        )


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _has_numbers(text: str) -> bool:
    return bool(re.search(r"\b\d+(?:\.\d+)?\b", text or ""))


def _hashtags(text: str) -> int:
    return len(re.findall(r"#[A-Za-z0-9_]+", text or ""))


def _has_specificity_signal(text: str) -> bool:
    lower = str(text or "").lower()
    return _has_numbers(lower) or any(
        signal in lower
        for signal in (
            "verified",
            "check",
            "compare",
            "device load",
            "compatibility",
            "watt-hour",
            "right fit",
            "depends on",
            "prioritize",
        )
    )


def score_content(content: dict[str, Any], requested_platforms: list[str] | None = None) -> dict[str, Any]:
    """Score only the requested platforms, with native criteria per social environment."""

    consumer_qa = validate_consumer_receipt(content) if content.get("consumer_root") else {"passed": True, "errors": []}

    platform_posts = content.get("platform_posts", {}) if isinstance(content.get("platform_posts"), dict) else {}
    text_by_platform = {
        "wordpress": str(content.get("wp_content", "")),
        "facebook": str((platform_posts.get("facebook") or {}).get("caption") or content.get("fb_caption", "")),
        "instagram": str((platform_posts.get("instagram") or {}).get("caption") or content.get("ig_caption", "")),
        "linkedin": str((platform_posts.get("linkedin") or {}).get("caption") or content.get("li_text", "")),
    }
    platforms = {str(platform).strip().lower() for platform in (requested_platforms or []) if str(platform).strip()}
    if not platforms:
        platforms = {"wordpress", "facebook", "instagram", "linkedin"}
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

    def score_platform(platform: str) -> dict[str, Any]:
        text = text_by_platform.get(platform, "")
        lower = text.lower()
        audience_relevance = 15.0 if any(word in lower for word in ("home", "business", "travel", "outage", "work", "device")) else 11.0
        usefulness = 15.0
        if platform == "wordpress" and len(text) < 1000:
            usefulness -= 5
        platform_fit = 15.0
        native_checks: list[str] = []
        if platform == "facebook":
            native_checks.append("conversational_context")
            if len(text) < 180 or not ("?" in text or "comment" in lower or "share" in lower):
                platform_fit -= 3
            if _hashtags(text) > 8:
                platform_fit -= 3
        elif platform == "instagram":
            native_checks.append("visual_hook_and_saveability")
            if _hashtags(text) < 3:
                platform_fit -= 4
        elif platform == "linkedin":
            native_checks.append("professional_decision_support")
            if not any(word in lower for word in ("business", "professional", "continuity", "decision", "operations", "work", "planning")):
                platform_fit -= 4
            if _hashtags(text) > 3:
                platform_fit -= 3
        product_message_fit = 10.0 if not product_name or product_name.lower() in lower else 6.0
        specificity = 10.0 if _has_specificity_signal(text) else 5.0
        conversion_potential = 10.0 - (6.0 if not cta.strip() else 0.0) - (3.0 if funnel_stage == "CONVERSION" and not has_explicit_cta_keyword(cta) else 0.0)
        brand_credibility = 2.0 if any(word in lower for word in ("guarantee", "100%", "instant")) else 5.0
        components = {
            "hook_strength": round(_clamp(hook_strength, 0, 20), 2), "audience_relevance": round(_clamp(audience_relevance, 0, 15), 2),
            "usefulness": round(_clamp(usefulness, 0, 15), 2), "platform_fit": round(_clamp(platform_fit, 0, 15), 2),
            "product_message_fit": round(_clamp(product_message_fit, 0, 10), 2), "specificity": round(_clamp(specificity, 0, 10), 2),
            "conversion_potential": round(_clamp(conversion_potential, 0, 10), 2), "brand_credibility": round(_clamp(brand_credibility, 0, 5), 2),
        }
        total = round(sum(components.values()), 2)
        return {"platform": platform, "total": total, "decision": "approve" if total >= 82 else "regenerate_once" if total >= 75 else "reject", "component_scores": components, "native_checks": native_checks}

    platform_results = {platform: score_platform(platform) for platform in sorted(platforms)}
    total = round(sum(result["total"] for result in platform_results.values()) / len(platform_results), 2)
    component_scores = {key: round(sum(result["component_scores"][key] for result in platform_results.values()) / len(platform_results), 2) for key in next(iter(platform_results.values()))["component_scores"]}

    if not consumer_qa["passed"]:
        decision = "reject"
    elif total >= 82:
        decision = "approve"
    elif total >= 75:
        decision = "regenerate_once"
    else:
        decision = "reject"

    return {
        "total": total,
        "decision": decision,
        "component_scores": component_scores,
        "platform_results": platform_results,
        "consumer_receipt_qa": consumer_qa,
    }
