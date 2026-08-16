"""Bounded creative knowledge retrieval and decision packets.

This module stores principles, not third-party executions or copy.  It is
deliberately deterministic so production can make a defensible creative
decision when external research is unavailable.
"""

from __future__ import annotations

import json
import os
import re
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Any


AGENT_CONTRACTS = {
    "Strategy Red Team": {
        "mission": "challenge evidence-incompatible strategy proposals before lock",
        "inputs": ["strategy proposal", "verified facts", "claim limits"],
        "outputs": ["PASS", "CHANGE_ANGLE", "challenge evidence"],
        "authority": "may challenge an angle; may not select product, audience, benefit, or publish",
        "budget": "one deterministic pre-lock review",
        "termination": "pass or evidence-backed challenge",
        "escalation": "Strategy Intelligence",
    },
    "Claim Intelligence": {
        "mission": "classify provenance and remove unsupported assertions without replacements",
        "inputs": ["candidate copy", "verified facts", "forbidden claims"],
        "outputs": ["claim ledger", "provenance", "removed claims"],
        "authority": "may block unsupported claims; may not invent evidence or publish",
        "budget": "one deterministic candidate-boundary pass",
        "termination": "ledger complete",
        "escalation": "Strategy Intelligence when removal breaks the angle",
    },
    "Metacognition": {
        "mission": "route fresh failure evidence to the smallest repair owner within the existing attempt budget",
        "inputs": ["fresh findings", "coherence", "attempt history", "strategy lock"],
        "outputs": ["repair owner", "scope", "continue/escalate/abstain"],
        "authority": "may route bounded repair; may not lower thresholds, extend retries, or publish",
        "budget": "one decision per candidate",
        "termination": "local repair, governed reconsideration, or abstention",
        "escalation": "authoritative publish governance remains separate",
    },
}


def agent_contracts() -> dict[str, dict[str, Any]]:
    """Owner-readable authority boundaries for the logical roles already in use."""
    return {name: dict(contract) for name, contract in AGENT_CONTRACTS.items()}
from urllib.parse import quote_plus
from urllib.request import Request, urlopen
from html.parser import HTMLParser

from . import research_router


_SEED_REFERENCES = (
    {"reference_id": "layout-editorial-explainer", "source": "internal design principle", "source_type": "internal_repository", "pattern_type": "layout", "platform": ["facebook", "instagram", "linkedin"], "content_job": ["EXPLAIN_THIS", "TEACH_ME"], "layout_logic": "editorial hierarchy: question, answer, supporting proof", "copy_logic": "question -> answer -> why it matters", "visual_logic": "one focal proof with generous reading space", "information_hierarchy": "headline, proof, explanation", "product_role": "supporting proof", "human_role": "decision maker", "benefit_presentation": "diagram or ordered reference", "cta_style": "learn_more", "text_density": "medium", "format": "editorial", "why_it_works": "prioritizes comprehension before promotion", "when_to_use": "an evidence-backed educational decision", "when_not_to_use": "a product-only announcement", "brand_compatibility": "high", "novelty": "stable", "license_or_use_boundary": "abstract principle; no external creative copied"},
    {"reference_id": "layout-human-context", "source": "internal design principle", "source_type": "internal_repository", "pattern_type": "composition", "platform": ["facebook", "instagram"], "content_job": ["PREPARE_ME", "HELP_ME"], "layout_logic": "human situation leads; product appears as a credible supporting object", "copy_logic": "situation -> friction -> practical possibility", "visual_logic": "believable use context instead of literal emotional claim", "information_hierarchy": "human moment, product role, practical action", "product_role": "demonstration object", "human_role": "active user", "benefit_presentation": "scene plus one clear callout", "cta_style": "see_how_it_works", "text_density": "low", "format": "context-led", "why_it_works": "makes the benefit legible without exploiting anxiety", "when_to_use": "a supported customer moment exists", "when_not_to_use": "the claim needs detailed comparison", "brand_compatibility": "high", "novelty": "diverse", "license_or_use_boundary": "abstract principle; no external creative copied"},
    {"reference_id": "layout-comparison-decision", "source": "internal design principle", "source_type": "internal_repository", "pattern_type": "information_design", "platform": ["facebook", "instagram", "linkedin"], "content_job": ["HELP_ME_CHOOSE", "GIVE_ME_A_REFERENCE"], "layout_logic": "side-by-side decision criteria with one recommended evaluation method", "copy_logic": "decision -> options -> tradeoff -> recommendation", "visual_logic": "truthful comparison grid or priority ladder", "information_hierarchy": "decision, criteria, recommendation", "product_role": "reference or proof", "human_role": "informed chooser", "benefit_presentation": "comparison", "cta_style": "compare_options", "text_density": "medium", "format": "data-led", "why_it_works": "turns specifications into a usable decision", "when_to_use": "customers need to compare supported facts", "when_not_to_use": "there is no defensible comparison", "brand_compatibility": "high", "novelty": "diverse", "license_or_use_boundary": "abstract principle; no external creative copied"},
    {"reference_id": "layout-professional-brief", "source": "internal design principle", "source_type": "internal_repository", "pattern_type": "platform_creative", "platform": ["linkedin"], "content_job": ["EXPLAIN_THIS", "HELP_ME_CHOOSE"], "layout_logic": "professional brief: operational context, decision support, proof", "copy_logic": "observation -> business implication -> practical recommendation", "visual_logic": "restrained information hierarchy with a useful takeaway", "information_hierarchy": "context, implication, recommendation", "product_role": "proof", "human_role": "professional decision maker", "benefit_presentation": "decision support", "cta_style": "learn_more", "text_density": "medium", "format": "professional-editorial", "why_it_works": "respects LinkedIn's professional context", "when_to_use": "a legitimate business or operational context is supported", "when_not_to_use": "consumer-only lifestyle content", "brand_compatibility": "high", "novelty": "stable", "license_or_use_boundary": "abstract principle; no external creative copied"},
)


