"""Copy intelligence (Master Build §18-§23, §37, §62, §64-§65, §67, §68).

Covers:
  * Hook engine (multi-candidate generation + scoring)
  * Hook-payoff contract enforcement (§19)
  * Information structure selection (§20)
  * Information density scoring (§21)
  * So-what enforcement (§22)
  * Memory anchor extraction (§23)
  * Humanness filter for copy (§62)
  * Tone range enforcement (§64)
  * CTA intelligence + fatigue (§67, §68)

All deterministic — no LLM required, so it can also serve as a
critic/gate over LLM-generated copy in later stages.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable

from . import libraries


# --- Hook engine (§18) ------------------------------------------------------


AI_SLOP_PATTERNS = (
    r"\bin today'?s fast[- ]paced world\b",
    r"\bgame[- ]changer\b",
    r"\brevolutionize\b",
    r"\bunlock (?:the|your)\b",
    r"\belevate (?:the|your)\b",
    r"\bever wondered\b",
    r"\blook no further\b",
    r"\bhere'?s the thing\b",
    r"\bthe truth is\b",
    r"\bbuckle up\b",
    r"\bat the end of the day\b",
    r"\blet me tell you\b",
    r"\btrust me\b",
    r"\byou won'?t believe\b",
    r"^\s*so,?\s+",
    r"—[^—]*—[^—]*—",  # too many em-dashes in one sentence
)


@dataclass
class HookCandidate:
    text: str
    family: str
    scores: dict[str, float] = field(default_factory=dict)
    total: float = 0.0


def _match_any(patterns: Iterable[str], text: str) -> bool:
    low = text.lower()
    return any(re.search(p, low) for p in patterns)


def humanness_score(text: str) -> float:
    """Return 0-1 humanness. 1.0 = very human; low = AI-slop detected."""
    if not text:
        return 0.0
    penalty = 0.0
    banned = libraries.hook_global_banned_openers()
    low = text.lower().strip()
    if any(low.startswith(b) for b in banned):
        penalty += 0.35
    if _match_any(AI_SLOP_PATTERNS, text):
        penalty += 0.4
    # forced enthusiasm
    if text.count("!") >= 2:
        penalty += 0.2
    # rhetorical question with no payoff signal
    if text.strip().endswith("?") and len(text.split()) <= 4:
        penalty += 0.15
    return max(0.0, 1.0 - penalty)


def _stopping_power(text: str) -> float:
    if not text:
        return 0.0
    words = text.split()
    length_bonus = 1.0 if 6 <= len(words) <= 22 else 0.6
    concreteness = 0.5
    if re.search(r"\b\d+(?:[.,]\d+)?\b", text):
        concreteness += 0.2
    if any(w in text.lower() for w in ("myth", "why", "reason", "actually", "quietly", "silently", "biggest")):
        concreteness += 0.15
    return min(1.0, 0.5 * length_bonus + 0.5 * concreteness)


def _specificity(text: str) -> float:
    if not text:
        return 0.0
    tokens = text.lower().split()
    specific = sum(1 for t in tokens if t.isdigit() or re.match(r"\d+", t))
    proper = sum(1 for t in text.split() if t[:1].isupper() and t.lower() not in {"the", "a", "an"})
    return min(1.0, 0.15 * specific + 0.05 * proper + 0.35)


def _curiosity(text: str) -> float:
    low = text.lower()
    hits = sum(1 for k in ("reason", "why", "how", "surprising", "overlooked", "quietly", "actually", "few people") if k in low)
    return min(1.0, 0.35 + 0.15 * hits)


def _believability(text: str) -> float:
    if _match_any((r"\bguarantee\b", r"\b100%\b", r"\bunlimited\b", r"\bmagic\b", r"\bmiracle\b"), text):
        return 0.4
    return 0.85


def score_hook(
    text: str,
    *,
    family: str,
    recent_hooks: Iterable[str] = (),
) -> HookCandidate:
    """Score a single hook candidate across 6 dimensions + humanness."""
    scores: dict[str, float] = {
        "stopping_power": _stopping_power(text),
        "specificity": _specificity(text),
        "curiosity": _curiosity(text),
        "believability": _believability(text),
        "humanness": humanness_score(text),
    }
    recent = {r.strip().lower() for r in recent_hooks if r}
    scores["originality"] = 0.3 if text.strip().lower() in recent else 0.9
    scores["family_fit"] = 0.85 if family in libraries.hook_families() else 0.5
    total = sum(scores.values()) / max(1, len(scores))
    return HookCandidate(text=text, family=family, scores=scores, total=total)


def generate_candidates(
    *,
    hook_stems: dict[str, list[str]],
    reader_job: str,
    recent_hooks: Iterable[str] = (),
) -> list[HookCandidate]:
    """Generate + score hook candidates from provided stems per family.

    ``hook_stems`` should map family_id → list of candidate hook strings.
    Callers provide these (either LLM-generated or hand-authored). This
    function is the scorer/selector, not the generator.
    """
    out: list[HookCandidate] = []
    fams = libraries.hook_families()
    for fam, texts in hook_stems.items():
        if fam not in fams:
            continue
        for t in texts:
            if not t:
                continue
            out.append(score_hook(t, family=fam, recent_hooks=recent_hooks))
    out.sort(key=lambda c: c.total, reverse=True)
    return out


def select_best_hook(candidates: list[HookCandidate]) -> HookCandidate | None:
    if not candidates:
        return None
    # Reject any candidate below minimum humanness bar
    surviving = [c for c in candidates if c.scores.get("humanness", 0) >= 0.55]
    ranked = surviving or candidates
    return ranked[0]


# --- Hook-payoff contract (§19) --------------------------------------------


def hook_strength(hook: str) -> float:
    """Cheap proxy: reuse hook scoring average."""
    return score_hook(hook, family="direct_value").total


def payoff_strength(body: str, *, hook: str = "") -> float:
    """Reward concrete numbers, specific nouns, and content that pays off the hook."""
    if not body:
        return 0.0
    score = 0.0
    if re.search(r"\b\d+(?:[.,]\d+)?\b", body):
        score += 0.2
    if len(body.split()) >= 25:
        score += 0.2
    if any(k in body.lower() for k in ("because", "the reason", "so", "which means", "here's why")):
        score += 0.2
    if hook:
        # If hook promises a mechanism ("why", "reason", "how"), body must contain it
        low_hook = hook.lower()
        if any(k in low_hook for k in ("why", "reason", "how", "what actually")):
            if any(k in body.lower() for k in ("because", "since", "the reason", "the mechanism")):
                score += 0.2
    score += 0.2  # baseline for having content
    return min(1.0, score)


def contract_ok(hook: str, body: str, *, tolerance: float = 0.15) -> tuple[bool, str]:
    """§19: reject when hook_strength > payoff_strength by more than tolerance."""
    hs = hook_strength(hook)
    ps = payoff_strength(body, hook=hook)
    if hs - ps > tolerance:
        return False, f"hook_strength ({hs:.2f}) > payoff_strength ({ps:.2f}) — rewrite"
    return True, f"contract OK (hs={hs:.2f}, ps={ps:.2f})"


# --- Information structures (§20) ------------------------------------------


INFORMATION_STRUCTURES: dict[str, list[str]] = {
    "hook_answer_explanation_example_takeaway": ["hook", "answer", "explanation", "example", "takeaway"],
    "problem_why_what_happens_what_to_do": ["problem", "why", "what_happens", "what_to_do"],
    "myth_reality_explanation_implication": ["myth", "reality", "explanation", "implication"],
    "scenario_consequence_lesson": ["scenario", "consequence", "lesson"],
    "question_surprising_answer_why_application": ["question", "surprising_answer", "why", "application"],
}


def structure_for(genre: dict[str, Any]) -> list[str]:
    """Return ordered beats for a genre's info structure."""
    struct_id = genre.get("info_structure", "hook_answer_explanation_example_takeaway")
    return INFORMATION_STRUCTURES.get(struct_id, INFORMATION_STRUCTURES["hook_answer_explanation_example_takeaway"])


