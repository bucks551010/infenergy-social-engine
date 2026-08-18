"""Independent, deterministic Reader Value and trust review for final content."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


_ROOT = Path(__file__).resolve().parents[2]
_VALUE_PATH = _ROOT / "data" / "marketing" / "human_truth" / "reader_value_criteria.json"
_TRUST_PATH = _ROOT / "data" / "marketing" / "human_truth" / "trust_behaviors.json"
_FEAR_TACTICS = (
    "act now before it's too late",
    "don't let your family suffer",
    "you can't afford to be unprepared",
    "guaranteed safety",
    "total protection",
    "never worry again",
    "fear will leave",
)
_HELPFUL_SIGNALS = ("how", "what", "check", "compare", "choose", "decide", "understand", "plan", "prioritize", "first")
_TRUST_SIGNALS = ("verified", "check", "depends", "limit", "need to know", "right fit", "may", "can", "cannot")
_REFRAME_SIGNALS = ("not just", "instead", "before", "first", "rather than", "the real question")


def _load_list(path: Path, key: str) -> list[dict[str, Any]]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        values = payload.get(key, []) if isinstance(payload, dict) else []
        return [value for value in values if isinstance(value, dict)]
    except (OSError, json.JSONDecodeError):
        return []


def _flatten(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(_flatten(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return " ".join(_flatten(item) for item in value)
    return str(value or "")


def _keywords(value: str) -> set[str]:
    return {
        word for word in re.findall(r"[a-z]{4,}", value.lower())
        if word not in {"with", "that", "this", "when", "what", "your", "from", "into", "they", "have"}
    }


def _has_any(text: str, signals: tuple[str, ...]) -> bool:
    return any(signal in text for signal in signals)


def review(*, strategy: dict[str, Any], copy: dict[str, Any], visual: dict[str, Any]) -> dict[str, Any]:
    """Assess reader value and trust without inventing customer facts or outcomes."""
    text = _flatten(copy).lower()
    visual_text = _flatten(visual).lower()
    human_connection = strategy.get("human_connection") if isinstance(strategy.get("human_connection"), dict) else {}
    creation_logic = human_connection.get("preemptive_creation_logic") if isinstance(human_connection.get("preemptive_creation_logic"), dict) else {}
    moment_world = human_connection.get("moment_world") if isinstance(human_connection.get("moment_world"), dict) else {}
    criteria = _load_list(_VALUE_PATH, "criteria")
    trust_behaviors = _load_list(_TRUST_PATH, "behaviors")
    fear_tactics = [phrase for phrase in _FEAR_TACTICS if phrase in text]
    weak_premise = not bool(strategy.get("customer_moment") and strategy.get("human_need") and strategy.get("benefit"))
    moment_terms = _keywords(" ".join(str(moment_world.get(key, "")) for key in ("person", "decision_state", "responsibility", "human_question")))
    text_terms = _keywords(text)
    moment_connection = bool(moment_terms & text_terms)
    has_human_context = bool(moment_world)
    scores = {
        "useful": 1.0 if _has_any(text, _HELPFUL_SIGNALS) else 0.0,
        "captivating": 1.0 if len(str(copy.get("hook", "")).split()) >= 4 and not fear_tactics else 0.0,
        "caring": 1.0 if (moment_connection if has_human_context else bool(strategy.get("customer_moment") and strategy.get("human_need"))) else 0.0,
        "for_them": 1.0 if ("?" in text or any(token in text for token in (" you ", " your ", "we ", "our "))) else 0.0,
        "trust_building": 1.0 if not fear_tactics and (not has_human_context or _has_any(text, _TRUST_SIGNALS)) else 0.0,
    }
    failed = [criterion_id for criterion_id, score in scores.items() if score < 0.6]
    trust_signal_ids: list[str] = []
    if scores["useful"]:
        trust_signal_ids.append("value_before_asking")
    if scores["trust_building"]:
        trust_signal_ids.append("never_overclaim")
    if "?" in text or _has_any(text, ("compare", "depends", "check")):
        trust_signal_ids.append("answer_hard_question")
    if _has_any(text, ("limit", "cannot", "depends", "may not")):
        trust_signal_ids.append("honest_limits")
    if fear_tactics:
        verdict = "DO_NOT_PUBLISH"
    elif weak_premise:
        verdict = "CHANGE_ANGLE"
    elif has_human_context and failed:
        verdict = "REVISE_COPY"
    else:
        verdict = "PASS"
    brain_signals = [signal for signal in _HELPFUL_SIGNALS + _REFRAME_SIGNALS if signal in text]
    heart_signals = sorted(moment_terms & text_terms)
    failure_patterns: list[str] = []
    if not scores["useful"]:
        failure_patterns.append("NO_BRAIN_MOVEMENT")
    if not scores["caring"]:
        failure_patterns.append("EMPTY_HUMAN_VALUE")
    if fear_tactics:
        failure_patterns.append("MANUFACTURED_FEAR")
    if has_human_context and not moment_connection:
        failure_patterns.append("VISUAL_DISCONNECT")
    human_brain = {
        "question": (creation_logic.get("before_generation", {}).get("brain_movement", {}) or {}).get("question", ""),
        "score": scores["useful"],
        "passed": bool(scores["useful"]),
        "evidence": brain_signals,
    }
    human_heart = {
        "question": (creation_logic.get("before_generation", {}).get("heart_after", {}) or {}).get("question", ""),
        "score": scores["caring"],
        "passed": bool(scores["caring"] and not fear_tactics),
        "evidence": heart_signals,
        "fear_tactics": fear_tactics,
    }
    return {
        "verdict": verdict,
        "reader_value_scores": scores,
        "reader_value_minimum": 0.6,
        "reader_value_criteria": [criterion.get("id", "") for criterion in criteria],
        "reader_value_failures": failed,
        "trust_signals": trust_signal_ids,
        "trust_behavior_ids": [behavior.get("id", "") for behavior in trust_behaviors],
        "human_brain": human_brain,
        "human_heart": human_heart,
        "preemptive_failure_patterns": failure_patterns,
        "preemptive_recovery_guidance": {
            "handling_rule": creation_logic.get("handling_rule", ""),
            "terminal_gate": False,
        },
        "fear_tactics": fear_tactics,
        "believable_situation": bool(strategy.get("customer_moment") and strategy.get("human_need")),
        "benefit_supports_outcome": bool(strategy.get("important_capability") and strategy.get("benefit") and strategy.get("human_outcome")),
        "natural": not fear_tactics,
        "copy_visual_same_idea": moment_connection and bool(moment_terms & _keywords(visual_text)),
        "evidence": {
            "moment_terms_matched": sorted(moment_terms & text_terms),
            "human_context_applied": has_human_context,
        },
    }