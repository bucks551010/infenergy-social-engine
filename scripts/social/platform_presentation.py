"""Platform-native copy presentation without changing strategy or claims."""

from __future__ import annotations

import re
from typing import Any


_GENERIC_ENGAGEMENT = ("what do you think", "tell us below", "would you use this")


def _sentences(text: str) -> list[str]:
    return [item.strip() for item in re.split(r"(?<=[.!?])\s+", text.strip()) if item.strip()]


def evaluate(caption: str, *, platform: str, visual_specs: list[str] | None = None) -> dict[str, Any]:
    text = str(caption or "").strip()
    words = re.findall(r"\b[\w'-]+\b", text)
    sentences = _sentences(text)
    hashtags = re.findall(r"#[A-Za-z0-9_]+", text)
    specs = [str(item).lower() for item in (visual_specs or []) if str(item).strip()]
    duplicate_specs = [item for item in specs if item and item in text.lower()]
    generic_bait = any(phrase in text.lower() for phrase in _GENERIC_ENGAGEMENT)
    density = "TOO_DENSE" if len(words) > {"facebook": 190, "instagram": 120, "linkedin": 260}.get(platform, 190) else "APPROPRIATE"
    return {
        "word_count": len(words),
        "sentence_count": len(sentences),
        "paragraph_count": len([line for line in text.split("\n\n") if line.strip()]),
        "average_sentence_length": round(len(words) / max(1, len(sentences)), 1),
        "hashtag_count": len(hashtags),
        "visual_information_load": specs,
        "caption_information_load": "high" if density == "TOO_DENSE" else "appropriate",
        "duplicate_information": duplicate_specs,
        "complementarity_score": 1.0 if not duplicate_specs else max(0.35, 1.0 - 0.15 * len(duplicate_specs)),
        "reading_burden": density,
        "generic_engagement_bait": generic_bait,
    }


def _compact_parts(components: dict[str, Any], platform: str) -> tuple[str, str, str, list[str]]:
    hook = str(components.get("logic_hook") or components.get("hook") or "").strip()
    situation = str(components.get("situation") or "").strip()
    bridge = str(components.get("logic_bridge") or components.get("info") or "").strip()
    benefit = str(components.get("benefit_fragment") or "").strip()
    product = str(components.get("product_name") or "this product").strip()
    cta = str(components.get("cta") or "Learn more").strip()
    specs = [str(item).strip() for item in (components.get("feature_bullets") or []) if str(item).strip()]
    context = bridge or situation
    payoff = f"{product} is supporting proof for that decision: {benefit}." if benefit else f"{product} is supporting proof for that decision."
    return hook, context, payoff, specs


def format_caption(components: dict[str, Any], *, platform: str) -> tuple[str, dict[str, Any]]:
    """Use one proof in copy; let a spec-carrying visual carry the rest."""
    hook, context, payoff, specs = _compact_parts(components, platform)
    cta = str(components.get("cta") or "Learn more").strip()
    if platform == "instagram":
        caption = "\n\n".join(filter(None, [hook, context, payoff, cta, "#PortablePower #Preparedness #TravelPower"]))
    elif platform == "linkedin":
        caption = "\n\n".join(filter(None, [hook, context, "The decision is less about accumulating specs and more about matching the supported job to the equipment you carry.", payoff, cta, "#PortablePower #Resilience #BusinessContinuity"]))
    else:
        caption = "\n\n".join(filter(None, [hook, context, payoff, cta, "#PortablePower #Preparedness #BackupPower"]))
    presentation = evaluate(caption, platform=platform, visual_specs=specs)
    presentation.update({
        "selected_hashtags": re.findall(r"#[A-Za-z0-9_]+", caption),
        "hashtag_reason": "selective category and use-case discovery",
        "platform_role": platform,
        "emoji_mode": "NONE",
        "decoration_decisions": ["whitespace: hierarchy", "cta_separation: visibility"],
        "presentation_critic": "PASS" if presentation["reading_burden"] == "APPROPRIATE" and not presentation["generic_engagement_bait"] else "REVISE",
    })
    return caption, presentation