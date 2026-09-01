from __future__ import annotations

import re
import uuid
from datetime import date
from typing import Any


CREATE_INTENT = re.compile(r"\b(create|make|generate|build|produce|design|render)\b", re.I)
HERO_ALIASES = re.compile(r"\b(infenergy|the superhero|my superhero|our superhero|the hero|our hero|the character)\b", re.I)
INTEGRATED_TEXT = re.compile(r"\b(interact(?:ing)? with (?:the )?(?:words|text)|text physical|words physical|typography|message (?:is|as) part of the scene|says?\s+)", re.I)


def is_flagship_creative_command(message: str) -> bool:
    text = str(message or "").strip()
    return bool(CREATE_INTENT.search(text) and re.search(
        r"\b(post|visual|image|carousel|mission|quote|reel|poster|story|superhero|infenergy|typography|cards?|slides?)\b",
        text,
        re.I,
    ))


def _exact_text(message: str) -> list[str]:
    quoted = [next(item for item in match.groups() if item is not None).strip() for match in re.finditer(r'"([^"]{2,160})"|“([^”]{2,160})”|\'([^\']{2,160})\'', message)]
    says = re.search(
        r"\b(?:says?|reads?|words?)\s+([A-Z][A-Z0-9 ',.!?&-]{2,100}?)(?=$|\s+(?:and|with|while|where|have|show|for|on|as)\b)",
        message,
    )
    if says:
        quoted.append(says.group(1).strip(" ,"))
    return list(dict.fromkeys(item for item in quoted if item))


def _develop_quote(message: str) -> dict[str, Any]:
    match = re.search(r"\b(?:about|on)\s+([^.!?]{2,80})", message, re.I)
    theme = match.group(1).strip().lower() if match else ""
    library = {
        "momentum": ["MOMENTUM IS ENERGY WITH DIRECTION.", "DIRECTION TURNS EFFORT INTO MOMENTUM.", "ENERGY MOVES. PURPOSE DECIDES WHERE."],
        "resilience": ["DEPLETED DOESN'T MEAN FINISHED.", "RECOVERY IS POWER RETURNING WITH PURPOSE.", "WHAT BENDS CAN STILL CARRY ENERGY FORWARD."],
        "preparation": ["PREPARATION TURNS UNCERTAINTY INTO OPTIONS.", "READY IS A DECISION MADE BEFORE THE MOMENT.", "A PLAN IS STORED CONFIDENCE."],
        "connection": ["POWER MATTERS MOST WHEN IT KEEPS US CONNECTED.", "CONNECTION IS WHAT ENERGY MAKES POSSIBLE.", "KEEP THE CURRENT. KEEP THE CONNECTION."],
        "small steps": ["SMALL STEPS STILL MOVE YOU FORWARD.", "PROGRESS DOESN'T NEED TO ARRIVE AT FULL POWER.", "ONE DIRECTED STEP CHANGES THE DISTANCE."],
        "energy": ["THE DIRECTION OF YOUR ENERGY MATTERS AS MUCH AS THE AMOUNT.", "ENERGY BECOMES POWER WHEN PURPOSE GIVES IT A JOB.", "SPEND YOUR ENERGY WHERE IT CAN CHANGE THE OUTCOME."],
    }
    key = next((name for name in library if name in theme), "")
    if not key:
        rotation = ["energy", "connection", "preparation", "resilience", "momentum", "small steps"]
        key = rotation[date.today().toordinal() % len(rotation)]
    candidates = library[key]
    return {"theme": key, "candidates": candidates, "selected": candidates[0], "rejected_as_weaker": candidates[1:]}