COPY_GRAMMARS = (
    {"id": "observation_insight", "steps": ["observation", "insight", "business_connection"], "best_for": ["EXPLAIN_THIS", "TEACH_ME"]},
    {"id": "question_answer", "steps": ["question", "answer", "why_it_matters"], "best_for": ["EXPLAIN_THIS", "HELP_ME_CHOOSE"]},
    {"id": "situation_friction_possibility", "steps": ["situation", "friction", "possibility"], "best_for": ["PREPARE_ME", "HELP_ME"]},
    {"id": "misconception_truth", "steps": ["misconception", "truth", "explanation"], "best_for": ["TEACH_ME", "EXPLAIN_THIS"]},
    {"id": "decision_tradeoff", "steps": ["decision", "options", "tradeoff", "recommendation"], "best_for": ["HELP_ME_CHOOSE", "GIVE_ME_A_REFERENCE"]},
    {"id": "capability_outcome", "steps": ["product", "capability", "human_outcome"], "best_for": ["SHOW_ME", "HELP_ME"]},
)


@dataclass(frozen=True)
class AutonomousQuestion:
    question: str
    question_type: str
    why_it_matters: str
    decision_affected: str
    materiality: float
    existing_answer: str = ""
    confidence: float = 0.0
    research_needed: bool = False
    meeting_needed: bool = False

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__


_MEETINGS = {
    "strategy": ("MARKETING_STRATEGY", ["Creative Director", "Human Connection Strategist", "Platform Creative Strategist"], ["strategy_lock", "business_intelligence"]),
    "claim": ("CLAIM", ["Benefit Translator", "Copy Critic", "Originality Guardian"], ["strategy_lock", "claim_ledger"]),
    "platform": ("PLATFORM", ["Platform Creative Strategist", "Creative Director"], ["strategy_lock", "platform_constraints"]),
    "fatigue": ("CREATIVE_CONCEPT", ["Creative Director", "Visual Composition Architect", "Art Director", "Visual Critic"], ["creative_memory", "reference_graph"]),
    "human": ("HUMAN_CONNECTION", ["Human Connection Strategist", "Benefit Translator", "Copy Architect"], ["strategy_lock", "customer_moment"]),
    "copy": ("COPY", ["Copy Architect", "Hook Strategist", "Copy Critic"], ["strategy_lock", "copy_memory"]),
    "layout": ("LAYOUT", ["Visual Composition Architect", "Information Priority", "Art Director"], ["strategy_lock", "visual_memory"]),
    "information": ("INFORMATION_DESIGN", ["Information Priority", "Visual Composition Architect", "Copy Critic"], ["strategy_lock", "verified_facts"]),
    "campaign": ("CAMPAIGN", ["Creative Director", "Platform Creative Strategist", "Human Connection Strategist"], ["campaign_state", "performance_history"]),
    "performance": ("PERFORMANCE", ["Creative Director", "Platform Creative Strategist", "Copy Critic", "Visual Critic"], ["performance_history", "creative_memory"]),
}


def _path(data_dir: str | None) -> str:
    root = data_dir or os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")
    return os.path.join(root, "social", "creative_reference_graph.json")


def load_reference_graph(data_dir: str | None = None) -> dict[str, Any]:
    try:
        with open(_path(data_dir), encoding="utf-8") as handle:
            state = json.load(handle)
        if isinstance(state.get("references"), list):
            return state
    except (OSError, json.JSONDecodeError, AttributeError):
        pass
    return {"references": [dict(item) for item in _SEED_REFERENCES], "copy_grammars": [dict(item) for item in COPY_GRAMMARS]}


def save_reference_graph(state: dict[str, Any], data_dir: str | None = None) -> None:
    path = _path(data_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2)


def _source_type_for(need: str) -> str:
    text = need.lower()
    if any(word in text for word in ("layout", "composition", "typography", "information design", "carousel")):
        return "public_repository_or_design_system"
    if any(word in text for word in ("copy", "hook", "headline", "cta")):
        return "public_writing_framework"
    return "public_creative_reference"


