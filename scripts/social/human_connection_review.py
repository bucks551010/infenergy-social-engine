"""Independent post-production human-connection critic."""
from __future__ import annotations

from typing import Any


def review(*, strategy: dict[str, Any], copy: dict[str, Any], visual: dict[str, Any]) -> dict[str, Any]:
    text = " ".join(str(value) for value in copy.values()).lower()
    visual_text = " ".join(str(value) for value in visual.values()).lower()
    need = str(strategy.get("human_need", "")).lower()
    outcome = str(strategy.get("human_outcome", "")).lower()
    exploitative = any(word in text for word in ("fear", "panic", "shame", "guaranteed"))
    copy_match, visual_match = bool(need and need in text), bool(need and (need in visual_text or outcome in visual_text))
    weak_premise = not bool(strategy.get("customer_moment") and strategy.get("human_need") and strategy.get("benefit"))
    verdict = "DO_NOT_PUBLISH" if exploitative else "CHANGE_ANGLE" if weak_premise else "PASS" if copy_match and visual_match else "REVISE_BOTH" if not copy_match and not visual_match else "REVISE_COPY" if not copy_match else "REVISE_VISUAL"
    return {"verdict": verdict, "believable_situation": bool(strategy.get("customer_moment") and strategy.get("human_need")), "benefit_supports_outcome": bool(strategy.get("important_capability") and strategy.get("benefit") and outcome), "natural": not exploitative, "copy_visual_same_idea": copy_match and visual_match}