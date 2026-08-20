"""Platform-native copy presentation without changing strategy or claims."""

from __future__ import annotations

import re
from typing import Any


_GENERIC_ENGAGEMENT = ("what do you think", "tell us below", "would you use this")
_CONTRAST_MARKERS = ("traditional power bank", "power bank", "portable backup", "portable power station", " vs ", "versus")
_PLANNING_INSTRUCTION_PATTERNS = (
    r"\binvite (?:a |the )?(?:practical )?response\b",
    r"\badd (?:a )?cta\b",
    r"\binsert (?:the )?link\b",
    r"\bmention (?:the )?product\b",
    r"\buse (?:a )?concise hook\b",
    r"\binclude hashtags\b",
    r"\bencourage engagement\b",
    r"\badd (?:a )?practical question\b",
)
_HASHTAG_LIMITS = {"facebook": 5, "instagram": 8, "linkedin": 5}


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
        "category": ["PortablePower", "BackupPower", "MobilePower", "PowerOnTheGo", "PortableEnergy"],
        "use_case": [],
        "audience_situation": ["Preparedness", "PowerPreparedness"],
        "discovery": ["StayPowered", "EnergyIndependence", "PowerSolutions", "EverydayPower", "PowerPlanning", "PowerKnowledge", "EnergyAwareness"],
    }
    keyword_tags = {
        "battery": "BatteryEducation",
        "charging": "ChargingTips",
        "electrical": "ElectricalBasics",
        "grid": "PowerGrid",
        "education": "EnergyLiteracy",
        "phone": "MobileCharging",
        "laptop": "LaptopPower",
        "camera": "CameraGear",
        "drone": "DronePower",
        "travel": "TravelPower",
        "mobile work": "MobileWork",
        "mobile office": "MobileOffice",
        "remote work": "RemoteWork",
        "professional": "ProfessionalGear",
        "power bank": "PowerBank",
        "wall outlet": "AwayFromTheOutlet",
        "daily devices": "DeviceCharging",
        "outage": "PowerOutage",
        "off-grid": "OffGridPower",
        "emergency": "EmergencyPreparedness",
        "adventure": "AdventureReady",
    }
    for keyword, tag in keyword_tags.items():
        if keyword in text:
            categories["use_case"].append(tag)

    if platform == "linkedin":
        categories["discovery"].append("Resilience")

    tags: list[str] = []
    for values in categories.values():
        for value in values:
            if value and value not in tags:
                tags.append(value)
    return tags[:_HASHTAG_LIMITS.get(platform, 5)], categories


def _repair_unsupported_broad_claims(value: str) -> str:
    """Narrow common unsupported generalizations into safe decision guidance."""
    repaired = str(value or "")
    replacements = (
        (r"\bensures? real-world compatibility\b", "helps you compare published specifications with the device requirements"),
        (r"\bmost compact batteries fail\b", "compact batteries can miss the job when their published capacity or output does not match the device"),
        (r"\bkeeps? (?:your )?laptop running mid-flight\b", "can be compared with the laptop's published power requirements before travel"),
        (r"\bsustained energy for (?:your )?laptop mid-flight\b", "published capacity to compare with the laptop's requirements before travel"),
    )
    for pattern, replacement in replacements:
        repaired = re.sub(pattern, replacement, repaired, flags=re.IGNORECASE)
    return repaired


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


def _sales_meaning(specifications: list[str], use_case: str) -> list[str]:
    """Translate only recognizable published power facts into customer-safe meaning."""
    source = " ".join(specifications).lower()
    meanings: list[str] = []
    if "154wh" in source or "41,600mah" in source or "41600mah" in source:
        meanings.append(
            "154Wh (41,600mAh) gives you a compact stored-power reserve for compatible daily devices when an outlet is not nearby."
        )
    if "200w" in source or "110v" in source:
        meanings.append(
            "200W AC output and 110V access add a practical AC-power option for compatible small electronics you carry."
        )
    if not meanings:
        for item in specifications[:2]:
            meanings.append(f"Published detail: {item}. Compare it with the actual device and job before you buy.")
    return meanings


def _semantic_key(paragraph: str, product: str) -> str:
    lowered = paragraph.lower()
    if any(token in lowered for token in ("no practical plan", "without validating", "misses the job", "gets picked before", "weak setup")):
        return "pain"
    if lowered.startswith(("compare ", "map ", "review ", "build ", "see what")):
        return "decision_step"
    if _is_contrast(paragraph):
        return "contrast"
    if product and product.lower() in lowered:
        return "product"
    if any(token in lowered for token in ("154wh", "41,600mah", "41600mah", "200w", "110v", "spec")):
        return "proof"
    if any(token in lowered for token in ("laptop", "phone", "camera", "travel", "mobile work", "outage", "device")):
        return "use_case"
    return "context"


def _new_supporting_depth(source_parts: list[str], *, product: str, covered: set[str], cta: str) -> list[str]:
    """Keep source information only when it adds a new sales dimension."""
    depth: list[str] = []
    seen: set[str] = set(covered)
    for paragraph in source_parts:
        if paragraph.strip().lower() == cta.lower() or re.fullmatch(r"(?:#[A-Za-z0-9_]+\s*)+", paragraph):
            continue
        key = _semantic_key(paragraph, product)
        normalized = re.sub(r"[^a-z0-9]+", " ", paragraph.lower()).strip()
        if key in seen or normalized in seen:
            continue
        seen.add(key)
        seen.add(normalized)
        depth.append(paragraph)
    return depth


