"""Living, non-product-first audience value decisions and acceptance lab."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any


_EXPERIENCES = (
    ("tip_and_trick", "practical check", "SAVE", False),
    ("did_you_know", "verified fact with consequence", "LEARN", False),
    ("when_was_the_last_time", "habit reflection", "NO_CTA", False),
    ("myth_vs_reality", "misconception correction", "SAVE", False),
    ("common_mistake", "decision error prevention", "SAVE", False),
    ("before_you", "pre-decision support", "PLAN", False),
    ("how_it_works", "plain-language explanation", "LEARN", False),
    ("quick_win", "small practical improvement", "TRY", False),
    ("overlooked_dependency", "hidden dependency", "REFLECT", False),
    ("better_questions", "decision-quality improvement", "SAVE", False),
    ("what_would_happen_if", "scenario reasoning", "REFLECT", False),
    ("comparison_tradeoff", "honest tradeoff", "CHOOSE", False),
    ("lifestyle_reflection", "routine reflection", "NO_CTA", False),
    ("checklist", "save-worthy preparation", "SAVE", False),
    ("mini_lesson", "compact technical learning", "LEARN", False),
    ("counterintuitive_insight", "assumption challenge", "SHARE", False),
    ("misconception", "useful correction", "SAVE", False),
    ("decision_support", "better choice without a sale", "CHOOSE", False),
    ("human_situation", "recognizable moment", "REFLECT", False),
    ("brand_worldview", "helpful category belief", "NO_CTA", False),
    ("research_insight", "evidence-led observation", "SHARE", False),
    ("community_conversation", "worthwhile discussion", "RESPOND", False),
    ("scenario_story", "human consequence", "NO_CTA", False),
    ("seasonal_timely", "timely practical context", "PLAN", False),
    ("equipment_fit", "product relevance earned by fit", "EXPLORE", True),
    ("portable_power_tradeoff", "category comparison", "CHOOSE", True),
    ("backup_planning", "preparedness planning", "SAVE", False),
    ("technology_routine", "technology dependency reflection", "REFLECT", False),
    ("work_mobility", "mobile-work continuity", "PLAN", False),
    ("follow_up_question", "unresolved audience question", "FOLLOW", False),
)

_TERRITORIES = (
    ("outlet_dependence", "How many parts of a normal day quietly depend on the next outlet?", "Map the devices that matter after convenience disappears."),
    ("device_fit", "Capacity alone does not tell you whether a power option fits the equipment you carry.", "Match stored energy, output access, and the actual device job."),
    ("preparedness_horizon", "The first device you reach for is not always the one that matters two hours later.", "Rank needs by the moment they become important."),
    ("mobility_routine", "Travel plans often account for luggage but not for the devices that make the plan workable.", "Plan around the work, navigation, and communication tools you rely on."),
    ("convenience_tradeoff", "A convenient charging habit can hide a fragile routine.", "Notice the dependency before it becomes an interruption."),
    ("decision_quality", "A larger number is not automatically a better choice.", "The right capability is the one that matches the job."),
)

_FORM_DETAILS = {
    "tip_and_trick": "Start by listing the device, its job, and the point at which losing it would actually interrupt the day.",
    "did_you_know": "The useful fact is not how many devices you own; it is which one becomes a problem when access changes.",
    "when_was_the_last_time": "Think back to the last delayed flight, storm, or long drive and identify the first missing convenience you noticed.",
    "myth_vs_reality": "Myth: more capacity automatically solves the problem. Reality: the right connection and the right device priority matter first.",
    "common_mistake": "A common mistake is planning around the phone while forgetting the work, navigation, medical, or communication tool behind it.",
    "before_you": "Before adding another device to a plan, decide what it must do, how soon it matters, and what failure looks like.",
    "how_it_works": "Separate stored energy, available output, and access points; each answers a different part of the real-world question.",
    "quick_win": "Make a two-column note today: devices that are convenient to have and devices that would change the day if unavailable.",
    "overlooked_dependency": "The hidden dependency is often the cable, outlet, adapter, or network tool that turns a charged device into a useful one.",
    "better_questions": "Ask 'what job must this device complete?' before asking 'what is the biggest option available?'.",
    "what_would_happen_if": "Run the scenario forward by two hours, not two minutes; the priority list often changes once the immediate inconvenience passes.",
    "comparison_tradeoff": "Compare choices by the work they preserve, the space they take, and the assumptions they remove, not by a single headline number.",
    "lifestyle_reflection": "Notice how often you recharge by habit rather than by need; a routine can look reliable until its usual outlet disappears.",
    "checklist": "Check the device, its cable, its required port, its priority, and the moment it becomes important.",
    "mini_lesson": "A capacity figure describes stored energy; it does not by itself describe the connection, output, or device task you still need.",
    "counterintuitive_insight": "The most important item in a backup plan is sometimes the modest device that keeps work, directions, or contact possible.",
    "misconception": "Preparedness is not collecting more gear. It is knowing which small set of tools protects the day you are trying to keep intact.",
    "decision_support": "A better choice begins with a defined job, a realistic constraint, and one way to tell whether the choice actually fits.",
    "human_situation": "Picture a parent coordinating a pickup, a traveler rerouting a trip, or a worker finishing a task: the useful device is different in each case.",
    "brand_worldview": "Useful technology should make ordinary life less fragile, not make people decode a specification sheet before they can act.",
    "research_insight": "The most revealing audience question is often a sentence about the moment that went wrong, not a request for a feature list.",
    "community_conversation": "Different routines create different priorities. Comparing the moment that matters is more useful than arguing about one universal setup.",
    "scenario_story": "A small interruption becomes a bigger one when the tool that coordinates the next step was never included in the plan.",
    "seasonal_timely": "Use the season as a prompt to revisit the routines that change with travel, weather, school schedules, or longer days away from home.",
    "equipment_fit": "When a category becomes relevant, earn the comparison by defining the equipment job before naming an option.",
    "portable_power_tradeoff": "Portable power is a tradeoff among what must stay available, what can wait, and what access the situation actually allows.",
    "backup_planning": "A useful backup plan names the first three jobs to protect and the order in which they matter.",
    "technology_routine": "The more invisible a technology routine becomes, the more useful it is to occasionally test what it assumes.",
    "work_mobility": "Mobile work depends on more than a charged laptop: access, connection, and the next communication step all have to hold together.",
    "follow_up_question": "The next good question is the one the first answer exposed: what would still be missing after the obvious device is covered?",
}


@dataclass(frozen=True)
class AudienceValueIdea:
    """A human opportunity that exists before any presentation form is selected."""

    human_reality: str
    tension: str
    takeaway: str
    practical_value: str
    reflection_value: str
    structure_hint: str = ""
    research_required: bool = False
    research_question: str = ""
    audience_state: str = ""
    why_now: str = ""
    continuity_origin: str = ""
    unresolved_question: str = ""
    campaign_relevance: str = "NO_CAMPAIGN"
    product_relevance: str = "NOT_RELEVANT"
    confidence: float = 0.0
    thread_id: str = ""
    thread_action: str = "NONE"
    current_concept: str = ""


@dataclass(frozen=True)
class AudienceValueOpportunity:
    content_form: str
    human_reality: str
    why_interesting: str
    reader_question: str
    reader_takeaway: str
    why_it_matters: str
    desired_memory_anchor: str
    practical_value: str
    reflection_value: str
    share_save_value: str
    product_needed: bool
    cta_class: str
    state_reason: str
    abstain: bool = False
    abstain_reason: str = ""
    research_required: bool = False
    research_question: str = ""
    idea: dict[str, Any] | None = None
    expression: dict[str, Any] | None = None
    campaign_effect: str = "NO_CAMPAIGN"
    product_relevance: str = "NOT_RELEVANT"
    continuity_origin: str = ""
    unresolved_question: str = ""
    human_value_review: dict[str, Any] | None = None
    continuity_thread: dict[str, Any] | None = None
    thread_action: str = "NONE"
    performance_lesson_applied: str = ""

    def as_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def observe_state(recent: dict[str, list[Any]] | None = None, *, seasonal_context: str | None = None) -> dict[str, Any]:
    """Reduce living history to decision signals, not a fixed posting calendar."""
    recent = recent or {}
    forms = [str(item) for item in recent.get("audience_value_forms", []) if item]
    takeaways = [str(item) for item in recent.get("reader_takeaways", []) if item]
    questions = [str(item) for item in recent.get("reader_questions", []) if item]
    cta_classes = [str(item) for item in recent.get("audience_value_cta_classes", []) if item]
    product_pressure = sum(bool(item) for item in recent.get("product_roles", []))
    return {
        "recent_forms": forms,
        "recent_takeaways": takeaways,
        "recent_questions": questions,
        "recent_cta_classes": cta_classes,
        "human_realities": [str(item) for item in recent.get("human_realities", []) if item],
        "seasonal_context": seasonal_context or "",
        "product_pressure": product_pressure,
        "unresolved_question": questions[0] if questions else "",
        "audience_signals": list(recent.get("audience_signals", [])),
        "unresolved_tensions": list(recent.get("unresolved_tensions", [])),
        "performance_learnings": list(recent.get("performance_learnings", [])),
        "research_needs": list(recent.get("research_needs", [])),
        "unresolved_threads": list(recent.get("unresolved_threads", [])),
        "assumptions_challenged": list(recent.get("assumptions_challenged", [])),
        "practical_values": list(recent.get("practical_values", [])),
        "performance_lessons": list(recent.get("performance_lessons", [])),
        "performance_lessons_applied": list(recent.get("performance_lessons_applied", [])),
        "campaign_state": dict(recent.get("campaign_state") or {}),
        "commercial_pressure": list(recent.get("commercial_pressure", [])),
        "product_context": list(recent.get("product_context", [])),
        "continuity_threads": [item for item in recent.get("continuity_threads", []) if isinstance(item, dict)],
    }


_PLANNING_LANGUAGE = (
    "answer the unresolved", "previous question", "last post", "follow-up", "follow up",
    "create a post", "continue the topic", "adjacent decision", "prior audience-value",
)


def _is_audience_question(question: str) -> bool:
    low = question.strip().lower()
    return bool(low and "?" in low and not any(phrase in low for phrase in _PLANNING_LANGUAGE))


def _thread_concept(text: str) -> str:
    low = text.lower()
    if any(word in low for word in ("tradeoff", "carry", "manage")):
        return "tradeoff"
    if any(word in low for word in ("dependency", "cable", "connection", "route", "task")):
        return "dependency"
    if any(word in low for word in ("priority", "matter most", "first")):
        return "priority"
    if any(word in low for word in ("requirement", "output", "handle", "constraint")):
        return "requirements"
    if any(word in low for word in ("fit", "compatible", "capacity")):
        return "fit"
    return "routine"


def _successor_for(thread: dict[str, Any]) -> dict[str, str] | None:
    """Advance a thread by concept, never by wrapping its prior wording."""
    concept = str(thread.get("unresolved_concept") or thread.get("concept") or "")
    questions = {
        "dependency": ("priority", "Which part of this routine would matter first if access changed?", "Rank the job by consequence before choosing what to protect."),
        "priority": ("requirements", "What does the most important job actually require to keep working?", "Name the device, connection, and constraint behind the job."),
        "requirements": ("fit", "How can you tell whether an option fits the job you defined?", "Compare capability against the real task instead of a headline number."),
        "fit": ("tradeoff", "Which tradeoff matters after you know what fits?", "Choose the constraint you are actually willing to carry or manage."),
    }
    item = questions.get(concept)
    if not item:
        return None
    next_concept, question, takeaway = item
    if next_concept == str(thread.get("concept")):
        return None
    return {"concept": next_concept, "question": question, "takeaway": takeaway}


def _branch_successors_for(idea: AudienceValueIdea) -> list[dict[str, str]]:
    """Retain only genuinely distinct next decisions created by an idea."""
    if idea.current_concept != "dependency":
        return []
    return [
        {"concept": "priority", "question": "Which part of this routine would matter first if access changed?", "takeaway": "Rank the job by consequence before choosing what to protect.", "priority": "CURRENT"},
        {"concept": "requirements", "question": "What does the important job need in order to keep working?", "takeaway": "Name the device, connection, and constraint behind the job.", "priority": "DEFERRED"},
    ]


def _idea_specific_packet(idea: AudienceValueIdea) -> dict[str, str]:
    """Turn a selected semantic idea into distinct human-visible beats."""
    reality = idea.human_reality.replace("_", " ")
    packets = {
        "dependency": {
            "hook": f"A charged device can still leave {reality} stuck.",
            "why_interesting": "The useful question is what has to work around the device for the task to finish.",
            "explanation": idea.tension,
            "human_consequence": "The interruption usually comes from the missing link, not the most visible device.",
            "practical_action": "Trace one ordinary task from the first message to the completed outcome, then name the connection, access point, or person it needs.",
            "reflection": "Convenience feels self-contained until one quiet dependency disappears.",
            "memory_anchor": "Follow the task chain.",
        },
        "priority": {
            "hook": f"The first device you notice is not always the first one {reality} needs.",
            "why_interesting": "Immediate annoyance and real consequence often arrive at different times.",
            "explanation": idea.tension,
            "human_consequence": "A routine holds together longer when the next essential job is protected before the obvious one.",
            "practical_action": "Put three jobs in order by the moment losing each one changes the day, then protect the earliest consequence first.",
            "reflection": "What feels urgent in the first minute can be less important by the first hour.",
            "memory_anchor": "Rank by consequence time.",
        },
        "requirements": {
            "hook": f"Before comparing options for {reality}, define the job that cannot fail.",
            "why_interesting": "A specification only becomes useful once it is tied to a real constraint.",
            "explanation": idea.tension,
            "human_consequence": "Choosing by a headline number can leave the decisive connection or access need uncovered.",
            "practical_action": "Write the device, connection, time window, and constraint for one important job before looking at any capability claim.",
            "reflection": "The requirement is usually clearer after you describe the task, not the equipment.",
            "memory_anchor": "Define the job first.",
        },
        "fit": {
            "hook": f"For {reality}, the biggest number may answer the wrong question.",
            "why_interesting": "Fit is a match between a requirement and a capability, not a contest between labels.",
            "explanation": idea.tension,
            "human_consequence": "A better-looking option can still fail the job it was chosen to support.",
            "practical_action": "Compare each option against the exact device, connection, time window, and constraint you already identified.",
            "reflection": "A useful comparison starts with what must work, not what looks most impressive.",
            "memory_anchor": "Match capability to the job.",
        },
        "tradeoff": {
            "hook": f"Every workable setup for {reality} asks you to carry one tradeoff.",
            "why_interesting": "Once several options fit, the decision shifts from capability to the friction you will actually live with.",
            "explanation": idea.tension,
            "human_consequence": "An option is only practical when its size, access, and upkeep fit the routine around it.",
            "practical_action": "Choose the constraint you can manage repeatedly, then rule out options that make that constraint worse.",
            "reflection": "The right compromise is the one your routine can keep honoring.",
            "memory_anchor": "Choose the livable tradeoff.",
        },
    }
    return packets.get(idea.current_concept, {
        "hook": f"The ordinary routine around {reality} can fail before the obvious device does.",
        "why_interesting": "The useful distinction is between what feels convenient now and what keeps the next task possible.",
        "explanation": idea.tension,
        "human_consequence": idea.reflection_value,
        "practical_action": idea.practical_value,
        "reflection": idea.reflection_value,
        "memory_anchor": "Name the next task.",
    })


def synthesize_living_state(recent: dict[str, list[Any]] | None = None, *, seasonal_context: str | None = None) -> dict[str, Any]:
    """Make persisted changes explicit inputs to the next Engine B decision."""
    state = observe_state(recent, seasonal_context=seasonal_context)
    legacy_threads = [
        {
            "thread_id": f"legacy:{question}",
            "human_reality": state["human_realities"][0] if state["human_realities"] else "an ordinary routine",
            "concept": _thread_concept(question),
            "audience_understanding": state["recent_takeaways"][0] if state["recent_takeaways"] else "",
            "unresolved_concept": _thread_concept(question),
            "unresolved_question": question,
            "why_unresolved": "A prior audience question remains unanswered.",
            "practical_next_step": state["practical_values"][0] if state["practical_values"] else "Use the question to clarify one real decision.",
            "depth": 0,
            "status": "OPEN",
        }
        for question in state["unresolved_threads"]
        if _is_audience_question(question)
    ] if not state["continuity_threads"] else []
    latest_threads: dict[str, dict[str, Any]] = {}
    for thread in state["continuity_threads"]:
        candidates = [thread] + [branch for branch in thread.get("branch_successors", []) if isinstance(branch, dict)]
        for candidate in candidates:
            thread_id = str(candidate.get("thread_id") or "")
            if thread_id and thread_id not in latest_threads:
                # `recent()` is newest first, so the first record is authoritative.
                latest_threads[thread_id] = candidate
    open_threads = [
        thread for thread in latest_threads.values()
        if thread.get("status") == "OPEN" and _is_audience_question(str(thread.get("unresolved_question") or ""))
    ] + legacy_threads
    state["open_threads"] = open_threads
    state["deferred_threads"] = [
        thread for thread in latest_threads.values()
        if thread.get("status") == "DEFERRED" and _is_audience_question(str(thread.get("unresolved_question") or ""))
    ]
    state["closed_threads"] = [
        thread for thread in latest_threads.values()
        if thread.get("status") in {"CLOSED", "RESOLVED"}
    ]
    unanswered = [thread.get("unresolved_question") for thread in open_threads] or [
        question for question in state["unresolved_threads"] if _is_audience_question(question)
    ]
    state["what_audience_now_knows"] = state["recent_takeaways"][:3]
    state["open_question"] = str(unanswered[0]) if unanswered else ""
    state["what_not_to_repeat"] = state["recent_takeaways"][:3] + state["assumptions_challenged"][:2]
    state["causal_changes"] = [item for item in (
        f"unresolved thread: {state['open_question']}" if state["open_question"] else "",
        f"performance lesson: {state['performance_lessons'][0]}" if state["performance_lessons"] else "",
        f"campaign phase: {state['campaign_state'].get('phase', '')}" if state["campaign_state"] else "",
    ) if item]
    return state


def _campaign_effect(state: dict[str, Any]) -> str:
    campaign = state["campaign_state"]
    if not campaign:
        return "NO_CAMPAIGN"
    if campaign.get("status") in {"PAUSED", "ENDED"}:
        return str(campaign["status"])
    if state["open_question"]:
        return "CONTINUE" if campaign.get("status") == "ACTIVE" else "START"
    return "EVOLVE" if campaign.get("status") == "ACTIVE" else "START"


def _product_relevance(idea: AudienceValueIdea, state: dict[str, Any]) -> str:
    product_context = " ".join(str(item) for item in state.get("product_context", []))
    if not product_context or state["product_pressure"] or state["commercial_pressure"]:
        return "NOT_RELEVANT"
    if any(word in f"{idea.tension} {idea.unresolved_question}".lower() for word in ("fit", "output", "compatible", "capacity")):
        return "NATURALLY_RELEVANT"
    return "POSSIBLY_RELEVANT"


def human_value_review(idea: AudienceValueIdea, state: dict[str, Any]) -> dict[str, Any]:
    """Reject generic, thin, or sale-disguised education before expression work."""
    packet = _idea_specific_packet(idea)
    text = " ".join((packet["hook"], packet["explanation"], packet["practical_action"], packet["memory_anchor"], packet["reflection"])).lower()
    generic_phrases = ("be prepared", "stay ready", "plan ahead", "make better choices", "audit a routine", "think about your setup", "check your current approach", "consider what matters", "review your needs")
    generic = any(phrase in text for phrase in generic_phrases)
    duplicated_takeaway = packet["hook"].lower().strip(" ?.") == idea.takeaway.lower().strip(" ?.")
    scores = {
        "interest": bool(packet["hook"] and packet["hook"] != idea.tension),
        "usefulness": len(packet["practical_action"].split()) >= 8,
        "specificity": len(set(text.split())) >= 14,
        "curiosity": bool(packet["why_interesting"]),
        "practical_value": bool(packet["practical_action"]),
        "reflection_value": bool(packet["reflection"]),
        "decision_value": bool(idea.takeaway),
        "human_relevance": bool(idea.human_reality),
        "memorability": len(packet["memory_anchor"].split()) >= 3,
    }
    passed = not generic and not duplicated_takeaway and sum(scores.values()) >= 7
    return {"passed": passed, "scores": scores, "reason": "generic_or_thin" if not passed else "attention_earned_without_product", "genericity_challenge": {"brand_generic": generic, "specific_insight": passed, "changes_thinking": passed, "hook_takeaway_distinct": not duplicated_takeaway}}


def invent_expression(idea: AudienceValueIdea, state: dict[str, Any]) -> dict[str, str]:
    """Create an expression description from the selected idea, not a source-map key."""
    packet = _idea_specific_packet(idea)
    opening = packet["hook"]
    reveal = packet["why_interesting"]
    structure = f"{opening} {reveal} {packet['explanation']} Consequence: {packet['human_consequence']} Action: {packet['practical_action']}"
    family = {
        "dependency": "dependency map",
        "priority": "priority ladder",
        "requirements": "requirements checklist",
        "fit": "fit comparison",
        "tradeoff": "tradeoff scenario",
    }.get(idea.current_concept, "causal reflection" if "assumption" in idea.tension.lower() else "decision reveal")
    return {"expression_family": family, "expression_structure": structure, "visual_implication": "human-context sequence or diagram, chosen after the idea", "known_capability_reference": "none required", **packet, "cta": ""}


def platform_expression(opportunity: AudienceValueOpportunity | dict[str, Any], platform: str) -> dict[str, str]:
    """Translate one already-selected idea without changing its value claim."""
    source = opportunity.as_dict() if isinstance(opportunity, AudienceValueOpportunity) else opportunity
    idea = source.get("idea") or {}
    question = str(source.get("reader_question") or "")
    takeaway = str(source.get("reader_takeaway") or "")
    practical = str(source.get("practical_value") or "")
    reality = str(source.get("human_reality") or "")
    why = str(source.get("why_it_matters") or "")
    expression = source.get("expression") or {}
    hook = str(expression.get("hook") or question)
    interest = str(expression.get("why_interesting") or why)
    consequence = str(expression.get("human_consequence") or source.get("reflection_value") or "")
    anchor = str(expression.get("memory_anchor") or takeaway)
    expressions = {
        "facebook": {"format": "accessible explanation", "copy": f"{hook}\n\n{interest}\n\n{why}\n\n{consequence}\n\nTry this: {practical}\n\n{takeaway}\n\nRemember: {anchor}"},
        "instagram_static": {"format": "single visual insight", "copy": f"{hook}\n\n{anchor}\n\n{takeaway}\n\n{practical}"},
        "instagram_reel": {"format": "progressive reveal", "copy": f"Hook: {hook}\nScene 1: {reality}.\nScene 2: {why}\nScene 3: {consequence}\nFinal freeze: {anchor}\nCaption: {practical}"},
        "linkedin": {"format": "decision-quality reasoning", "copy": f"A decision-quality problem: {question}\n\n{interest}\n\nOperational consequence: {consequence}\n\nDecision method: {practical}\n\nPrinciple: {takeaway}\n\nMemory cue: {anchor}"},
    }
    result = expressions.get(platform, expressions["facebook"]).copy()
    result["idea_memory_anchor"] = str(idea.get("takeaway") or takeaway)
    return result


def discover_idea(state: dict[str, Any]) -> AudienceValueIdea | None:
    """Find the reader problem first; forms are deliberately absent here."""
    unused_lessons = [
        str(lesson) for lesson in state["performance_lessons"]
        if str(lesson) not in state["performance_lessons_applied"]
    ]
    if unused_lessons:
        lesson = unused_lessons[0]
        return AudienceValueIdea(
            human_reality=state["human_realities"][0] if state["human_realities"] else "a reader deciding what matters first",
            tension="Which part of this routine would be most useful to prioritize next?",
            takeaway="Use the audience signal to deepen the priority decision, not to repeat the prior format.",
            practical_value="Rank the jobs that change the day before comparing the tools that support them.",
            reflection_value="A strong save signal can mean the decision problem matters more than the format that carried it.",
            audience_state="performance suggests the audience values practical priority-setting",
            why_now=lesson,
            continuity_origin="performance lesson",
            campaign_relevance=_campaign_effect(state),
            confidence=0.8,
            current_concept="priority",
        )
    campaign = state["campaign_state"]
    campaign_question = str(campaign.get("unresolved_question") or state["open_question"] or "")
    if campaign.get("status") == "ACTIVE" and campaign_question:
        return AudienceValueIdea(
            human_reality=str(campaign.get("human_reality") or (state["human_realities"][0] if state["human_realities"] else "an ordinary routine")),
            tension=campaign_question,
            takeaway=str(campaign.get("audience_understanding") or campaign.get("current_audience_understanding") or "Clarify the campaign question with a useful decision criterion."),
            practical_value=str(campaign.get("practical_next_step") or campaign.get("current_practical_next_step") or "Use the campaign's unresolved question to make the next decision clearer."),
            reflection_value="A campaign can advance understanding without repeating its earlier language.",
            audience_state="the campaign has an unresolved audience question with current strategic value",
            why_now="active campaign priority",
            continuity_origin="active campaign",
            campaign_relevance=_campaign_effect(state),
            confidence=0.7,
            current_concept=_thread_concept(campaign_question),
        )
    if state["open_threads"]:
        thread = state["open_threads"][0]
        depth = int(thread.get("depth") or 0)
        question = str(thread["unresolved_question"])
        if depth <= 1 and _is_audience_question(question):
            concept = str(thread.get("unresolved_concept") or _thread_concept(question))
            takeaway_by_concept = {
                "priority": "Rank the jobs that become important first, not the devices you notice first.",
                "requirements": "Name the device, connection, and constraint behind the job before comparing options.",
                "fit": "Compare capability against the real task instead of a headline number.",
                "tradeoff": "Choose the constraint you are actually willing to carry or manage.",
            }
            return AudienceValueIdea(
                human_reality=str(thread.get("human_reality") or "an ordinary routine"),
                tension=question,
                takeaway=takeaway_by_concept.get(concept, "Clarify the next decision in the routine."),
                practical_value=str(thread.get("practical_next_step") or "Use the unresolved concept to test one real decision."),
                reflection_value="The next lesson answers a different audience question rather than restating the earlier post.",
                audience_state=str(thread.get("audience_understanding") or "the audience needs the next decision criterion"),
                why_now=str(thread.get("why_unresolved") or "a meaningful audience question remains open"),
                continuity_origin=str(thread.get("audience_understanding") or thread.get("thread_id") or "open semantic thread"),
                campaign_relevance=_campaign_effect(state),
                confidence=0.72,
                thread_id=str(thread.get("thread_id") or ""),
                thread_action="CONTINUE",
                current_concept=concept,
            )
    signals = list(state["audience_signals"]) + list(state["unresolved_tensions"])
    for raw in signals:
        if not isinstance(raw, dict):
            continue
        reality = str(raw.get("human_reality") or raw.get("reality") or "").strip()
        tension = str(raw.get("tension") or raw.get("question") or "").strip()
        takeaway = str(raw.get("reader_takeaway") or raw.get("takeaway") or "").strip()
        practical = str(raw.get("practical_value") or raw.get("value") or takeaway).strip()
        if reality and tension and takeaway:
            return AudienceValueIdea(
                human_reality=reality,
                tension=tension,
                takeaway=takeaway,
                practical_value=practical,
                reflection_value=str(raw.get("reflection_value") or f"It asks what {reality} depends on.").strip(),
                structure_hint=str(raw.get("structure_hint") or "").strip(),
                research_required=bool(raw.get("research_required")),
                research_question=str(raw.get("research_question") or "").strip(),
                audience_state=str(raw.get("audience_state") or "new human signal").strip(),
                why_now=str(raw.get("why_now") or "a current audience signal created a specific value opportunity").strip(),
                continuity_origin=str(raw.get("continuity_origin") or "current audience signal").strip(),
                unresolved_question=str(raw.get("unresolved_question") or "").strip(),
                campaign_relevance=_campaign_effect(state),
                confidence=float(raw.get("confidence") or 0.7),
                current_concept=_thread_concept(f"{tension} {takeaway}"),
            )
    territory = max(_TERRITORIES, key=lambda candidate: _territory_score(candidate, state))
    territory_id, question, takeaway = territory
    return AudienceValueIdea(
        human_reality=territory_id.replace("_", " "),
        tension=question,
        takeaway=takeaway,
        practical_value={
            "outlet_dependence": "Identify the task that stops when its usual outlet is unavailable, then name the access it needs to continue.",
            "device_fit": "Write down the device, port, and time window for the job before treating a capacity figure as an answer.",
            "preparedness_horizon": "Rank the first three jobs by when losing them changes the day, rather than by which device you reach for first.",
            "mobility_routine": "Walk through one delayed trip and identify the navigation, communication, and work step that must survive the change.",
            "convenience_tradeoff": "Pick one charging habit and name the outlet, cable, and timing assumption that makes it feel automatic.",
            "decision_quality": "Compare two options against the defined task, connection, and constraint instead of their largest headline number.",
        }[territory_id],
        reflection_value=f"It asks the reader to reconsider {territory_id.replace('_', ' ')} in their own routine.",
        audience_state="no explicit new signal; use only a fresh, non-repeated human territory",
        why_now="the territory remains unaddressed in recent memory",
        continuity_origin="fresh territory",
        campaign_relevance=_campaign_effect(state),
        confidence=0.45,
        current_concept=_thread_concept(f"{question} {takeaway}"),
    )


def select_expression(idea: AudienceValueIdea, state: dict[str, Any]) -> tuple[str, str, str, bool, str]:
    """Expression is descriptive and free-form; known capabilities are optional references."""
    expression = invent_expression(idea, state)
    return (
        expression["expression_family"],
        expression["expression_structure"],
        "NO_CTA",
        idea.product_relevance == "NATURALLY_RELEVANT",
        "invented from the selected value idea without a predefined expression key",
    )


def _experience_score(experience: tuple[str, str, str, bool], state: dict[str, Any]) -> tuple[int, int, int, str]:
    content_form, _, cta_class, product_needed = experience
    freshness = 3 if content_form not in state["recent_forms"] else -4
    cta_freshness = 1 if cta_class not in state["recent_cta_classes"] else -1
    product_restraint = -2 if product_needed and state["product_pressure"] else 0
    return (freshness + cta_freshness + product_restraint, freshness, cta_freshness, content_form)


def _territory_score(territory: tuple[str, str, str], state: dict[str, Any]) -> tuple[int, int, str]:
    territory_id, question, takeaway = territory
    takeaway_freshness = 4 if takeaway not in state["recent_takeaways"] else -5
    question_freshness = 1 if question not in state["recent_questions"] else -1
    seasonal_fit = 1 if state["seasonal_context"] and territory_id in state["seasonal_context"].lower() else 0
    return (takeaway_freshness + question_freshness + seasonal_fit, takeaway_freshness, territory_id)


def _opportunity(experience: tuple[str, str, str, bool], territory: tuple[str, str, str], state: dict[str, Any]) -> AudienceValueOpportunity:
    content_form, form_value, cta_class, product_needed = experience
    territory_id, question, takeaway = territory
    detail = _FORM_DETAILS[content_form]
    return AudienceValueOpportunity(
        content_form=content_form,
        human_reality=territory_id,
        why_interesting=f"{detail} It turns {form_value} into a specific question about {territory_id.replace('_', ' ')}.",
        reader_question=question,
        reader_takeaway=takeaway,
        why_it_matters=detail,
        desired_memory_anchor=takeaway,
        practical_value=detail,
        reflection_value=f"It asks the reader to reconsider {territory_id.replace('_', ' ')} in their own routine.",
        share_save_value="It gives the reader a reusable decision check rather than a generic engagement prompt.",
        product_needed=product_needed,
        cta_class=cta_class,
        state_reason=(
            f"state-ranked opportunity; forms={len(state['recent_forms'])}; "
            f"takeaways={len(state['recent_takeaways'])}; product_pressure={state['product_pressure']}"
        ),
    )


def _opportunity_from_idea(idea: AudienceValueIdea, state: dict[str, Any]) -> AudienceValueOpportunity:
    content_form, form_value, cta_class, product_needed, selection_reason = select_expression(idea, state)
    expression = invent_expression(idea, state)
    review = human_value_review(idea, state)
    source_thread = next((thread for thread in state["open_threads"] if thread.get("thread_id") == idea.thread_id), {})
    successor = _successor_for({"concept": idea.current_concept})
    branches = _branch_successors_for(idea) if not idea.thread_id else []
    thread_status = "OPEN"
    thread_action = idea.thread_action
    if branches:
        successor = branches[0]
        thread_action = "BRANCH"
    if idea.thread_action == "CONTINUE":
        # The selected successor answers the open concept; do not keep a
        # wording-derived thread alive without a new independent signal.
        successor = None
        thread_status = "RESOLVED"
    elif not successor:
        thread_action = "CLOSE"
        thread_status = "CLOSED"
    if successor:
        unresolved_question = successor["question"]
        unresolved_concept = successor["concept"]
    else:
        unresolved_question = ""
        unresolved_concept = ""
    thread_id = idea.thread_id or f"{idea.current_concept}:{idea.human_reality}".replace(" ", "_")
    branch_successors = [
        {
            "thread_id": f"{thread_id}:{branch['concept']}",
            "human_reality": idea.human_reality,
            "concept": branch["concept"],
            "unresolved_concept": branch["concept"],
            "unresolved_question": branch["question"],
            "audience_understanding": branch["takeaway"],
            "practical_next_step": _idea_specific_packet(replace(idea, current_concept=branch["concept"]))["practical_action"],
            "why_unresolved": "A distinct successor was retained because it answers a different decision question.",
            "priority": 0.55,
            "revisit_condition": "Revisit after the higher-priority successor is resolved or a matching audience signal appears.",
            "defer_reason": "A more immediate decision has stronger current value.",
            "status": branch["priority"],
            "depth": 1,
        }
        for branch in branches[1:]
    ]
    thread = {
        "thread_id": thread_id,
        "source_post_id": "",
        "human_reality": idea.human_reality,
        "concept": idea.current_concept,
        "question_answered": idea.tension,
        "audience_understanding": idea.takeaway,
        "unresolved_concept": unresolved_concept,
        "unresolved_question": unresolved_question,
        "why_unresolved": "The audience has a distinct next decision to make." if successor else "The current semantic thread delivered its next useful answer.",
        "possible_successor_questions": [successor["question"]] if successor else [],
        "practical_next_step": idea.practical_value,
        "campaign_relevance": idea.campaign_relevance,
        "product_relevance": idea.product_relevance,
        "priority": idea.confidence,
        "freshness": "CURRENT",
        "depth": int(source_thread.get("depth") or 0) + 1,
        "status": thread_status,
        "lifecycle_action": thread_action,
        "close_reason": "The semantic question has delivered its useful resolution." if thread_status == "CLOSED" else "",
        "branch_successors": branch_successors,
    }
    return AudienceValueOpportunity(
        content_form=content_form,
        human_reality=idea.human_reality,
        why_interesting=expression["why_interesting"],
        reader_question=idea.tension,
        reader_takeaway=idea.takeaway,
        why_it_matters=expression["explanation"],
        desired_memory_anchor=expression["memory_anchor"],
        practical_value=expression["practical_action"],
        reflection_value=expression["reflection"],
        share_save_value="It gives the reader a reusable decision check rather than a generic engagement prompt.",
        product_needed=product_needed,
        cta_class=cta_class,
        state_reason=f"idea-first discovery; {selection_reason}; expression={form_value}",
        research_required=idea.research_required,
        research_question=idea.research_question,
        idea=idea.__dict__.copy(),
        expression=expression,
        campaign_effect=idea.campaign_relevance,
        product_relevance=idea.product_relevance,
        continuity_origin=idea.continuity_origin,
        unresolved_question=unresolved_question,
        human_value_review=review,
        continuity_thread=thread,
        thread_action=thread_action,
        performance_lesson_applied=idea.why_now if idea.continuity_origin == "performance lesson" else "",
    )


def discover(*, recent: dict[str, list[Any]] | None = None, rotation_index: int = 0, seasonal_context: str | None = None) -> AudienceValueOpportunity:
    """Choose a valuable human opportunity or abstain when no fresh opportunity exists."""
    state = synthesize_living_state(recent, seasonal_context=seasonal_context)
    used_forms = set(state["recent_forms"])
    idea = discover_idea(state)
    if idea is None:
        return AudienceValueOpportunity(
            content_form="",
            human_reality="",
            why_interesting="No current human reality supplies a defensible value opportunity.",
            reader_question="",
            reader_takeaway="",
            why_it_matters="Avoid filling the feed when the state contains no audience need.",
            desired_memory_anchor="",
            practical_value="",
            reflection_value="",
            share_save_value="",
            product_needed=False,
            cta_class="NO_CTA",
            state_reason="no qualifying audience signal",
            abstain=True,
            abstain_reason="no_current_audience_value_opportunity",
        )
    idea = replace(idea, product_relevance=_product_relevance(idea, state))
    if idea.research_required:
        return AudienceValueOpportunity(
            content_form="",
            human_reality=idea.human_reality,
            why_interesting=idea.practical_value,
            reader_question=idea.tension,
            reader_takeaway=idea.takeaway,
            why_it_matters="The potential value depends on a fact that has not been verified.",
            desired_memory_anchor=idea.takeaway,
            practical_value="",
            reflection_value=idea.reflection_value,
            share_save_value="",
            product_needed=False,
            cta_class="NO_CTA",
            state_reason="research required before a factual audience-value claim",
            abstain=True,
            abstain_reason="RESEARCH_REQUIRED",
            research_required=True,
            research_question=idea.research_question or idea.tension,
        )
    repeated_takeaway = any(idea.takeaway.lower() == item.lower() for item in state["recent_takeaways"])
    if repeated_takeaway and len(used_forms) >= len(_EXPERIENCES) // 2:
        return AudienceValueOpportunity(
            content_form="",
            human_reality=idea.human_reality,
            why_interesting="The available state points only to a recently delivered takeaway.",
            reader_question=idea.tension,
            reader_takeaway=idea.takeaway,
            why_it_matters="Avoid repeating a thought merely because the schedule fired.",
            desired_memory_anchor=idea.takeaway,
            practical_value="",
            reflection_value="",
            share_save_value="",
            product_needed=False,
            cta_class="NO_CTA",
            state_reason="recent takeaway and form are stale",
            abstain=True,
            abstain_reason="no_fresh_audience_value_opportunity",
        )
    opportunity = _opportunity_from_idea(idea, state)
    if not (opportunity.human_value_review or {}).get("passed"):
        return replace(
            opportunity,
            content_form="",
            abstain=True,
            abstain_reason="human_value_gate_rejected",
            state_reason="human value gate rejected generic, thin, or insufficiently specific content",
        )
    return opportunity


def lab_concepts(*, recent: dict[str, list[Any]] | None = None) -> list[dict[str, Any]]:
    """Generate 30 varied nonpublishing concepts for human review, not a posting queue."""
    concepts: list[dict[str, Any]] = []
    state = observe_state(recent)
    for index, experience in enumerate(_EXPERIENCES):
        opportunity = _opportunity(experience, _TERRITORIES[index % len(_TERRITORIES)], state)
        concept = opportunity.as_dict()
        concept.update({
            "facebook_concept": f"Ask the question, then explain: {opportunity.why_it_matters}",
            "instagram_static_concept": f"One visual cue for {opportunity.human_reality.replace('_', ' ')} paired with: {opportunity.reader_takeaway}",
            "instagram_reel_concept": f"Open on the routine, reveal the overlooked assumption, then land: {opportunity.reader_takeaway}",
            "linkedin_concept": f"Frame the operational consequence, then offer this decision principle: {opportunity.reader_takeaway}",
            "visual_idea": f"A real human routine showing {opportunity.human_reality.replace('_', ' ')} without decorative product pressure.",
            "follow_reason": "The account demonstrated useful judgment rather than asking for attention without earning it.",
            "value_delivered": opportunity.practical_value,
            "what_person_learns": opportunity.reader_takeaway,
            "what_it_makes_them_think_about": opportunity.reflection_value,
            "expected_takeaway": opportunity.reader_takeaway,
        })
        concepts.append(concept)
    return concepts


def representative_copy(opportunity: dict[str, Any]) -> str:
    """Produce human-visible lab copy without a product, model, publisher, or visual call."""
    action = opportunity.get("cta_class", "NO_CTA")
    ending = {
        "SAVE": "Save this for the next time you plan what needs to stay available.",
        "SHARE": "Share it with the person who plans the practical details.",
        "REFLECT": "Take a minute to notice what your normal routine assumes.",
        "RESPOND": "What would change your answer?",
        "NO_CTA": "",
    }.get(action, "")
    parts = [
        str(opportunity["reader_question"]),
        str(opportunity["why_it_matters"]),
        str(opportunity["reader_takeaway"]),
        ending,
    ]
    return "\n\n".join(part for part in parts if part)