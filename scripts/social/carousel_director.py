"""Carousel Director (Master Build §43-§46).

Turns a strategic content package into a coherent multi-slide narrative.
Each slide has a purpose, a reason-to-swipe, and structured on-image + caption
allocation. Deterministic — no LLM required.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


OFFICIAL_LOGO_URL = "https://infenergypower.com/wp-content/uploads/2023/08/cropped-IP-selected-logo-01-Badge.png"
DEFAULT_MORAL = "Preparation turns a warning into a chance to act."
DEFAULT_CTA = "GO TO INFENERGY"
DEFAULT_TAGLINE = "Stay powered. Stay connected. Stay ready."
DEFAULT_WEBSITE = "infenergypower.com"


@dataclass
class Slide:
    index: int
    purpose: str
    reason_to_swipe: str
    headline: str
    body: str
    visual_type: str
    visual_direction: str
    role: str = "STORY"
    logo_url: str = ""
    call_to_action: str = ""
    tagline: str = ""
    website: str = ""


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
                    "role": s.role,
                    "logo_url": s.logo_url,
                    "call_to_action": s.call_to_action,
                    "tagline": s.tagline,
                    "website": s.website,
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


def normalize_slide_dicts(
    slides: list[dict[str, Any]],
    *,
    title: str,
    moral: str = DEFAULT_MORAL,
    call_to_action: str = DEFAULT_CTA,
    tagline: str = DEFAULT_TAGLINE,
    website: str = DEFAULT_WEBSITE,
) -> list[dict[str, Any]]:
    """Add mandatory delivery framing to any Social carousel plan."""
    narrative = [
        dict(slide)
        for slide in slides
        if isinstance(slide, dict) and str(slide.get("role") or "STORY").upper() not in {"COVER", "FINALE"}
    ][:8]
    for slide in narrative:
        slide["role"] = "STORY"

    cover = {
        "role": "COVER",
        "purpose": "mission_cover",
        "beat": "Open with the mission cover",
        "headline": str(title or "INFENERGY MICRO MISSION").strip(),
        "body": "INFENERGY ORIGINAL | MICRO MISSION",
        "supporting": "ENTER THE MISSION",
        "on_image_text_hint": "ENTER THE MISSION",
    }
    finale = {
        "role": "FINALE",
        "purpose": "branded_moral_cta",
        "beat": "Close with the revelation, moral, and Infenergy call to action",
        "headline": "THE MISSION TRUTH",
        "body": str(moral or DEFAULT_MORAL).strip(),
        "supporting": "\n\n".join(
            value
            for value in (
                str(moral or DEFAULT_MORAL).strip(),
                str(call_to_action or DEFAULT_CTA).strip(),
                str(tagline or DEFAULT_TAGLINE).strip(),
                str(website or DEFAULT_WEBSITE).strip(),
            )
            if value
        ),
        "on_image_text_hint": str(call_to_action or DEFAULT_CTA).strip(),
        "call_to_action": str(call_to_action or DEFAULT_CTA).strip(),
        "tagline": str(tagline or DEFAULT_TAGLINE).strip(),
        "website": str(website or DEFAULT_WEBSITE).strip(),
        "logo_url": OFFICIAL_LOGO_URL,
    }
    framed = [cover, *narrative, finale]
    for index, slide in enumerate(framed, start=1):
        slide["slide"] = index
    return framed


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
    framed = normalize_slide_dicts(
        [
            {
                "purpose": slide.purpose,
                "reason_to_swipe": slide.reason_to_swipe,
                "headline": slide.headline,
                "body": slide.body,
                "visual_type": slide.visual_type,
                "visual_direction": slide.visual_direction,
            }
            for slide in slides
        ],
        title=slides[0].headline if slides else "INFENERGY MICRO MISSION",
        moral=slides[-1].body if slides else DEFAULT_MORAL,
    )
    framed_slides = [
        Slide(
            index=int(slide["slide"]),
            purpose=str(slide.get("purpose") or "story"),
            reason_to_swipe=str(slide.get("reason_to_swipe") or ("enter the mission" if slide["role"] == "COVER" else "visit Infenergy")),
            headline=str(slide.get("headline") or ""),
            body=str(slide.get("body") or ""),
            visual_type=str(slide.get("visual_type") or visual_type),
            visual_direction=str(slide.get("visual_direction") or visual_direction),
            role=str(slide["role"]),
            logo_url=str(slide.get("logo_url") or ""),
            call_to_action=str(slide.get("call_to_action") or ""),
            tagline=str(slide.get("tagline") or ""),
            website=str(slide.get("website") or ""),
        )
        for slide in framed
    ]
    arc = " → ".join(slide.purpose for slide in framed_slides)
    return Carousel(slide_count=len(framed_slides), narrative_arc=arc, slides=framed_slides)


def is_valid_carousel(c: Carousel, *, max_slides: int) -> tuple[bool, list[str]]:
    """§44 swipe motivation + slide-count sanity."""
    problems: list[str] = []
    if c.slide_count == 0:
        problems.append("no slides")
    if c.slide_count > max_slides:
        problems.append(f"exceeds platform max_slides ({c.slide_count} > {max_slides})")
    if c.slide_count and c.slides[0].role != "COVER":
        problems.append("first slide must be COVER")
    if c.slide_count and c.slides[-1].role != "FINALE":
        problems.append("last slide must be FINALE")
    if any(slide.role != "STORY" for slide in c.slides[1:-1]):
        problems.append("middle slides must be STORY")
    if c.slide_count and not any(s.purpose in {"hook", "problem", "myth", "question", "scenario"} for s in c.slides[1:-1]):
        problems.append("no valid opening slide")
    for s in c.slides:
        if not s.reason_to_swipe:
            problems.append(f"slide {s.index} has no reason_to_swipe (§44)")
    return (not problems), problems