# --- Information density (§21) ---------------------------------------------


_FILLER_TOKENS = {
    "basically", "literally", "essentially", "just", "very", "really",
    "actually",  # ok in headlines; penalize in body
    "somehow", "kind of", "sort of",
}


def density(text: str) -> float:
    """0-1 density: penalize filler; reward specific nouns."""
    if not text:
        return 0.0
    tokens = re.findall(r"\b\w+\b", text.lower())
    if not tokens:
        return 0.0
    fillers = sum(1 for t in tokens if t in _FILLER_TOKENS)
    total = len(tokens)
    filler_ratio = fillers / total
    numeric = sum(1 for t in tokens if t.isdigit())
    numeric_bonus = min(0.2, 0.02 * numeric)
    return max(0.0, min(1.0, 0.9 - 1.5 * filler_ratio + numeric_bonus))


# --- So-what engine (§22) --------------------------------------------------


def has_so_what(body: str) -> bool:
    """§22: body must connect fact → meaning."""
    if not body:
        return False
    low = body.lower()
    triggers = ("so ", "which means", "the reason", "because", "so that", "which is why", "meaning ")
    return any(t in low for t in triggers)


# --- Memory anchor (§23) --------------------------------------------------


def extract_memory_anchor(body: str, *, takeaway: str = "") -> str:
    """Pull the most memorable single-sentence takeaway.

    Rule-based: prefer explicit takeaway; else the shortest sentence
    containing a number or an imperative verb; else the first sentence.
    """
    if takeaway:
        return takeaway.strip()
    if not body:
        return ""
    sents = re.split(r"(?<=[.!?])\s+", body.strip())
    if not sents:
        return ""
    scored: list[tuple[float, str]] = []
    for s in sents:
        s = s.strip()
        if not s:
            continue
        length_score = 1.0 if 8 <= len(s.split()) <= 22 else 0.5
        specificity = 0.5
        if re.search(r"\b\d+(?:[.,]\d+)?\b", s):
            specificity += 0.25
        if any(v in s.lower() for v in ("store", "avoid", "check", "keep", "leave", "unplug", "measure")):
            specificity += 0.15
        scored.append((length_score + specificity, s))
    scored.sort(reverse=True)
    return scored[0][1] if scored else sents[0]


