"""Platform-native copy presentation without changing strategy or claims."""

from __future__ import annotations

import re
from typing import Any


_GENERIC_ENGAGEMENT = ("what do you think", "tell us below", "would you use this")
_CONTRAST_MARKERS = ("traditional power bank", "power bank", "portable backup", "portable power station", " vs ", "versus")


def _paragraphs(text: str) -> list[str]:
    return [item.strip() for item in re.split(r"\n\s*\n", str(text or "").strip()) if item.strip()]


def _tag(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", str(value or ""))


def _is_contrast(paragraph: str) -> bool:
    lowered = paragraph.lower()
    return sum(marker in lowered for marker in _CONTRAST_MARKERS) >= 2


def _portfolio(components: dict[str, Any], platform: str, source: str) -> tuple[list[str], dict[str, list[str]]]:
    """Build only tags that are grounded in the product and stated use context."""
    product = _tag(str(components.get("product_name") or ""))
    text = " ".join((source, str(components.get("use_case_line") or ""))).lower()
    categories: dict[str, list[str]] = {
        "brand": ["InfenergyPower"],
        "product": [product] if product else [],
        "category": ["PortablePower", "BackupPower"],
        "use_case": [],
        "audience_situation": ["Preparedness"],
        "discovery": ["StayPowered"],
    }
    keyword_tags = {
        "laptop": "LaptopPower",
        "camera": "CameraGear",
        "travel": "TravelPower",
        "mobile work": "MobileWork",
        "outage": "PowerOutage",
        "emergency": "EmergencyPreparedness",
        "adventure": "AdventureReady",
    }
    for keyword, tag in keyword_tags.items():
        if keyword in text:
            categories["use_case"].append(tag)

    if platform == "linkedin":
        categories["discovery"] = ["Resilience"]
    elif "outage" not in text and "emergency" not in text:
        categories["audience_situation"] = []

    tags: list[str] = []
    for values in categories.values():
        for value in values:
            if value and value not in tags:
                tags.append(value)
    limit = 5 if platform == "linkedin" else 15
    return tags[:limit], categories


def _above_fold(caption: str, components: dict[str, Any], platform: str) -> dict[str, Any]:
    opening = " ".join(_paragraphs(caption)[:2])
    product = str(components.get("product_name") or "").strip()
    benefit = str(components.get("benefit_fragment") or "").strip()
    use_case = str(components.get("use_case_line") or "").strip()
    lowered = opening.lower()
    product_present = bool(product and product.lower() in lowered)
    benefit_present = bool(benefit and benefit.lower() in lowered)
    use_case_present = bool(use_case and use_case.lower() in lowered)
    return {
        "above_fold_hook": _paragraphs(caption)[0] if _paragraphs(caption) else "",
        "above_fold_product_presence": product_present,
        "above_fold_primary_benefit": benefit_present,
        "above_fold_use_case": use_case_present,
        "above_fold_value_complete": bool(product_present and benefit_present),
        "copy_depth_to_product": 1 if product_present else None,
        "platform": platform,
    }


def refine_caption(
    caption: str,
    *,
    components: dict[str, Any],
    platform: str,
    product_led: bool = True,
    include_proof: bool = True,
) -> tuple[str, dict[str, Any]]:
    """Put verified commercial value first while retaining useful source depth below it."""
    source_parts = _paragraphs(caption)
    source_without_tags = [part for part in source_parts if not re.fullmatch(r"(?:#[A-Za-z0-9_]+\s*)+", part)]
    kept_depth: list[str] = []
    contrast_explained = _is_contrast(str(components.get("logic_hook") or components.get("hook") or ""))
    for part in source_without_tags:
        if _is_contrast(part):
            if contrast_explained:
                continue
            contrast_explained = True
        kept_depth.append(part)

    product = str(components.get("product_name") or "").strip()
    benefit = str(components.get("benefit_fragment") or "").strip().rstrip(".")
    use_case = str(components.get("use_case_line") or "").strip()
    hook = str(components.get("logic_hook") or components.get("hook") or "").strip()
    proof = [str(item).strip() for item in (components.get("feature_bullets") or []) if str(item).strip()][:2]
    cta = str(components.get("cta") or "Learn more").strip()

    core: list[str] = []
    if hook:
        core.append(hook)
    if product_led and product:
        product_line = f"{product} is a portable backup option that {benefit}." if benefit else f"Meet {product}, a portable backup option."
        core.append(f"{product_line} {use_case}".strip())
    elif use_case:
        core.append(use_case)
    selected_proof = proof[:1] if platform == "instagram" else proof
    if selected_proof and include_proof:
        core.append("Key specs, translated: " + "; ".join(selected_proof) + ".")
    if platform == "linkedin":
        core.append("The professional decision is matching supported equipment to the actual job, not accumulating specifications.")

    core_text = " ".join(core).lower()
    optional_depth = [
        part for part in kept_depth
        if part.lower() not in core_text and part.strip().lower() != cta.lower()
    ]
    if platform == "instagram":
        optional_depth = [part for part in optional_depth if not _is_contrast(part)][:2]
    tags, categories = _portfolio(components, platform, caption)
    hashtag_line = " ".join(f"#{tag}" for tag in tags)
    refined = "\n\n".join(filter(None, ["\n\n".join(core), "\n\n".join(optional_depth), cta, hashtag_line]))
    presentation = _above_fold(refined, components, platform)
    presentation.update({
        "priority_layers": ["scroll_stopper", "product_core_value", "quick_proof", "optional_depth", "action_discovery"],
        "contrast_explained": contrast_explained,
        "contrast_paragraph_count": sum(1 for part in optional_depth if _is_contrast(part)),
        "selected_hashtags": [f"#{tag}" for tag in tags],
        "hashtag_categories": categories,
        "hashtag_target_density": "10-15 useful tags when sufficient relevant evidence exists" if platform in ("facebook", "instagram") else "3-5 selective professional tags",
        "hashtag_relevance_score": 1.0 if tags else 0.0,
        "hashtag_reason": "brand, product, category, verified use-case, and discovery tags only",
        "optional_depth_present": bool(optional_depth),
        "reordered_for_priority": product_led and bool(product),
        "platform_expression": {
            "facebook": "front_loaded_commercial_value_with_optional_depth",
            "instagram": "visual_first_mobile_scannable_caption",
            "linkedin": "professional_decision_support_editorial",
        }.get(platform, "priority_layered"),
    })
    return refined, presentation


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
    caption, priority = refine_caption(caption, components=components, platform=platform, include_proof=False)
    presentation = evaluate(caption, platform=platform, visual_specs=specs)
    presentation.update({
        **priority,
        "platform_role": platform,
        "emoji_mode": "NONE",
        "decoration_decisions": ["whitespace: hierarchy", "cta_separation: visibility"],
        "presentation_critic": "PASS" if presentation["reading_burden"] == "APPROPRIATE" and not presentation["generic_engagement_bait"] else "REVISE",
    })
    return caption, presentation