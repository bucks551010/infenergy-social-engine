"""Carousel Director (Master Build §43-§46).

Turns a strategic content package into a coherent multi-slide narrative.
Each slide has a purpose, a reason-to-swipe, and structured on-image + caption
allocation. Deterministic — no LLM required.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Slide:
    index: int
    purpose: str
    reason_to_swipe: str
    headline: str
    body: str
    visual_type: str
    visual_direction: str


@dataclass
class Carousel:
    slide_count: int
    narrative_arc: str
    slides: list[Slide] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "slide_count": self.slide_count,
            "narrative_arc": self.narrative_arc,
            "slides": [
                {
                    "slide": s.index,
                    "purpose": s.purpose,
                    "reason_to_swipe": s.reason_to_swipe,
                    "headline": s.headline,
                    "body": s.body,
                    "visual_type": s.visual_type,
                    "visual_direction": s.visual_direction,
                }
                for s in self.slides
            ],
        }


_ARCS: dict[str, list[tuple[str, str]]] = {
    "hook_answer_explanation_example_takeaway": [
        ("hook", "why keep swiping"),
        ("answer", "get the direct answer"),
        ("explanation", "understand the mechanism"),
        ("example", "see how it applies"),
        ("takeaway", "one thing to remember"),
    ],
    "problem_why_what_happens_what_to_do": [
        ("problem", "recognize the problem"),
        ("why", "understand the cause"),
        ("what_happens", "see the consequence"),
        ("what_to_do", "know the action"),
    ],
    "myth_reality_explanation_implication": [
        ("myth", "recognize the myth"),
        ("reality", "see the truth"),
        ("explanation", "understand why"),
        ("implication", "know what changes"),
    ],
    "scenario_consequence_lesson": [
        ("scenario", "see yourself in this"),
        ("consequence", "understand the stakes"),
        ("lesson", "remember the takeaway"),
    ],
    "question_surprising_answer_why_application": [
        ("question", "get the question"),
        ("surprising_answer", "the answer"),
        ("why", "why it's true"),
        ("application", "how to use it"),
    ],
}


def build(
    *,
    info_structure: str,
    beat_content: dict[str, str],
    visual_type: str,
    visual_direction: str,
) -> Carousel:
    """Build a carousel following an information structure."""
    beats = _ARCS.get(info_structure) or _ARCS["hook_answer_explanation_example_takeaway"]
    slides: list[Slide] = []
    for idx, (beat, swipe_reason) in enumerate(beats, start=1):
        content = beat_content.get(beat, "").strip()
        if not content:
            # Skip empty beats — carousels use the fewest slides needed (§43)
            continue
        # Compact headline: first sentence
        head = content.split(".")[0][:110]
        body = content
        slides.append(
            Slide(
                index=idx,
                purpose=beat,
                reason_to_swipe=swipe_reason,
                headline=head,
                body=body,
                visual_type=visual_type,
                visual_direction=visual_direction,
            )
        )
    # Renumber so indices are contiguous
    for i, s in enumerate(slides, start=1):
        s.index = i
    arc = " → ".join(s.purpose for s in slides)
    return Carousel(slide_count=len(slides), narrative_arc=arc, slides=slides)


def is_valid_carousel(c: Carousel, *, max_slides: int) -> tuple[bool, list[str]]:
    """§44 swipe motivation + slide-count sanity."""
    problems: list[str] = []
    if c.slide_count == 0:
        problems.append("no slides")
    if c.slide_count > max_slides:
        problems.append(f"exceeds platform max_slides ({c.slide_count} > {max_slides})")
    if c.slide_count and not any(s.purpose in {"hook", "problem", "myth", "question", "scenario"} for s in c.slides):
        problems.append("no valid opening slide")
    for s in c.slides:
        if not s.reason_to_swipe:
            problems.append(f"slide {s.index} has no reason_to_swipe (§44)")
    return (not problems), problems