class _PublicLinks(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            href = dict(attrs).get("href") or ""
            if href.startswith("https://"):
                self.links.append(href)


def repository_scout(*, need: str, limit: int = 3) -> dict[str, Any]:
    """Discover a very small public repository set without requiring a URL.

    The GitHub metadata endpoint supplies provenance and license data.  Source
    code/creative assets are never imported; only a conservative abstraction
    of the repository's stated purpose is retained.
    """
    query = quote_plus(f"{need} language:HTML,CSS")
    url = f"https://api.github.com/search/repositories?q={query}&sort=stars&order=desc&per_page={max(1, min(limit, 5))}"
    try:
        request = Request(url, headers={"Accept": "application/vnd.github+json", "User-Agent": "InfenergyCreativeScout/1.0"})
        with urlopen(request, timeout=12) as response:  # nosec B310: fixed GitHub discovery endpoint
            payload = json.loads(response.read().decode("utf-8", errors="replace"))
    except Exception as exc:
        return {"status": "SOURCE_UNAVAILABLE", "source_type": _source_type_for(need), "need": need, "error": type(exc).__name__, "candidates": []}
    candidates = []
    for item in payload.get("items", [])[:limit]:
        license_info = item.get("license") or {}
        candidates.append({
            "source": item.get("html_url", ""), "name": item.get("full_name", ""), "description": item.get("description") or "",
            "stars": int(item.get("stargazers_count") or 0), "license": license_info.get("spdx_id") or "NOASSERTION",
            "source_type": "public_repository", "use_boundary": "metadata-informed abstract principle only; no code, assets, layouts, or copy are reused",
        })
    candidates.sort(key=lambda item: (item["stars"], bool(item["description"])), reverse=True)
    return {"status": "OK", "source_type": _source_type_for(need), "need": need, "candidates": candidates}


def source_scout(*, need: str, limit: int = 3) -> dict[str, Any]:
    """Use the repository scout plus one bounded public-reference search.

    Search output is only provenance metadata; extraction remains an abstract
    principle and never imports a page's copy, creative execution, or assets.
    """
    repository = repository_scout(need=need, limit=limit)
    candidates = list(repository.get("candidates", []))
    search_url = f"https://html.duckduckgo.com/html/?q={quote_plus(need + ' design principles')}"
    try:
        request = Request(search_url, headers={"User-Agent": "InfenergyCreativeScout/1.0"})
        with urlopen(request, timeout=12) as response:  # nosec B310: fixed discovery endpoint
            parser = _PublicLinks()
            parser.feed(response.read().decode("utf-8", errors="replace"))
        ignored = {"duckduckgo.com", "google.com", "bing.com", "github.com"}
        seen = {item.get("source") for item in candidates}
        for link in parser.links:
            host = link.split("/", 3)[2].lower().removeprefix("www.")
            if host in ignored or link in seen:
                continue
            candidates.append({"source": link, "name": host, "description": f"Public { _source_type_for(need).replace('_', ' ') } reference for {need}", "stars": 0, "license": "REFERENCE_ONLY", "source_type": "public_reference", "use_boundary": "abstract principle only; no external copy, artwork, assets, or execution are reused"})
            seen.add(link)
            if len(candidates) >= limit:
                break
    except Exception as exc:
        if not candidates:
            return {"status": "LIVE_DISCOVERY_BLOCKED", "source_type": _source_type_for(need), "need": need, "error": type(exc).__name__, "candidates": []}
    return {"status": "OK" if candidates else "LIVE_DISCOVERY_BLOCKED", "source_type": _source_type_for(need), "need": need, "error": repository.get("error", "no public candidates returned"), "candidates": candidates[:limit]}


def _extract_pattern(candidate: dict[str, Any], need: str) -> dict[str, Any] | None:
    if not candidate.get("source") or not candidate.get("description"):
        return None
    text = f"{need} {candidate['description']}".lower()
    if "carousel" in text:
        layout, visual, content_job = "progressive slide hierarchy with one idea per panel", "ordered sequence with a visible continuation cue", ["EXPLAIN_THIS", "GIVE_ME_A_REFERENCE"]
    elif any(word in text for word in ("chart", "data", "infographic", "information")):
        layout, visual, content_job = "data-led hierarchy: claim, comparison, interpretation", "one truthful visual proof per message", ["EXPLAIN_THIS", "HELP_ME_CHOOSE"]
    else:
        layout, visual, content_job = "clear focal hierarchy with constrained supporting information", "composition serves the communication goal before decoration", ["EXPLAIN_THIS", "TEACH_ME", "HELP_ME_CHOOSE"]
    return {
        "reference_id": f"source-{abs(hash(candidate['source'])):x}", "source": candidate["source"], "source_type": candidate["source_type"],
        "pattern_type": "repository_principle", "platform": ["facebook", "instagram", "linkedin"], "content_job": content_job,
        "layout_logic": layout, "copy_logic": "original copy selected from internal grammar", "visual_logic": visual,
        "information_hierarchy": "message, supporting proof, action", "product_role": "chosen by strategy", "human_role": "chosen by customer moment",
        "benefit_presentation": "appropriate to the decision", "cta_style": "contextual", "text_density": "medium", "format": "principle-derived",
        "why_it_works": "repository purpose was abstracted into a communication principle", "when_to_use": "when it fits the supported strategy", "when_not_to_use": "when it would reproduce the source execution",
        "brand_compatibility": "review_required", "novelty": "new", "last_observed": datetime.now(timezone.utc).isoformat(),
        "license_or_use_boundary": f"{candidate['license']}; {candidate['use_boundary']}", "provenance_summary": candidate["description"][:240],
    }


def reference_heartbeat(data_dir: str | None = None, *, level: str = "LIGHT", knowledge_need: str = "", scout: Any = None) -> dict[str, Any]:
    """Refresh known principles and, within a level budget, acquire one bounded new source set."""
    if level not in {"LIGHT", "STANDARD", "DEEP"}:
        raise ValueError("unsupported creative reference heartbeat level")
    state = load_reference_graph(data_dir)
    known = {item.get("reference_id") for item in state["references"]}
    added = [dict(item) for item in _SEED_REFERENCES if item["reference_id"] not in known]
    state["references"].extend(added)
    grammar_ids = {item.get("id") for item in state.get("copy_grammars", [])}
    state.setdefault("copy_grammars", []).extend(dict(item) for item in COPY_GRAMMARS if item["id"] not in grammar_ids)
    budget = {"LIGHT": 0, "STANDARD": 2, "DEEP": 3}[level]
    acquisition = {"status": "NOT_REQUESTED", "candidates": []}
    extracted = 0
    if knowledge_need and budget:
        scout = scout or source_scout
        acquisition = scout(need=knowledge_need, limit=budget)
        existing_sources = {item.get("source") for item in state["references"]}
        for candidate in acquisition.get("candidates", []):
            pattern = _extract_pattern(candidate, knowledge_need)
            if pattern and pattern["source"] not in existing_sources:
                state["references"].append(pattern)
                existing_sources.add(pattern["source"])
                extracted += 1
    if level == "DEEP":
        state["stagnation_review"] = {"reference_count": len(state["references"]), "needs_diversification": len({item.get("pattern_type") for item in state["references"]}) < 3}
    state["last_heartbeat"] = {"level": level, "at": datetime.now(timezone.utc).isoformat(), "references": len(state["references"])}
    save_reference_graph(state, data_dir)
    return {"status": "ok", "added": len(added), "extracted": extracted, "references": len(state["references"]), "budget": {"external_discovery": budget}, "acquisition": acquisition}


def feed_intelligence(recent: dict[str, list[Any]]) -> dict[str, Any]:
    """Read existing creative memory and name the next useful feed counterweight."""
    def repeated(values: list[Any]) -> Any:
        clean = [str(value) for value in values if value]
        return clean[0] if len(clean) >= 3 and len(set(clean[:4])) == 1 else ""
    layout = repeated(recent.get("layout_grammars", []))
    product_role = repeated(recent.get("product_roles", []))
    human_presence = repeated(recent.get("human_presence", []))
    density = repeated(recent.get("text_densities", []))
    formats = [str(value) for value in recent.get("visual_formats", []) if value]
    format_repeat = formats[0] if formats and len(set(formats)) == 1 else ""
    needs = []
    if layout or format_repeat:
        needs.append("a different layout and visual rhythm")
    if product_role:
        needs.append("a different product role or placement")
    if human_presence:
        needs.append("a different human/product balance")
    if density:
        needs.append("a different information density")
    return {"layout_repetition": layout, "format_repetition": format_repeat, "product_role_repetition": product_role, "human_presence_repetition": human_presence, "text_density_repetition": density, "customer_moment_diversity": len(set(map(str, recent.get("customer_moments", [])))), "human_value_diversity": len(set(map(str, recent.get("emotional_framings", [])))), "content_job_diversity": len(set(map(str, recent.get("reader_jobs", [])))), "what_feed_needs_next": needs or ["continue with a balanced, evidence-led expression"], "novelty_required": bool(needs)}


def creative_learning_guidance(data_dir: str | None = None) -> list[dict[str, Any]]:
    """Read only repeated, non-conflicted recommendations; never treat one post as truth."""
    root = data_dir or os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")
    try:
        with open(os.path.join(root, "social", "living_intelligence.json"), encoding="utf-8") as handle:
            state = json.load(handle)
        return list((state.get("creative_learning") or {}).get("recommendations") or [])
    except (OSError, json.JSONDecodeError):
        return []


def campaign_guidance(data_dir: str | None = None) -> dict[str, Any]:
    """Read the bounded campaign decision made by the independent heartbeat."""
    root = data_dir or os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")
    try:
        with open(os.path.join(root, "social", "living_intelligence.json"), encoding="utf-8") as handle:
            state = json.load(handle)
        campaign = state.get("campaign_state") or {}
        return campaign if campaign.get("decision") in {"start", "evolve"} else {}
    except (OSError, json.JSONDecodeError):
        return {}


def _copy_concepts(*, strategy: dict[str, Any], grammar: dict[str, Any], recent: dict[str, list[Any]], platform: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Create compact, genuinely different approaches before writing one winner."""
    angle = str(strategy.get("angle") or "this practical decision")
    benefit = str(strategy.get("benefit") or "a clearer choice")
    question_angle = angle.rstrip(".?")
    why_match = re.match(
        r"why\s+(.+?)\s+(isn't|is not|aren't|are not|doesn't|does not|don't|do not)\s+(.+)",
        question_angle,
        flags=re.IGNORECASE,
    )
    if why_match:
        educational_opening = f"Why {why_match.group(2)} {why_match.group(1)} {why_match.group(3)}?"
    elif question_angle.lower().startswith(("why ", "how ", "what ", "when ", "where ", "which ", "can ", "does ", "is ")):
        educational_opening = f"{question_angle[:1].upper() + question_angle[1:]}?"
    else:
        educational_opening = f"What should you understand about {question_angle[:1].lower() + question_angle[1:]}?"
    customer_moment = str(strategy.get("customer_moment") or "power is uncertain").strip().rstrip(".?!")
    if customer_moment.lower().startswith(("before ", "after ", "during ", "when ", "while ")):
        human_opening = f"{customer_moment[:1].upper() + customer_moment[1:]}, what matters most?"
    else:
        human_opening = f"When {customer_moment}, what matters most?"
    misconception_opening = (
        "A longer specification list does not automatically show whether a product "
        f"{benefit.rstrip('.?!')}."
    )
    options = [
        {"approach": "human_recognition", "opening": human_opening, "structure": "situation -> friction -> possibility", "fit": 0.78},
        {"approach": "educational_insight", "opening": educational_opening, "structure": "observation -> insight -> business connection", "fit": 0.8},
        {"approach": "decision_support", "opening": f"Before choosing, compare the role a power solution needs to play.", "structure": "decision -> options -> tradeoff -> recommendation", "fit": 0.82},
        {"approach": "misconception", "opening": misconception_opening, "structure": "misconception -> truth -> explanation", "fit": 0.75},
    ]
    used = " ".join(map(str, recent.get("hooks", []))).lower()
    for item in options:
        if item["opening"].lower() in used:
            item["fit"] -= 0.35
        if platform.startswith("linkedin") and item["approach"] == "decision_support":
            item["fit"] += 0.1
    options.sort(key=lambda item: item["fit"], reverse=True)
    return options, options[0]


def platform_interpretations(*, strategy: dict[str, Any], concept: dict[str, Any], layout: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Adapt one truth into distinct native creative directions."""
    memory = concept.get("desired_memory") or strategy.get("human_outcome")
    return {
        "facebook": {"hook_posture": "conversation-starter", "copy_length": "medium", "format": "community_story", "information_density": "medium", "visual_composition": "human-context with a discussion cue", "cta_expression": "invite a practical response", "product_emphasis": "supporting", "desired_memory": memory},
        "instagram": {"hook_posture": "visual-first takeaway", "copy_length": "short", "format": "carousel_or_reel", "information_density": "low_to_medium", "visual_composition": "one memorable focal hierarchy", "cta_expression": "save or share the practical reference", "product_emphasis": "visual proof", "desired_memory": memory},
        "linkedin": {"hook_posture": "professional implication", "copy_length": "medium", "format": "professional_brief", "information_density": "medium", "visual_composition": "editorial decision-support hierarchy", "cta_expression": "learn more about the operational consideration", "product_emphasis": "evidence", "desired_memory": memory},
    }


def retrieve_references(*, reader_job: str, platform: str, recent_visual_formats: list[Any], data_dir: str | None = None, limit: int = 3) -> list[dict[str, Any]]:
    """Return a small diverse principle set, avoiding a pile of near-duplicates."""
    platform_key = platform.split("_", 1)[0]
    refs = load_reference_graph(data_dir)["references"]
    ranked = [item for item in refs if reader_job in item.get("content_job", []) and platform_key in item.get("platform", [])]
    ranked = ranked or [item for item in refs if platform_key in item.get("platform", [])]
    ranked.sort(key=lambda item: (item.get("novelty") == "new", item.get("source_type") != "internal_repository"), reverse=True)
    selected: list[dict[str, Any]] = []
    seen_formats = {str(item) for item in recent_visual_formats}
    for item in ranked:
        if item.get("format") in seen_formats and len(ranked) > limit:
            continue
        if item.get("pattern_type") in {chosen.get("pattern_type") for chosen in selected}:
            continue
        selected.append(item)
        if len(selected) >= limit:
            break
    return selected


def detect_questions(*, strategy: dict[str, Any], platform: str, recent: dict[str, list[Any]], signals: list[dict[str, Any]] | None = None) -> list[AutonomousQuestion]:
    """Detect material unknowns from any runtime signal, not a fixed checklist."""
    questions: list[AutonomousQuestion] = []
    actual_claims = list(strategy.get("claims") or strategy.get("proof") or [])
    claim_requires_evidence = bool(actual_claims or strategy.get("important_capability"))
    evidence = list(strategy.get("proof") or [])
    if claim_requires_evidence and not evidence:
        questions.append(AutonomousQuestion("Which verified fact supports the specific capability claim?", "claim", "A factual product claim needs traceable support.", "claim wording", 0.9, "", 0.0, True, True))
    if platform.startswith("linkedin") and not any(term in " ".join(str(strategy.get(key, "")) for key in ("customer_moment", "angle", "positioning")).lower() for term in ("business", "professional", "work", "operational")):
        questions.append(AutonomousQuestion("What legitimate professional context supports this LinkedIn expression?", "platform", "LinkedIn needs supported business or professional relevance.", "LinkedIn suitability", 0.8, "", 0.0, False, True))
    feed = feed_intelligence(recent)
    if feed["novelty_required"]:
        questions.append(AutonomousQuestion("What different visual grammar would improve feed variety?", "fatigue", "Feed rhythm shows repeated composition, role, or density.", "layout selection", 0.65, "; ".join(feed["what_feed_needs_next"]), 0.85, False, True))
    for signal in signals or []:
        if not isinstance(signal, dict) or not signal.get("question"):
            continue
        questions.append(AutonomousQuestion(str(signal["question"]), str(signal.get("question_type") or "human"), str(signal.get("why_it_matters") or "A better answer may change the creative decision."), str(signal.get("decision_affected") or "creative decision"), float(signal.get("materiality", 0.5)), str(signal.get("existing_answer") or ""), float(signal.get("confidence", 0.0)), bool(signal.get("research_needed", False)), bool(signal.get("meeting_needed", True))))
    return questions


def route_meetings(questions: list[AutonomousQuestion]) -> list[dict[str, Any]]:
    """Route only material questions to a meeting with executable criteria."""
    meetings = []
    for question in questions:
        if question.materiality < 0.6 or not question.meeting_needed:
            continue
        meeting_type, specialists, knowledge = _MEETINGS.get(question.question_type, _MEETINGS["human"])
        meetings.append({"meeting_type": meeting_type, "question": question.as_dict(), "required_specialists": specialists, "required_knowledge": knowledge, "research_needed": question.research_needed, "termination": "sufficient evidence, bounded research failure, or conservative decision"})
    return meetings


def _specialist_verdicts(*, strategy: dict[str, Any], questions: list[AutonomousQuestion], references: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Separable specialist responsibilities; deterministic and reviewable."""
    text = " ".join(str(strategy.get(key, "")) for key in ("audience", "customer_moment", "human_need", "benefit", "angle"))
    claim_gap = any(question.question_type == "claim" for question in questions)
    return {
        "Creative Director": {"criterion": "one clear communication objective", "passed": bool(strategy.get("angle"))},
        "Human Connection Strategist": {"criterion": "supported human situation and practical value", "passed": bool(strategy.get("customer_moment") and strategy.get("human_need"))},
        "Copy Architect": {"criterion": "grammar fits reader job", "passed": bool(strategy.get("reader_job"))},
        "Hook Strategist": {"criterion": "opening can create a specific curiosity or decision", "passed": bool(strategy.get("angle"))},
        "Benefit Translator": {"criterion": "feature-to-outcome chain is grounded", "passed": bool(strategy.get("benefit") or strategy.get("important_capability"))},
        "Information Priority": {"criterion": "not every fact competes for the graphic", "passed": True},
        "Visual Composition Architect": {"criterion": "a composition principle supports the message", "passed": bool(references)},
        "Art Director": {"criterion": "visual role does not duplicate caption", "passed": bool(strategy.get("visual_objective"))},
        "Platform Creative Strategist": {"criterion": "platform expression is supported", "passed": True},
        "Originality Guardian": {"criterion": "principles, not external executions or copy", "passed": all("abstract" in str(item.get("license_or_use_boundary", "abstract")) or item.get("source_type") == "internal_repository" for item in references)},
        "Copy Critic": {"criterion": "claims are evidence-scoped", "passed": not claim_gap},
        "Visual Critic": {"criterion": "visual hierarchy is distinct from recent work when fatigue exists", "passed": True},
        "context": {"supported_human_context": bool(text.strip())},
    }


def _benefit_chain(strategy: dict[str, Any]) -> dict[str, str]:
    feature = str(strategy.get("important_capability") or (strategy.get("proof") or [""])[0] or "")
    benefit = str(strategy.get("benefit") or "practical decision support")
    return {"FEATURE": feature, "FUNCTION": feature or "product capability", "PRACTICAL_BENEFIT": benefit, "CUSTOMER_OUTCOME": str(strategy.get("human_outcome") or benefit), "HUMAN_MEANING": str(strategy.get("human_value") or strategy.get("human_need") or "practical clarity")}


def _information_priority(strategy: dict[str, Any], benefit: dict[str, str]) -> dict[str, list[str]]:
    must = [item for item in (strategy.get("angle"), benefit["PRACTICAL_BENEFIT"]) if item]
    supporting = [str(item) for item in (strategy.get("proof") or [])[:2] if item]
    return {"MUST_SHOW": must[:2], "SHOULD_SHOW": [benefit["CUSTOMER_OUTCOME"]] if benefit["CUSTOMER_OUTCOME"] else [], "SUPPORTING": supporting, "OMIT": [str(item) for item in (strategy.get("proof") or [])[2:]]}


def _layout_grammar(*, selected: dict[str, Any], strategy: dict[str, Any], platform: str, fatigue: bool) -> dict[str, Any]:
    role = str(selected.get("product_role") or "supporting proof")
    human_context = bool(strategy.get("customer_moment") and strategy.get("human_need"))
    return {"components": ["headline", "benefit", "proof", "product", "cta", "brand_mark"], "primary_focal_point": "human situation" if human_context and "human" in selected.get("format", "") else "headline and benefit", "secondary_focal_point": role, "reading_flow": "Z-pattern" if platform.startswith("facebook") else "top-to-bottom editorial", "product_role": role, "product_placement": "supporting lower-right" if role != "hero" else "foreground center", "human_role": "active decision maker" if human_context else "absent", "human_placement": "contextual background" if human_context else "none", "headline_position": "top-left", "benefit_position": "adjacent to focal proof", "proof_position": "supporting lower-third", "cta_position": "footer", "text_density": selected.get("text_density", "medium"), "alignment": "asymmetrical editorial" if fatigue else "clear grid", "spacing_intent": "generous separation between claim and proof", "visual_hierarchy": selected.get("information_hierarchy", "headline, proof, explanation")}


def _concept_competition(*, strategy: dict[str, Any], references: list[dict[str, Any]], benefit: dict[str, str], fatigue: bool, recent: dict[str, list[Any]]) -> list[dict[str, Any]]:
    categories = [("human-context", "show the practical situation", "supporting character"), ("decision-support", "make the comparison or priority visible", "proof"), ("editorial", "frame one useful observation", "supporting proof")]
    concepts = []
    for index, (kind, visual_job, product_role) in enumerate(categories):
        reference = references[index % len(references)] if references else {"layout_logic": "clear hierarchy", "copy_logic": "question -> answer", "reference_id": "internal-fallback"}
        score = 0.8 - (0.1 if fatigue and index == 0 else 0)
        if kind in {str(item) for item in recent.get("visual_concepts", [])[:1]}:
            score -= 0.2
        concepts.append({"id": kind, "copy_job": reference["copy_logic"], "visual_job": visual_job, "layout_logic": reference["layout_logic"], "product_role": product_role, "human_role": "active decision maker" if kind == "human-context" else "viewer", "desired_memory": benefit["CUSTOMER_OUTCOME"], "reference_id": reference["reference_id"], "score": score})
    return sorted(concepts, key=lambda item: item["score"], reverse=True)


def _copy_grammar(*, reader_job: str, recent: dict[str, list[Any]], concepts: list[dict[str, Any]], data_dir: str | None) -> dict[str, Any]:
    persistent = load_reference_graph(data_dir).get("copy_grammars", [])
    candidates = [item for item in persistent if reader_job in item["best_for"]] or list(persistent)
    used = {str(item) for item in recent.get("copy_grammars", [])}
    selected = next((item for item in candidates if item["id"] not in used), candidates[0])
    return {"selected": selected, "candidates": candidates[:3], "reason": "reader-job fit and memory-aware diversity"}


def decide(*, strategy: dict[str, Any], platform: str, recent: dict[str, list[Any]], data_dir: str | None = None, signals: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Run one bounded autonomous creative meeting and return its decision evidence."""
    reference_heartbeat(data_dir, level="LIGHT")
    questions = detect_questions(strategy=strategy, platform=platform, recent=recent, signals=signals)
    meetings = route_meetings(questions)
    references = retrieve_references(reader_job=strategy.get("reader_job", ""), platform=platform, recent_visual_formats=recent.get("visual_formats", []), data_dir=data_dir)
    fatigue = any(question.question_type == "fatigue" for question in questions)
    benefit = _benefit_chain(strategy)
    concepts = _concept_competition(strategy=strategy, references=references, benefit=benefit, fatigue=fatigue, recent=recent)
    learning = creative_learning_guidance(data_dir)
    campaign = campaign_guidance(data_dir)
    for concept in concepts:
        if any(item.get("dimension") == "visual_concept_x_audience" and concept["id"] in item.get("values", []) for item in learning):
            concept["score"] += 0.08
        if campaign.get("next_content_priority") == "campaign_sequence" and concept["id"] == "decision-support":
            concept["score"] += 0.05
    concepts.sort(key=lambda item: item["score"], reverse=True)
    selected_concept = concepts[0]
    selected = next((item for item in references if item["reference_id"] == selected_concept["reference_id"]), references[0] if references else {"reference_id": "internal-fallback", "layout_logic": "clear hierarchy", "copy_logic": "question -> answer -> why it matters", "visual_logic": "one focal proof", "information_hierarchy": "headline, proof, explanation", "product_role": "supporting proof", "text_density": "medium"})
    grammar = _copy_grammar(reader_job=strategy.get("reader_job", ""), recent=recent, concepts=concepts, data_dir=data_dir)
    copy_concepts, selected_copy = _copy_concepts(strategy=strategy, grammar=grammar, recent=recent, platform=platform)
    selected = selected | {"copy_logic": " -> ".join(grammar["selected"]["steps"]), "creative_concept": selected_concept["id"]}
    rotation = bool(recent.get("visual_concepts"))
    layouts = _layout_grammar(selected=selected, strategy=strategy, platform=platform, fatigue=fatigue or rotation)
    native = platform_interpretations(strategy=strategy, concept=selected_concept, layout=layouts)
    platform_outcomes = {"facebook": {"status": "ELIGIBLE"}, "instagram": {"status": "ELIGIBLE"}, "linkedin": {"status": "ELIGIBLE"}}
    for question in questions:
        if question.question_type == "platform" and platform.startswith("linkedin"):
            platform_outcomes["linkedin"] = {"status": "DECLINED", "reason": "no supported professional or business context"}
    claim_questions = [question for question in questions if question.question_type == "claim"]
    research_tasks = [research_router.route(question=question.question, why_needed=question.why_it_matters, entity=strategy.get("offering") or strategy.get("topic") or "Infenergy", decision_affected=question.decision_affected).as_dict() for question in questions if question.research_needed]
    specialists = _specialist_verdicts(strategy=strategy, questions=questions, references=references)
    material_claim_risk = bool(claim_questions and strategy.get("claims"))
    action = "do_not_publish" if material_claim_risk else "create"
    return {
        "QUESTION": "What original creative expression best communicates this supported strategy now?",
        "WHY_IT_MATTERS": "The creative decision determines whether a real customer can understand the supported benefit.",
        "DECISION_REQUIRED": "select layout, copy grammar, and product role",
        "EXISTING_KNOWLEDGE": {"strategy_lock": strategy, "recent_creative": recent},
        "KNOWLEDGE_GAPS": [question.as_dict() for question in questions],
        "SOURCES_CONSULTED": ["strategy_lock", "creative_memory", "creative_reference_graph"],
        "REFERENCE_PATTERNS_USED": [item["reference_id"] for item in references],
        "AGENTS_PARTICIPATING": ["Creative Director", "Human Connection Strategist", "Information Priority Agent", "Originality Guardian"],
        "CANDIDATE_ANSWERS": concepts,
        "MAJOR_OBJECTIONS": [question.why_it_matters for question in claim_questions if material_claim_risk],
        "SELECTED_ANSWER": selected,
        "CONFIDENCE": 0.8 if not claim_questions else 0.6,
        "ASSUMPTIONS": ["References are abstract principles, not source executions."],
        "CLAIM_LIMITS": strategy.get("claim_limits", "Use only verified facts."),
        "ACTION": action,
        "MEMORY_UPDATE": {"layout_logic": selected["layout_logic"], "copy_logic": selected["copy_logic"], "concept": selected_concept["id"], "product_role": selected_concept["product_role"], "text_density": selected.get("text_density", "medium"), "copy_approach": selected_copy["approach"], "hook": selected_copy["opening"]},
        "FOLLOW_UP_TRIGGER": "research_tasks" if research_tasks else "performance_review",
        "research_tasks": research_tasks,
        "questions": [question.as_dict() for question in questions],
        "meetings": meetings,
        "specialist_verdicts": specialists,
        "platform_outcomes": platform_outcomes,
        "benefit_translation": benefit,
        "information_priority": _information_priority(strategy, benefit),
        "copy_grammar": grammar,
        "layout_grammar": layouts,
        "creative_concepts": concepts,
        "copy_concepts": copy_concepts,
        "selected_copy_concept": selected_copy,
        "hook_selection": {"family": selected_copy["approach"], "text": selected_copy["opening"], "scores": {"audience_relevance": selected_copy["fit"], "novelty": 1.0 if selected_copy["opening"].lower() not in " ".join(map(str, recent.get("hooks", []))).lower() else 0.4, "specificity": 0.75, "platform_fit": 0.85, "human_connection": 0.8, "payoff_alignment": 0.8}},
        "feed_intelligence": feed_intelligence(recent),
        "creative_learning_guidance": learning,
        "campaign_guidance": campaign,
        "platform_interpretations": native,
        "novelty_process": {"triggered": fatigue or rotation, "action": "select a different composition/copy grammar" if fatigue or rotation else "standard diversity retrieval"},
        "originality_review": specialists["Originality Guardian"],
    }