def _slide_count(message: str, micro_mission: bool) -> int:
    match = re.search(r"\b(\d{1,2})\s*(?:card|slide)", message, re.I)
    words = {"two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10}
    if not match:
        word_match = re.search(r"\b(" + "|".join(words) + r")[- ](?:card|slide)", message, re.I)
        count = words[word_match.group(1).lower()] if word_match else (6 if micro_mission else 1)
    else:
        count = int(match.group(1))
    return max(1, min(count, 10))


def _platform(message: str) -> str:
    for platform in ("instagram", "facebook", "linkedin"):
        if re.search(rf"\b{platform}\b", message, re.I):
            return platform
    return "instagram"


def _emotion(message: str) -> str:
    aliases = {
        "funny": "FUNNY", "humor": "FUNNY", "serious": "SERIOUS", "cinematic": "CINEMATIC",
        "epic": "EPIC", "warm": "WARM", "educational": "USEFUL", "science": "NERDY",
        "thoughtful": "REFLECTIVE", "reassuring": "HOPEFUL", "surprising": "SURPRISING",
    }
    lowered = message.lower()
    return next((value for key, value in aliases.items() if key in lowered), "CINEMATIC")


def _story_beats(message: str, count: int, exact_strings: list[str]) -> list[dict[str, Any]]:
    roles = ["HOOK", "DISCOVERY", "COMPLICATION", "THINKING_ADAPTATION", "PAYOFF", "RESOLUTION"]
    if count != 6:
        middle = ["ESCALATION"] * max(0, count - 2)
        roles = ["HOOK", *middle, "RESOLUTION"] if count > 1 else ["HOOK_PAYOFF"]
    subject = exact_strings[0] if exact_strings else message.strip()
    actions = {
        "HOOK": f"Open mid-problem around {subject}; the conflict is immediately legible and demands the next card.",
        "DISCOVERY": "Infenergy enters in motion, investigates the energy problem, and communicates with LUX only if diagnostics improve the scene.",
        "COMPLICATION": "The obvious solution fails or reveals a deeper energy-flow problem; preserve all established props, damage, scale, and lighting.",
        "THINKING_ADAPTATION": "Infenergy studies where the energy is going and adapts with engineering reasoning, relevant cape behavior, equipment, or purposeful scale change.",
        "PAYOFF": "Deliver the strongest cinematic action as Infenergy executes the earned solution and the environment visibly reacts.",
        "RESOLUTION": "Resolve the human consequence before any brand message; land the lesson, humor, or emotional payoff without turning the frame into an advertisement.",
        "ESCALATION": "Advance the same mini-film with a new obstacle, decision, or physical consequence; do not repeat the prior framing.",
        "HOOK_PAYOFF": f"Show one complete before-action-after story around {subject}, with Infenergy causing the outcome rather than posing.",
    }
    shots = ["environmental wide", "tracking medium", "macro or close-up", "over-the-shoulder diagnostic", "low-angle action wide", "quiet consequence medium"]
    return [
        {
            "index": index + 1,
            "role": role,
            "title": f"{index + 1} OF {count} - {role.replace('_', ' ').title()}",
            "prompt": f"{actions[role]} Camera: {shots[index % len(shots)]}. Card {index + 1} of {count}.",
            "useCanon": True,
        }
        for index, role in enumerate(roles[:count])
    ]


def compile_command(message: str) -> dict[str, Any]:
    text = str(message or "").strip()
    if not is_flagship_creative_command(text):
        raise ValueError("not_a_flagship_creative_command")
    micro_mission = bool(re.search(r"\b(micro[ -]?mission|mission|little story|superhero carousel|family reunion)\b", text, re.I))
    carousel = micro_mission or bool(re.search(r"\b(carousel|cards?|slides?)\b", text, re.I))
    exact_strings = _exact_text(text)
    quote_development = _develop_quote(text) if re.search(r"\bquote\b", text, re.I) and not exact_strings else {}
    if quote_development:
        exact_strings = [quote_development["selected"]]
    integrated = bool(INTEGRATED_TEXT.search(text) or (exact_strings and re.search(r"\b(post|visual|quote|words?|text)\b", text, re.I)))
    character_requested = not bool(re.search(r"\bwithout (?:infenergy|the hero|a character)\b", text, re.I))
    if re.search(r"\b(superhero|hero|mission)\b", text, re.I):
        character_requested = True
    characters = ["Infenergy"] if character_requested else []
    if re.search(r"\blux\b", text, re.I):
        characters.append("LUX")
    count = _slide_count(text, micro_mission) if carousel else 1
    platform = _platform(text)
    aspect_ratio = "4:5" if platform == "instagram" else "1:1"
    route = "MICRO_MISSION" if micro_mission else "CINEMATIC_STORY" if characters else "SCIENCE_VISUAL" if re.search(r"\b(science|educational|battery degradation)\b", text, re.I) else "REAL_WORLD_LIFESTYLE"
    kind = "carousel" if carousel else "typography" if integrated else "cinematic"
    action = (
        f"Infenergy physically changes, powers, repairs, carries, enters, or redirects the exact words {exact_strings[0]} as part of the environment."
        if integrated and characters and exact_strings
        else "Infenergy takes a physically legible action that causes the visual outcome; he does not stand beside the idea."
        if characters
        else f"Turn the requested idea into one visually legible action: {text}"
    )
    beats = _story_beats(text, count, exact_strings) if carousel else []
    return {
        "request_id": str(uuid.uuid4()),
        "objective": text,
        "deliverable": "carousel" if carousel else "social_visual",
        "creative_mode": route,
        "platform": platform,
        "format": kind,
        "card_count": count,
        "aspect_ratio": aspect_ratio,
        "visual_style": "cinematic 3D photorealism",
        "characters": characters,
        "canon_required": bool(characters),
        "emotional_mode": _emotion(text),
        "integrated_typography": integrated,
        "exact_visible_text": exact_strings,
        "quote_development": quote_development,
        "typography_material": "scene-authentic physical material",
        "infenergy_action": action,
        "story_beats": beats,
        "continuity_requirements": [
            "same canonical face, complexion, hairstyle, body, suit, chest mark, cape, and equipment",
            "same location, time progression, props, damage, scale, and direction of movement across cards",
            "cinematic shot variety must serve the story",
        ] if characters else [],
        "quality_gates": ["CANON_QA", "TEXT_QA", "STORY_QA", "VISUAL_QA", "CONTINUITY_QA", "ORIGINALITY_QA", "EMOTIONAL_QA"],
        "repair_policy": {"blocking": True, "max_major_revisions": 2, "return_defective_assets": False},
    }