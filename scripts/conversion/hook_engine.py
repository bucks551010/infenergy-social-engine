"""Hook engine — Spec Section 11.

Generates multiple hook candidates and scores them across 8 criteria, then
picks the strongest. Purely rule-based so it works without LLM access; can
be seeded with LLM-generated candidates when Gemini is available.
"""

from __future__ import annotations

import re
from typing import Any

from .libraries import hook_categories


SCORING_CRITERIA = (
    "stopping_power",
    "audience_relevance",
    "specificity",
    "curiosity",
    "believability",
    "product_connection",
    "originality",
    "platform_fit",
)


def is_banned(text: str) -> bool:
    if not text:
        return True
    lowered = text.lower()
    banned = hook_categories().get("banned_openers", [])
    return any(phrase.lower() in lowered for phrase in banned)


def eligible_categories(awareness_stage: str, law_name: str) -> list[str]:
    categories = hook_categories()["categories"]
    out = []
    for name, cfg in categories.items():
        aware_fit = awareness_stage in cfg.get("awareness_fit", [])
        law_fit = law_name in cfg.get("law_fit", [])
        if aware_fit or law_fit:
            out.append(name)
    return out or list(categories.keys())


def score_hook(
    hook: str,
    audience_keywords: list[str] | None = None,
    product_name: str | None = None,
    recent_hooks: list[str] | None = None,
    platform: str = "facebook",
) -> dict[str, float]:
    """Score a hook 0-10 per criterion (spec §11). Returns dict + 'total' (0-80)."""
    if not hook or is_banned(hook):
        return {c: 0.0 for c in SCORING_CRITERIA} | {"total": 0.0}

    length = len(hook)
    words = hook.split()
    lowered = hook.lower()

    # stopping_power: length in a good range + presence of pattern-interrupt cues
    sp = 0.0
    if 40 <= length <= 140:
        sp += 5.0
    elif 20 <= length < 40 or 140 < length <= 200:
        sp += 3.0
    if any(k in lowered for k in ("mistake", "hidden", "before you", "most people", "why", "how ")):
        sp += 3.0
    if "?" in hook:
        sp += 2.0
    sp = min(sp, 10.0)

    # audience_relevance: keyword coverage
    kws = [k.lower() for k in (audience_keywords or [])]
    hits = sum(1 for k in kws if k and k in lowered)
    ar = min(2.5 * hits, 10.0) if kws else 5.0

    # specificity: numbers, named things, concrete nouns
    sc = 0.0
    if re.search(r"\d", hook):
        sc += 4.0
    if re.search(r"\b(hours?|minutes?|watts?|Wh|mAh|days?|percent|%)\b", hook, re.IGNORECASE):
        sc += 3.0
    if len(words) >= 6:
        sc += 3.0
    sc = min(sc, 10.0)

    # curiosity: open loops
    cu = 0.0
    if any(k in lowered for k in ("why", "how", "what", "the reason", "before you")):
        cu += 4.0
    if any(k in lowered for k in ("nobody tells you", "most people", "you might not")):
        cu += 3.0
    if "?" in hook:
        cu += 3.0
    cu = min(cu, 10.0)

    # believability: penalize superlatives / absolutes
    bel = 10.0
    for word in ("guaranteed", "100%", "instant", "revolutionary", "life-changing", "unmatched", "always"):
        if word in lowered:
            bel -= 3.0
    bel = max(bel, 0.0)

    # product_connection: does product name or category appear?
    pc = 0.0
    if product_name and product_name.lower() in lowered:
        pc += 6.0
    if any(k in lowered for k in ("power", "battery", "charge", "outage", "backup", "portable")):
        pc += 4.0
    pc = min(pc, 10.0)

    # originality: penalize similarity to recent hooks
    org = 10.0
    for r in (recent_hooks or []):
        if not r:
            continue
        overlap = _token_overlap(lowered, r.lower())
        if overlap > 0.6:
            org -= 6.0
        elif overlap > 0.4:
            org -= 3.0
    org = max(org, 0.0)

    # platform_fit
    pf = 5.0
    if platform == "instagram" and length <= 90:
        pf += 5.0
    elif platform == "linkedin" and 60 <= length <= 180:
        pf += 5.0
    elif platform == "facebook" and 50 <= length <= 200:
        pf += 5.0
    pf = min(pf, 10.0)

    scores = {
        "stopping_power": sp,
        "audience_relevance": ar,
        "specificity": sc,
        "curiosity": cu,
        "believability": bel,
        "product_connection": pc,
        "originality": org,
        "platform_fit": pf,
    }
    scores["total"] = round(sum(scores[c] for c in SCORING_CRITERIA), 2)
    return scores


def _token_overlap(a: str, b: str) -> float:
    ta = set(re.findall(r"[a-z]{3,}", a))
    tb = set(re.findall(r"[a-z]{3,}", b))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / max(len(ta | tb), 1)


def pick_best(
    candidates: list[str],
    audience_keywords: list[str] | None = None,
    product_name: str | None = None,
    recent_hooks: list[str] | None = None,
    platform: str = "facebook",
    min_total: float = 40.0,
) -> tuple[str, dict[str, float], list[dict[str, Any]]]:
    """Return (winner, winner_scores, all_scored) sorted best-first.
    Winner may be empty string if no candidate meets `min_total`.
    """
    scored: list[dict[str, Any]] = []
    for cand in candidates:
        s = score_hook(cand, audience_keywords, product_name, recent_hooks, platform)
        scored.append({"hook": cand, "scores": s})
    scored.sort(key=lambda x: x["scores"]["total"], reverse=True)
    if not scored:
        return "", {}, []
    top = scored[0]
    if top["scores"]["total"] < min_total:
        return "", top["scores"], scored
    return top["hook"], top["scores"], scored
