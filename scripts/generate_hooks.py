from __future__ import annotations

import re
from typing import Any

from campaign_runtime import stable_text_hash

HOOK_CATEGORIES = [
    "scenario",
    "question",
    "common_mistake",
    "myth",
    "comparison",
    "checklist",
    "curiosity",
    "demonstration",
    "problem_recognition",
    "local_relevance",
    "business_continuity",
    "product_use_case",
]

GENERIC_BLOCKLIST = {
    "power up your life",
    "stay prepared",
    "energy when you need it",
    "don't get left in the dark",
}


def _normalize(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip().lower())


def _looks_generic(hook: str) -> bool:
    base = _normalize(hook)
    if base in GENERIC_BLOCKLIST:
        return True
    # Reject obvious emoji-heavy sales style.
    emoji_count = sum(1 for ch in hook if ord(ch) > 127)
    if emoji_count >= 4:
        return True
    return False


def _score_hook(hook: str, topic: str, product_name: str, audience_segment: str) -> dict[str, int]:
    h = hook.strip()
    low = h.lower()
    topic_words = [w for w in re.findall(r"[a-zA-Z]{4,}", topic.lower())]
    audience_words = [w for w in re.findall(r"[a-zA-Z]{4,}", audience_segment.lower())]
    product_words = [w for w in re.findall(r"[a-zA-Z]{4,}", product_name.lower())]

    clarity = 16 if len(h.split()) >= 6 else 10
    specificity = 16 if any(ch.isdigit() for ch in h) or any(w in low for w in ("outage", "bill", "runtime", "watt", "wh", "backup")) else 9
    audience_relevance = 16 if any(w in low for w in audience_words[:6]) else 10
    curiosity = 16 if "?" in h or any(w in low for w in ("most", "hidden", "mistake", "myth", "why")) else 10
    product_relevance = 16 if any(w in low for w in product_words[:4]) else 10
    natural_language = 16 if len(h) <= 140 and h.count("!") <= 1 else 9

    # Bonus for topical overlap
    overlap = sum(1 for w in set(topic_words[:8]) if w in low)
    specificity = min(20, specificity + min(4, overlap))

    return {
        "clarity": min(20, clarity),
        "specificity": min(20, specificity),
        "audience_relevance": min(20, audience_relevance),
        "curiosity": min(20, curiosity),
        "product_relevance": min(20, product_relevance),
        "natural_language": min(20, natural_language),
    }


def _infer_hook_family(hook: str) -> str:
    low = _normalize(hook)
    if "?" in hook or low.startswith("what") or low.startswith("how") or low.startswith("why"):
        return "question"
    if "myth" in low:
        return "myth"
    if "mistake" in low:
        return "common_mistake"
    if " vs " in low or "compare" in low:
        return "comparison"
    if "checklist" in low or low.startswith("before you buy"):
        return "checklist"
    if "if " in low or "imagine" in low:
        return "scenario"
    if "fit" in low and "plan" in low:
        return "product_use_case"
    return "curiosity"


def _dominant_recent_family(recent_hooks: list[str] | None) -> str:
    counts: dict[str, int] = {}
    for raw in (recent_hooks or [])[:8]:
        family = _infer_hook_family(str(raw or ""))
        counts[family] = counts.get(family, 0) + 1
    if not counts:
        return ""
    family, count = max(counts.items(), key=lambda kv: kv[1])
    return family if count >= 2 else ""


def _total_score(component_scores: dict[str, int], duplicate_penalty: int) -> int:
    total = sum(component_scores.values())
    return max(0, total - duplicate_penalty)


def _category_templates(topic: str, product_name: str) -> dict[str, list[str]]:
    return {
        "scenario": [
            f"If the grid went down tonight, would your current setup handle {topic.lower()}?",
            f"Imagine a 4-hour outage this week: what fails first in your home?",
        ],
        "question": [
            f"What is the one device you cannot lose power to during an outage?",
            f"Are you choosing backup power based on specs or guesswork?",
        ],
        "common_mistake": [
            "Most buyers compare battery size but ignore daily load reality.",
            "The most expensive backup-power mistake is buying by hype, not usage.",
        ],
        "myth": [
            "Myth: bigger numbers always mean better backup power.",
            "Myth: a single spec tells you everything about reliability.",
        ],
        "comparison": [
            "Spec sheet vs real-world usage: only one predicts outage performance.",
            f"Cost now vs outage cost later: which one are you actually optimizing?",
        ],
        "checklist": [
            "Before you buy: map loads, verify specs, confirm charging paths.",
            "3 checks before choosing your next backup-power system.",
        ],
        "curiosity": [
            "The hidden reason many backup systems disappoint in week one.",
            "Most people miss this one spec that changes real runtime outcomes.",
        ],
        "demonstration": [
            "Watch how load mapping changes the product decision in minutes.",
            "Real setup example: from random shopping to spec-matched backup.",
        ],
        "problem_recognition": [
            "Rising rates and outage risk expose weak home power plans.",
            "If your plan starts at checkout, it is probably already wrong.",
        ],
        "local_relevance": [
            "Severe-weather season is where weak power plans get expensive.",
            "Utility volatility makes preparedness a planning issue, not a panic issue.",
        ],
        "business_continuity": [
            "Business continuity starts with power continuity, not just insurance.",
            "Downtime costs are usually higher than buyers estimate.",
        ],
        "product_use_case": [
            f"Where does {product_name} fit in a practical outage plan?",
            f"Use-case first: when {product_name} is a fit and when it is not.",
        ],
    }


def select_hook(
    topic: str,
    product_name: str,
    audience_segment: str,
    recent_hook_hashes: set[str],
    recent_hooks: list[str] | None = None,
    preferred_hooks: list[str] | None = None,
) -> dict[str, Any]:
    templates = _category_templates(topic, product_name)
    candidates: list[dict[str, Any]] = []

    for category in HOOK_CATEGORIES:
        for text in templates.get(category, []):
            candidates.append({"hook": text.strip(), "hook_type": category})

    for text in (preferred_hooks or []):
        if text and text.strip():
            candidates.append({"hook": text.strip(), "hook_type": "curiosity"})

    scored: list[dict[str, Any]] = []
    dominant_family = _dominant_recent_family(recent_hooks)
    for row in candidates:
        hook = row["hook"]
        if _looks_generic(hook):
            continue
        component_scores = _score_hook(hook, topic, product_name, audience_segment)
        duplicate_penalty = 35 if stable_text_hash(hook) in recent_hook_hashes else 0
        family_penalty = 8 if dominant_family and row.get("hook_type") == dominant_family else 0
        total = _total_score(component_scores, duplicate_penalty)
        total = max(0, total - family_penalty)
        scored.append(
            {
                "hook": hook,
                "hook_type": row["hook_type"],
                "component_scores": component_scores,
                "score": total,
                "duplicate_penalty": duplicate_penalty,
                "family_penalty": family_penalty,
            }
        )

    if not scored:
        fallback = f"What is the one outage risk most homes overlook about {topic.lower()}?"
        return {
            "hook": fallback,
            "hook_type": "question",
            "component_scores": _score_hook(fallback, topic, product_name, audience_segment),
            "score": 60,
            "duplicate_penalty": 0,
        }

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored[0]