def _preserved_sales_depth(source_parts: list[str], *, cta: str) -> list[str]:
    """Retain source-backed use context that adds value beyond the core proof block."""
    markers = (
        "drone", "mobile office", "remote work", "photography", "camping",
        "adventure", "travel", "outage", "off-grid", "emergency", "vehicle",
        "backpack", "long commute", "daily carry",
    )
    candidates: list[tuple[int, int, str]] = []
    seen: set[str] = set()
    for paragraph_index, paragraph in enumerate(source_parts):
        for sentence in _sentences(paragraph):
            normalized = re.sub(r"[^a-z0-9]+", " ", sentence.lower()).strip()
            lowered = sentence.lower()
            if (
                not normalized
                or normalized in seen
                or sentence.strip().lower() == cta.lower()
                or re.fullmatch(r"(?:#[A-Za-z0-9_]+\s*)+", sentence.strip())
                or "key specs" in lowered
                or "why buyers choose" in lowered
                or _is_contrast(sentence)
            ):
                continue
            if any(marker in lowered for marker in markers):
                seen.add(normalized)
                device_value = sum(token in lowered for token in ("laptop", "phone", "camera", "drone", "electronics"))
                context_value = sum(marker in lowered for marker in markers)
                candidates.append((device_value * 10 + context_value, paragraph_index, sentence.strip()))
    return [sentence for _, _, sentence in sorted(candidates, key=lambda item: (-item[0], item[1]))[:3]]


def _layered_caption(
    *,
    platform: str,
    hook: str,
    product: str,
    benefit: str,
    use_case: str,
    proof_meanings: list[str],
    optional_depth: list[str],
    cta: str,
    hashtags: str,
    product_led: bool,
) -> tuple[str, int | None]:
    core = [hook]
    if product_led and product:
        product_value = f"Meet {product}: a portable charging backup that {benefit}."
        core.append(f"{product_value} {use_case}".strip())
    elif use_case:
        core.append(use_case)
    supporting = proof_meanings
    if platform == "instagram":
        supporting = proof_meanings[:1]
        optional_depth = optional_depth[:2]
    elif platform == "linkedin":
        core.append("For mobile teams and preparedness planners, the decision is whether the published capability matches the equipment that must remain available.")
    proof_block = ""
    if supporting:
        proof_block = "Key specs:\n" + "\n".join(f"- {item}" for item in supporting)
    body = ["\n\n".join(item for item in core if item), proof_block]
    if optional_depth:
        body.append("\n\n".join(optional_depth))
    body.extend([cta, hashtags])
    caption = "\n\n".join(item for item in body if item.strip())
    optional_start = len(re.findall(r"\b[\w'-]+\b", "\n\n".join(body[:2]))) + 1 if optional_depth else None
    return caption, optional_start


_INTERNAL_PUBLIC_COPY_PATTERNS = _PLANNING_INSTRUCTION_PATTERNS + (
    r"\breader job\b",
    r"\bdesired response\b",
    r"\bcontent mode\b",
    r"\bcommercial intensity\b",
    r"\bselected fact\b",
    r"\bevidence ready\b",
    r"\bremediation\b",
    r"\bgovernance\b",
    r"\bverified input\b",
    r"\bproduct-fit guidance\b",
    r"\bfor this topic\b",
    r"\bthe practical context\b",
    r"\bfor you, that means\b",
    r"\bhelp practical product-fit guidance\b",
    r"\ba practical power decision\b",
)


def _remove_internal_language(paragraph: str) -> str:
    """Remove only sentence-level planning language from public copy."""
    kept = [
        sentence for sentence in _sentences(paragraph)
        if not any(re.search(pattern, sentence, flags=re.IGNORECASE) for pattern in _INTERNAL_PUBLIC_COPY_PATTERNS)
    ]
    return " ".join(kept).strip()


def _normalized_paragraph(paragraph: str) -> str:
    return re.sub(r"\s+", " ", paragraph).strip().lower()


def _is_hashtag_paragraph(paragraph: str) -> bool:
    return bool(re.fullmatch(r"(?:#[A-Za-z0-9_]+\s*)+", paragraph.strip()))


def _presentation_priority(paragraph: str, product: str) -> int:
    lowered = paragraph.lower()
    numeric_specs = _numeric_proof_tokens(paragraph)
    if product and product.lower() in lowered:
        return 1
    if "key spec" in lowered or len(numeric_specs) >= 2:
        return 2
    if numeric_specs:
        return 3
    return 4


def _source_thoughts(paragraphs: list[str]) -> list[str]:
    """Expose sentence-level thoughts only when source paragraphs are dense."""
    thoughts: list[str] = []
    for paragraph in paragraphs:
        if re.search(r"(?m)^\s*\d+\.\s+\S+", paragraph):
            thoughts.append(paragraph)
            continue
        sentences = _sentences(paragraph)
        if len(sentences) < 3 and not any("👉" in sentence for sentence in sentences):
            thoughts.append(paragraph)
        else:
            thoughts.extend(sentences)
    return thoughts