# --- Tone selection (§64, §65) --------------------------------------------


TONE_OPTIONS = (
    "curious", "helpful", "warm", "authoritative", "thoughtful",
    "direct", "playful", "analytical", "reflective", "urgent",
    "conversational", "surprising",
)


def tone_for(reader_job: str, emotional_driver: str) -> str:
    mapping = {
        "TEACH_ME": "thoughtful",
        "EXPLAIN_THIS": "analytical",
        "HELP_ME": "helpful",
        "WARN_ME": "direct",
        "PREPARE_ME": "authoritative",
        "SURPRISE_ME": "surprising",
        "MAKE_ME_THINK": "reflective",
        "MAKE_ME_CURIOUS": "curious",
        "START_A_CONVERSATION": "conversational",
        "GIVE_ME_CONFIDENCE": "warm",
    }
    return mapping.get(reader_job, "helpful")


# --- CTA intelligence + fatigue (§67, §68) --------------------------------


def choose_cta_type(
    *,
    genre: dict[str, Any],
    reader_job_config: dict[str, Any],
    recent_ctas: Iterable[str] = (),
) -> str:
    """Pick a CTA type respecting genre + reader_job + recency."""
    prefs: list[str] = list(reader_job_config.get("cta_preferences", []))
    prefs.extend(genre.get("cta_preferences", []))
    if not prefs:
        return "NO_CTA"
    recent = {c.strip() for c in recent_ctas if c}
    for cta in prefs:
        if cta not in recent:
            return cta
    # Fatigue fallback: everything recent — pick the least recent
    return prefs[-1]