def _group_supporting_thoughts(thoughts: list[str]) -> list[str]:
    """Create readable thought groups without shortening or rewriting source copy."""
    grouped: list[str] = []
    pending: list[str] = []
    for thought in thoughts:
        pending.append(thought)
        word_count = len(re.findall(r"\b[\w'-]+\b", " ".join(pending)))
        if len(pending) == 2 or word_count >= 55:
            grouped.append(" ".join(pending))
            pending = []
    if pending:
        grouped.append(" ".join(pending))
    return grouped


def _sentence(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text if text.endswith((".", "!", "?")) else f"{text}."


def _concise_public_detail(value: str, *, max_words: int = 35) -> str:
    cleaned = re.sub(r"&(?:amp|nbsp|quot|#39);", " ", str(value or ""), flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    words = cleaned.split()
    return " ".join(words[:max_words]).rstrip(" ,;:")


def _clean_public_fragment(value: str, *, max_words: int = 35) -> str:
    text = _concise_public_detail(value, max_words=max_words)
    return re.sub(r"\b(\w+)\s+\1\b", r"\1", text, flags=re.IGNORECASE).strip()


def _engagement_safe_text(value: str) -> str:
    cleaned = _repair_unsupported_broad_claims(str(value or "").strip())
    if re.search(
        r"\b(?:product|infenergy|shop|buy|purchase|specs?|compatibility|selected|link|risk score)\b",
        cleaned,
        flags=re.IGNORECASE,
    ):
        return ""
    return cleaned


def _benefit_opening(components: dict[str, Any], *, product_led: bool) -> list[str]:
    """Present approved customer benefit and human outcome before supporting detail."""
    if not product_led:
        return []
    product = str(components.get("product_name") or "").strip()
    benefit = str(components.get("benefit_fragment") or "").strip().rstrip(".")
    after_state = str(components.get("after_state") or components.get("emotional_outcome") or "").strip().rstrip(".")
    opening: list[str] = []
    if benefit:
        value = f"{product} {benefit}"
        opening.append(_sentence(f"✨ {value}"))
    if after_state and not after_state.lower().startswith(("remember:", "the takeaway:", "takeaway:")):
        opening.append(_sentence(after_state))
    return opening[:2]


def _product_sales_pyramid(
    components: dict[str, Any],
    *,
    platform: str,
    source_caption: str,
    cta: str,
) -> tuple[str, dict[str, Any]]:
    """Build product sales copy from approved component meaning in a fixed editorial hierarchy."""
    product = str(components.get("product_name") or "").strip()
    framework = components.get("editorial_framework") if isinstance(components.get("editorial_framework"), dict) else {}
    benefit = _repair_unsupported_broad_claims(str(components.get("benefit_fragment") or "").strip().rstrip("."))
    situation = _repair_unsupported_broad_claims(str(components.get("situation") or "").strip().rstrip("."))
    after_state = _repair_unsupported_broad_claims(str(components.get("after_state") or components.get("emotional_outcome") or "").strip().rstrip("."))
    why_it_matters = _repair_unsupported_broad_claims(str(components.get("why_it_matters") or "").strip().rstrip("."))
    use_case = _repair_unsupported_broad_claims(str(components.get("use_case_line") or "").strip().rstrip("."))
    info = _repair_unsupported_broad_claims(str(components.get("info") or components.get("logic_bridge") or "").strip().rstrip("."))
    product_connection = _repair_unsupported_broad_claims(str(components.get("product_connection") or "").strip().rstrip("."))
    transformation = _repair_unsupported_broad_claims(str(components.get("transformation") or "").strip().rstrip("."))
    specs = [
        str(spec).strip() for spec in (components.get("feature_bullets") or [])
        if _numeric_proof_tokens(str(spec))
    ]
    non_numeric_info = " ".join(
        sentence for sentence in _sentences(info)
        if not _numeric_proof_tokens(sentence)
    )
    non_numeric_info = _concise_public_detail(non_numeric_info)

    human_moment = _clean_public_fragment(str(framework.get("human_moment") or situation), max_words=30)
    if len(human_moment.split()) < 5:
        human_moment = ""
    current_belief = _concise_public_detail(str(framework.get("current_belief") or situation), max_words=24)
    desired_belief = _concise_public_detail(str(framework.get("desired_belief") or non_numeric_info), max_words=28)
    proposition = _concise_public_detail(str(framework.get("dominant_proposition") or benefit), max_words=24)
    mechanism = _concise_public_detail(str(framework.get("mechanism") or non_numeric_info), max_words=24)
    if specs and _numeric_proof_tokens(mechanism):
        mechanism = ""
    functional_change = _concise_public_detail(str(framework.get("functional_transformation") or transformation), max_words=24)
    emotional_change = _concise_public_detail(str(framework.get("emotional_transformation") or after_state), max_words=20)
    future_state = _concise_public_detail(str(framework.get("ownership_future_pacing") or why_it_matters), max_words=20)
    hook = _concise_public_detail(str(components.get("logic_hook") or components.get("hook") or human_moment), max_words=26)
    if desired_belief:
        desired_belief = desired_belief[0].upper() + desired_belief[1:]
        if desired_belief.lower().startswith(("how ", "what ", "why ", "when ", "where ", "which ", "who ")):
            desired_belief = desired_belief.rstrip(".?!") + "?"
    belief_shift = " ".join(filter(None, [
        _sentence(f"The common assumption: {current_belief}") if current_belief else "",
        _sentence(f"The better question: {desired_belief}") if desired_belief else "",
    ]))
    product_reveal = _sentence(f"That is where {product} fits: {proposition or benefit}")
    mechanism_line = _sentence(f"How it supports that shift: {mechanism}") if mechanism else ""
    spec_block = "⚡ Key specs\n" + "\n".join(f"• {spec}" for spec in specs) if specs else ""
    if specs and not non_numeric_info:
        non_numeric_info = "Compare the published capacity and output with the actual devices and job before choosing."
    education = " ".join(filter(None, [
        _sentence(f"How to read those specs: {non_numeric_info}") if non_numeric_info else "",
        _sentence(product_connection) if product_connection else "",
    ]))
    human_value = _sentence(transformation) if transformation else ""
    portfolio_tags, categories = _portfolio(components, platform, source_caption)
    source_tags = re.findall(r"#[A-Za-z0-9_]+", source_caption)
    selected_tags = list(dict.fromkeys(source_tags + [f"#{tag}" for tag in portfolio_tags]))[:_HASHTAG_LIMITS.get(platform, 5)]
    hashtag_line = " ".join(selected_tags)
    transformation_line = _sentence(_clean_public_fragment(
        " ".join(filter(None, [functional_change, emotional_change, future_state])),
        max_words=100,
    ))
    platform_depth = {
        "facebook": [hook, human_moment, belief_shift, product_reveal, mechanism_line, spec_block, education, transformation_line],
        "instagram": [hook, belief_shift, product_reveal, spec_block, transformation_line],
        "linkedin": [hook, human_moment, belief_shift, product_reveal, mechanism_line, education, spec_block, transformation_line],
    }
    paragraphs = platform_depth.get(platform, platform_depth["facebook"]) + [
        f"👉 {cta}" if cta else "",
        hashtag_line,
    ]
    refined = "\n\n".join(paragraph for paragraph in paragraphs if paragraph.strip())
    presentation = _above_fold(refined, components, platform)
    presentation.update({
        "sales_structure": [
            "human_moment", "current_belief", "desired_belief", "dominant_proposition",
            "product_fit", "mechanism", "verified_proof", "functional_transformation",
            "emotional_transformation", "ownership_future_pacing", "natural_response",
        ],
        "selected_hashtags": selected_tags,
        "hashtag_categories": categories,
        "hashtag_target_density": f"{_HASHTAG_LIMITS.get(platform, 5)} focused tags maximum",
        "spec_sales_intelligence": "PASS" if spec_block else "NOT_APPLICABLE",
        "optional_depth_present": bool(education or human_value),
        "optional_depth_start_word": len(re.findall(r"\b[\w'-]+\b", "\n\n".join(paragraphs[:5]))) + 1 if education or human_value else None,
        "semantic_layer_evidence": {
            "hook": hook,
            "human_moment": human_moment,
            "belief_shift": belief_shift,
            "product": product,
            "primary_benefit": proposition or str(components.get("benefit_fragment") or ""),
            "mechanism": mechanism,
            "human_outcome": transformation_line,
            "selected_proof": [spec_block] if spec_block else [],
            "education": education,
            "cta": cta,
        },
        "platform_expression": f"{platform}_benefit_led_product_sales_editorial",
        "reordered_for_priority": True,
    })
    return refined, presentation


def _engagement_editorial(
    components: dict[str, Any],
    *,
    platform: str,
    source_caption: str,
    cta: str,
) -> tuple[str, dict[str, Any]]:
    """Build product-free content around participation or useful teaching, never sales."""
    source_has_steps = bool(re.search(r"(?m)^\s*\d+\.\s+\S+", source_caption))
    framework = components.get("editorial_framework") if isinstance(components.get("editorial_framework"), dict) else {}
    stage = str(components.get("funnel_stage") or ("EDUCATION" if source_has_steps else "ATTENTION")).strip().upper()
    hook = _engagement_safe_text(
        str(components.get("logic_hook") or components.get("hook") or "").strip()
    )
    situation = _engagement_safe_text(str(components.get("situation") or "").strip())
    insight = _engagement_safe_text(
        str(components.get("logic_bridge") or components.get("info") or "").strip()
    )
    why = _engagement_safe_text(
        str(components.get("why_it_matters") or components.get("why") or "").strip()
    )
    transformation = _engagement_safe_text(str(components.get("transformation") or "").strip())
    situation = _engagement_safe_text(str(framework.get("human_reality") or situation)) or "Most households know preparation matters, but priorities often remain unranked until normal routines are interrupted."
    tension = _engagement_safe_text(str(framework.get("tension") or why))
    curiosity = _engagement_safe_text(str(framework.get("curiosity") or hook))
    insight = _engagement_safe_text(str(framework.get("insight") or insight)) or "Start with the people and daily responsibilities that cannot simply pause, then name the first need you would protect."
    perspective = _engagement_safe_text(str(framework.get("infenergy_perspective") or why))
    story = _engagement_safe_text(str(framework.get("story") or ""))
    memory = _engagement_safe_text(str(framework.get("memory") or transformation)) or "One clear priority is the beginning of a plan the household can actually use."
    why = tension or perspective or "A specific answer turns a vague concern into a decision you can discuss and improve."
    transformation = memory

    if stage == "EDUCATION":
        if source_has_steps:
            source_lines = [line.strip() for line in source_caption.splitlines() if line.strip()]
            source_hook = next((line for line in source_lines if not re.match(r"^\d+\.\s+", line)), hook)
            actions = [line for line in source_lines if re.match(r"^\d+\.\s+", line)]
            hook = source_hook
        else:
            action_source = [value for value in (situation, insight, why) if value]
            actions = [
                _sentence(f"{index}. {value}")
                for index, value in enumerate(action_source[:3], start=1)
            ]
            while len(actions) < 3:
                defaults = (
                    "Name what must remain available",
                    "Compare the requirement with verified information",
                    "Decide what you will change before the need becomes urgent",
                )
                actions.append(_sentence(f"{len(actions) + 1}. {defaults[len(actions)]}"))
        final_cta = cta if cta and not re.search(r"\b(?:shop|buy|product|specs?|link|tap|score|seconds?)\b", cta, flags=re.IGNORECASE) else "Save this framework for your next planning check."
        paragraphs = [
            curiosity or hook,
            _sentence(situation),
            _sentence(f"The tension: {why}"),
            "A practical way to use this:\n" + "\n".join(actions),
            _sentence(f"Infenergy's perspective: {perspective or insight}"),
            "" if re.search(r"\bremember:", source_caption, flags=re.IGNORECASE) else _sentence(f"Remember: {transformation}"),
            f"👉 {final_cta}",
        ]
        structure = [
            "useful_knowledge_hook",
            "why_the_lesson_matters",
            "three_step_actionable_framework",
            "memorable_takeaway",
            "save_or_share_action",
            "focused_discovery",
        ]
        ideology = "teach_for_capability_without_forcing_a_sale"
        base_tags = ["#PowerKnowledge", "#Preparedness", "#EnergyLiteracy"]
    else:
        if hook.endswith("?"):
            question = hook
        elif hook:
            question = f"What changes when you take this seriously: {hook.rstrip('.')}?"
        else:
            question = "When normal power disappears, what is the first part of daily life you would protect?"
        final_cta = cta if cta and not re.search(r"\b(?:shop|buy|product|specs?|link|tap|score|seconds?)\b", cta, flags=re.IGNORECASE) else "Share the first priority you would protect and why."
        paragraphs = [
            curiosity or question,
            _sentence(situation),
            _sentence(f"The real tension: {why}"),
            _sentence(f"A better way to frame it: {insight}"),
            _sentence(story) if story else "",
            "" if re.search(r"\bremember:", source_caption, flags=re.IGNORECASE) else _sentence(f"Remember: {transformation}"),
            f"👉 {final_cta}",
        ]
        structure = [
            "human_pattern_interrupt",
            "relatable_tension",
            "fresh_reframe",
            "personal_stakes",
            "specific_participation_prompt",
            "focused_discovery",
        ]
        ideology = "earn_participation_through_relevance_not_bait"
        base_tags = ["#PowerPreparedness", "#EverydayPower", "#Preparedness"]

    selected_tags = base_tags[:_HASHTAG_LIMITS.get(platform, 5)]
    refined = "\n\n".join(part for part in paragraphs if part.strip())
    if selected_tags:
        refined = f"{refined}\n\n{' '.join(selected_tags)}"
    presentation = _above_fold(refined, components, platform)
    presentation.update({
        "engagement_structure": structure,
        "content_ideology": ideology,
        "selected_hashtags": selected_tags,
        "hashtag_categories": {"engagement": selected_tags},
        "hashtag_target_density": f"{_HASHTAG_LIMITS.get(platform, 5)} focused tags maximum",
        "optional_depth_present": True,
        "spec_sales_intelligence": "NOT_APPLICABLE",
        "semantic_layer_evidence": {
            "hook": curiosity or hook,
            "human_context": situation,
            "tension": tension,
            "insight": insight,
            "perspective": perspective,
            "story": story,
            "memory": memory,
            "cta": final_cta,
        },
        "platform_expression": f"{platform}_{stage.lower()}_engagement_editorial",
        "reordered_for_priority": True,
    })
    return refined, presentation


def refine_caption(
    caption: str,
    *,
    components: dict[str, Any],
    platform: str,
    product_led: bool = True,
    include_proof: bool = True,
) -> tuple[str, dict[str, Any]]:
    """Reorder approved public copy without creating or summarizing its meaning."""
    source_parts = _paragraphs(caption)
    product = str(components.get("product_name") or "").strip()
    cta = str(components.get("cta") or "Learn more").strip()
    source_has_steps = bool(re.search(r"(?m)^\s*\d+\.\s+\S+", caption))
    if re.search(r"\b(?:checklist|plan|steps)\b", cta, flags=re.IGNORECASE) and not source_has_steps:
        cta = "Review the verified product details." if product_led else "Save this guidance for your next planning session."
    if product_led and product and str(components.get("benefit_fragment") or "").strip():
        return _product_sales_pyramid(
            components,
            platform=platform,
            source_caption=caption,
            cta=cta,
        )
    if not product_led:
        return _engagement_editorial(
            components,
            platform=platform,
            source_caption=caption,
            cta=cta,
        )
    benefit_opening = _benefit_opening(components, product_led=product_led)
    opening_keys = {_normalized_paragraph(part) for part in benefit_opening}
    tags: list[str] = []
    sanitized_parts: list[str] = []
    seen: set[str] = set()
    for source_part in source_parts:
        if _is_hashtag_paragraph(source_part):
            tags.extend(re.findall(r"#[A-Za-z0-9_]+", source_part))
            continue
        sanitized = source_part if re.search(r"(?m)^\s*\d+\.\s+\S+", source_part) else _remove_internal_language(source_part)
        sanitized = _repair_unsupported_broad_claims(sanitized)
        normalized = _normalized_paragraph(sanitized)
        if sanitized.startswith("⚡ Key specs"):
            continue
        if sanitized and normalized and normalized not in seen and normalized not in opening_keys:
            seen.add(normalized)
            sanitized_parts.append(sanitized)

    body = _source_thoughts(sanitized_parts)
    normalized_cta = _normalized_paragraph(cta)
    body = [
        part for part in body
        if not (
            "👉" in part
            and _normalized_paragraph(re.sub(r"^(?:\s*👉\s*)+", "", part)) != normalized_cta
        )
    ]

    approved_specs = [
        str(spec).strip() for spec in (components.get("feature_bullets") or [])
        if _numeric_proof_tokens(str(spec))
    ]
    spec_block = ""
    if approved_specs:
        spec_block = "⚡ Key specs\n" + "\n".join(f"• {spec}" for spec in approved_specs)
        proof_deduped_body: list[str] = []
        for part in body:
            if not _numeric_proof_tokens(part):
                proof_deduped_body.append(part)
                continue
            proof_deduped_body.extend(
                sentence for sentence in _sentences(part)
                if not _numeric_proof_tokens(sentence) and "key specs" not in sentence.lower()
            )
        body = proof_deduped_body

    cta_parts = [
        part for part in body
        if normalized_cta
        and _normalized_paragraph(re.sub(r"^(?:\s*👉\s*)+", "", part)) == normalized_cta
    ]
    non_cta_parts = [part for part in body if part not in cta_parts]
    if non_cta_parts:
        hook, remaining = non_cta_parts[0], non_cta_parts[1:]
        prioritized = sorted(
            remaining,
            key=lambda part: _presentation_priority(part, product),
        )
        lead = prioritized[:1]
        supporting = _group_supporting_thoughts(prioritized[1:])
        ordered = benefit_opening + [hook] + lead + ([spec_block] if spec_block else []) + supporting
    else:
        ordered = benefit_opening + ([spec_block] if spec_block else [])
    ordered.extend(f"👉 {re.sub(r'^(?:\s*👉\s*)+', '', part).strip()}" for part in cta_parts)
    if cta and not cta_parts:
        ordered.append(f"👉 {cta}")
    portfolio_tags, categories = _portfolio(components, platform, caption)
    selected_tags = list(dict.fromkeys(tags + [f"#{tag}" for tag in portfolio_tags]))[:_HASHTAG_LIMITS.get(platform, 5)]
    hashtag_line = " ".join(selected_tags)
    refined = "\n\n".join(ordered + ([hashtag_line] if hashtag_line else []))
    refined = re.sub(r"(?m)^\s+(👉)", r"\1", refined)
    refined = re.sub(r"(?<!\n)\n👉", "\n\n👉", refined)
    optional_start = len(re.findall(r"\b[\w'-]+\b", "\n\n".join(ordered[:3]))) + 1 if len(ordered) > 3 else None
    presentation = _above_fold(refined, components, platform)
    presentation.update({
        "priority_layers": ["customer_benefit", "human_outcome", "hook", "product_and_proof", "supporting_depth", "action", "discovery"],
        "contrast_explained": False,
        "contrast_paragraph_count": 0,
        "selected_hashtags": selected_tags,
        "hashtag_categories": categories,
        "hashtag_target_density": f"{_HASHTAG_LIMITS.get(platform, 5)} focused tags maximum",
        "hashtag_relevance_score": 1.0 if selected_tags else 0.0,
        "hashtag_reason": "existing tags plus brand, product, category, and stated copy context",
        "optional_depth_present": len(ordered) > 3,
        "optional_depth_start_word": optional_start,
        "spec_sales_intelligence": "PASS" if spec_block or any(_numeric_proof_tokens(part) for part in ordered) else "NOT_APPLICABLE",
        "semantic_layer_evidence": {
            "hook": hook if non_cta_parts else "",
            "product": product,
            "primary_benefit": str(components.get("benefit_fragment") or ""),
            "human_outcome": str(components.get("emotional_outcome") or ""),
            "device_use_case": "",
            "selected_proof": [part for part in ordered if _numeric_proof_tokens(part)],
            "optional_depth": ordered[1:],
            "cta": cta,
        },
        "reordered_for_priority": bool(ordered),
        "platform_expression": {
            "facebook": "source_preserving_priority_editorial",
            "instagram": "source_preserving_priority_editorial",
            "linkedin": "source_preserving_priority_editorial",
        }.get(platform, "source_preserving_priority_editorial"),
    })
    return refined, presentation


def format_reel_caption(components: dict[str, Any], instagram_presentation: dict[str, Any]) -> str:
    """Keep Reel depth in the caption without transcribing its on-screen sequence."""
    product = str(components.get("product_name") or "").strip()
    use_case = str(components.get("use_case_line") or "").strip()
    cta = str(components.get("cta") or "Learn more").strip()
    tags = " ".join(instagram_presentation.get("selected_hashtags") or [])
    context = "A quick top-up is not always the whole job. Compare the published capacity, AC access, and supported device fit before you choose what to carry."
    return "\n\n".join(part for part in [
        f"{product} is for planning beyond the nearest outlet." if product else "Plan beyond the nearest outlet.",
        context,
        use_case,
        cta,
        tags,
    ] if part)


def _sentences(text: str) -> list[str]:
    return [item.strip() for item in re.split(r"(?<=[.!?])\s+", text.strip()) if item.strip()]


def _word_position(text: str, phrase: str) -> int | None:
    words = re.findall(r"\b[\w'-]+\b", text.lower())
    needle = re.findall(r"\b[\w'-]+\b", phrase.lower())
    if not needle:
        return None
    for index in range(len(words) - len(needle) + 1):
        if words[index:index + len(needle)] == needle:
            return index + 1
    return None


def mobile_first_screen(caption: str, *, width_chars: int = 38, visible_lines: int = 8) -> dict[str, Any]:
    """Approximate the first phone viewport using deterministic text wrapping."""
    paragraphs = _paragraphs(caption)
    lines: list[str] = []
    for paragraph_index, paragraph in enumerate(paragraphs):
        words = paragraph.split()
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
            if current and len(candidate) > width_chars:
                lines.append(current)
                current = word
            else:
                current = candidate
        if current:
            lines.append(current)
        if paragraph_index < len(paragraphs) - 1:
            lines.append("")
    visible = lines[:visible_lines]
    nonblank = [line for line in visible if line]
    return {
        "visible_lines": visible,
        "visible_text": "\n".join(visible),
        "entry_point": paragraphs[0] if paragraphs else "",
        "entry_point_visible": bool(paragraphs and paragraphs[0].split() and paragraphs[0].split()[0] in " ".join(nonblank)),
        "breathing_room": "" in visible,
        "dense_first_screen": len(nonblank) >= visible_lines,
        "central_idea_chars": len(paragraphs[0]) if paragraphs else 0,
    }


def _internal_instruction_leaks(text: str, planning_instructions: list[str] | None = None) -> list[str]:
    lowered = text.lower()
    leaks = [pattern for pattern in _INTERNAL_PUBLIC_COPY_PATTERNS if re.search(pattern, lowered)]
    for instruction in planning_instructions or []:
        normalized = str(instruction or "").strip().lower()
        if normalized and len(normalized) >= 8 and normalized in lowered:
            leaks.append(normalized)
    return list(dict.fromkeys(leaks))


def _numeric_proof_tokens(value: str) -> list[str]:
    return re.findall(r"\b\d[\d,]*(?:\s*)(?:wh|mah|w|v)\b", value.lower())


def render_platform_caption(
    caption: str,
    *,
    destination_url: str,
    platform: str,
) -> str:
    """Render the one human-visible string stored, reviewed, and published."""
    paragraphs = _paragraphs(caption)
    tags = ""
    if paragraphs and re.fullmatch(r"(?:#[A-Za-z0-9_]+\s*)+", paragraphs[-1]):
        tags = paragraphs.pop()
    url = str(destination_url or "").strip()
    paragraphs = [paragraph for paragraph in paragraphs if paragraph.strip() != url]
    if url:
        paragraphs.append(url)
    if tags:
        paragraphs.append(tags)
    return "\n\n".join(paragraphs)


def evaluate(
    caption: str,
    *,
    platform: str,
    visual_specs: list[str] | None = None,
    components: dict[str, Any] | None = None,
    planning_instructions: list[str] | None = None,
) -> dict[str, Any]:
    text = str(caption or "").strip()
    words = re.findall(r"\b[\w'-]+\b", text)
    sentences = _sentences(text)
    hashtags = re.findall(r"#[A-Za-z0-9_]+", text)
    specs = [str(item).lower() for item in (visual_specs or []) if str(item).strip()]
    visible_proof = set(_numeric_proof_tokens(text))
    duplicate_specs = [item for item in specs if any(token in visible_proof for token in _numeric_proof_tokens(item))]
    generic_bait = any(phrase in text.lower() for phrase in _GENERIC_ENGAGEMENT)
    components = components or {}
    product = str(components.get("product_name") or "")
    benefit = str(components.get("benefit_fragment") or "")
    cta = str(components.get("cta") or "")
    leaks = _internal_instruction_leaks(text, planning_instructions)
    paragraph_word_counts = [len(re.findall(r"\b[\w'-]+\b", paragraph)) for paragraph in _paragraphs(text)]
    longest_paragraph = max(paragraph_word_counts, default=0)
    density = "TOO_DENSE" if longest_paragraph > 80 else "APPROPRIATE"
    first_screen = mobile_first_screen(text)
    return {
        "final_caption": text,
        "word_count": len(words),
        "sentence_count": len(sentences),
        "paragraph_count": len([line for line in text.split("\n\n") if line.strip()]),
        "longest_paragraph_words": longest_paragraph,
        "average_sentence_length": round(len(words) / max(1, len(sentences)), 1),
        "hashtag_count": len(hashtags),
        "visual_information_load": specs,
        "caption_information_load": "high" if density == "TOO_DENSE" else "appropriate",
        "reinforcing_proof": duplicate_specs,
        "duplicate_information": [],
        "complementarity_score": 1.0,
        "reading_burden": density,
        "generic_engagement_bait": generic_bait,
        "product_intro_position": _word_position(text, product),
        "primary_benefit_position": _word_position(text, benefit),
        "cta_position": _word_position(text, cta),
        "link_present": bool(re.search(r"https?://\S+", text)),
        "internal_instruction_leak": bool(leaks),
        "internal_instruction_leaks": leaks,
        "specs_present": duplicate_specs,
        "optional_depth_present": len(_paragraphs(text)) >= 5,
        "mobile_first_screen": first_screen,
    }


def final_caption_qa(
    caption: str,
    *,
    platform: str,
    components: dict[str, Any],
    planning_instructions: list[str] | None = None,
) -> dict[str, Any]:
    """Gate final public copy; planning language is never publishable text."""
    metrics = evaluate(
        caption,
        platform=platform,
        visual_specs=list(components.get("feature_bullets") or []),
        components=components,
        planning_instructions=planning_instructions,
    )
    numeric_proof_available = any(_numeric_proof_tokens(str(item)) for item in components.get("feature_bullets") or [])
    product_led = bool(str(components.get("product_id") or "").strip())
    plan_promised = bool(re.search(
        r"\b(?:\d+[- ](?:step|hour)|action plan|practical plan|checklist|priority list|these steps|steps:)\b",
        caption,
        flags=re.IGNORECASE,
    ))
    actionable_steps = len(re.findall(r"(?m)^\s*\d+\.\s+\S+", caption)) >= 3
    reasons: list[str] = []
    if metrics["internal_instruction_leak"]:
        reasons.append("internal_instruction_leak")
    if product_led and not metrics["product_intro_position"]:
        reasons.append("product_not_visible")
    if product_led and not metrics["primary_benefit_position"]:
        reasons.append("primary_value_not_visible")
    if plan_promised and not actionable_steps:
        reasons.append("promised_plan_missing_actionable_steps")
    if platform == "facebook" and numeric_proof_available and not metrics["specs_present"]:
        reasons.append("verified_proof_missing")
    if platform == "facebook" and not metrics["link_present"]:
        reasons.append("required_link_missing")
    if metrics["paragraph_count"] < 4:
        reasons.append("paragraph_structure_missing")
    if metrics["reading_burden"] == "TOO_DENSE":
        reasons.append("wall_of_text_paragraph")
    if not metrics["mobile_first_screen"]["entry_point_visible"]:
        reasons.append("mobile_entry_point_missing")
    if metrics["mobile_first_screen"]["dense_first_screen"]:
        reasons.append("mobile_first_screen_too_dense")
    return {
        "status": "PRESENTATION_READY" if not reasons else "REVISE_PRESENTATION",
        "reasons": reasons,
        "metrics": metrics,
    }


def _compact_parts(components: dict[str, Any], platform: str) -> tuple[str, str, str, list[str]]:
    hook = str(components.get("logic_hook") or components.get("hook") or "").strip()
    situation = str(components.get("situation") or "").strip()
    bridge = str(components.get("logic_bridge") or components.get("info") or "").strip()
    benefit = str(components.get("benefit_fragment") or "").strip()
    product = str(components.get("product_name") or "").strip()
    cta = str(components.get("cta") or "Learn more").strip()
    specs = [str(item).strip() for item in (components.get("feature_bullets") or []) if str(item).strip()]
    context = bridge or situation
    payoff = ""
    return hook, context, payoff, specs


def format_caption(components: dict[str, Any], *, platform: str) -> tuple[str, dict[str, Any]]:
    """Use one proof in copy; let a spec-carrying visual carry the rest."""
    hook, context, payoff, specs = _compact_parts(components, platform)
    cta = str(components.get("cta") or "Learn more").strip()
    supporting_depth: list[str] = []
    seen_depth = {_normalized_paragraph(value) for value in (hook, context) if value}
    benefit = _normalized_paragraph(str(components.get("benefit_fragment") or ""))
    for key in ("situation", "transformation", "why_it_matters", "info", "use_case_line", "product_connection", "proof"):
        value = str(components.get(key) or "").strip()
        normalized = _normalized_paragraph(value)
        if key == "proof" and not any(
            marker in normalized
            for marker in ("checked", "verified", "published", "compare", "supports", "because", "shows")
        ):
            continue
        if value and normalized and normalized not in seen_depth and normalized != benefit:
            seen_depth.add(normalized)
            supporting_depth.append(value)
    if platform == "instagram":
        caption = "\n\n".join(filter(None, [hook, context, payoff, *supporting_depth, cta, "#PortablePower #Preparedness #TravelPower"]))
    elif platform == "linkedin":
        caption = "\n\n".join(filter(None, [hook, context, *supporting_depth, "The decision is less about accumulating specs and more about matching the supported job to the equipment you carry.", payoff, cta, "#PortablePower #Resilience #BusinessContinuity"]))
    else:
        caption = "\n\n".join(filter(None, [hook, context, payoff, *supporting_depth, cta, "#PortablePower #Preparedness #BackupPower"]))
    product_led = bool(
        components.get("product_id")
        or (
            str(components.get("product_name") or "").strip()
            and str(components.get("benefit_fragment") or "").strip()
            and specs
        )
    )
    caption, priority = refine_caption(
        caption,
        components=components,
        platform=platform,
        product_led=product_led,
        include_proof=False,
    )
    presentation = evaluate(caption, platform=platform, visual_specs=specs)
    presentation.update({
        **priority,
        "platform_role": platform,
        "emoji_mode": "NONE",
        "decoration_decisions": ["whitespace: hierarchy", "cta_separation: visibility"],
        "presentation_critic": "PASS" if presentation["reading_burden"] == "APPROPRIATE" and not presentation["generic_engagement_bait"] else "REVISE",
    })
    return caption, presentation