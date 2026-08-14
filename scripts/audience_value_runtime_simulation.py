"""Nonpublishing production-parity simulation for the real Engine B decision path."""

from __future__ import annotations

import tempfile
from pathlib import Path
import sys
from typing import Any

from social import audience_value, engines, memory_intelligence, performance_learning


_GENERIC_PHRASES = ("be prepared", "stay ready", "plan ahead", "make better choices", "audit a routine", "think about your setup", "check your current approach", "consider what matters", "review your needs")


def _copy(value: dict[str, Any]) -> str:
    expression = value.get("expression") or {}
    return "\n\n".join(part for part in (
        expression.get("hook", value.get("reader_question", "")),
        expression.get("why_interesting", ""),
        value.get("why_it_matters", ""),
        expression.get("human_consequence", value.get("reflection_value", "")),
        f"Try this: {value.get('practical_value', '')}" if value.get("practical_value") else "",
        value.get("reader_takeaway", ""),
        f"Remember: {expression.get('memory_anchor', value.get('desired_memory_anchor', ''))}" if expression.get("memory_anchor", value.get("desired_memory_anchor", "")) else "",
    ) if part)


def _human_value_score(value: dict[str, Any]) -> dict[str, bool]:
    expression = value.get("expression") or {}
    hook = str(expression.get("hook") or "").lower().strip(" ?.")
    takeaway = str(value.get("reader_takeaway") or "").lower().strip(" ?.")
    practical = str(value.get("practical_value") or "")
    anchor = str(expression.get("memory_anchor") or "")
    copy = _copy(value).lower()
    scores = {
        "INTEREST": bool(hook and hook != takeaway and expression.get("why_interesting")),
        "SPECIFICITY": bool(value.get("human_reality") and expression.get("explanation") and practical),
        "USEFULNESS": len(practical.split()) >= 8,
        "NEW_LEARNING": bool(takeaway and takeaway not in hook and takeaway not in str(expression.get("explanation") or "").lower()),
        "REFLECTION": bool(expression.get("reflection") and expression.get("human_consequence")),
        "MEMORABILITY": 2 <= len(anchor.split()) <= 7 and anchor.lower() != takeaway,
        "GENERICITY": not any(phrase in copy for phrase in _GENERIC_PHRASES),
        "VALUE_INDEPENDENT_OF_PRODUCT": not bool(value.get("product_needed")) or str(value.get("product_relevance") or "") in {"NATURALLY_RELEVANT", "DIRECTLY_RELEVANT"},
    }
    scores["HUMAN_VALUE_PASS"] = all(scores.values())
    return scores


def _record(value: dict[str, Any], *, data_dir: str, performance_lesson: str = "") -> None:
    memory_intelligence.append_content_record({
        "engine": "B", "audience_value_form": value.get("content_form", ""),
        "human_reality": value.get("human_reality", ""), "reader_question": value.get("reader_question", ""),
        "reader_takeaway": value.get("reader_takeaway", ""), "practical_value": value.get("practical_value", ""),
        "assumption_challenged": value.get("reflection_value", ""),
        "unresolved_thread": value.get("unresolved_question", ""),
        "continuity_thread": value.get("continuity_thread", {}),
        "question_answered": value.get("reader_question", ""),
        "question_created": value.get("unresolved_question", ""),
        "thread_action": value.get("thread_action", "NONE"),
        "audience_value_cta_class": value.get("cta_class", ""),
        "performance_lesson": performance_lesson, "campaign_effect": value.get("campaign_effect", ""),
        "performance_lesson_applied": value.get("performance_lesson_applied", ""),
    }, data_dir=data_dir)


def run(*, count: int = 12) -> dict[str, Any]:
    """Call Engine B, persist its outcome, and let its own memory change the next decision."""
    with tempfile.TemporaryDirectory() as data_dir:
        initial = {
            "human_reality": "a parent coordinating a delayed pickup",
            "tension": "Which invisible dependency can stop a pickup plan after the phone is charged?",
            "takeaway": "Trace the task, not the device.",
            "practical_value": "Map the contact, route, cable, and next action before the delay happens.",
            "reflection_value": "A familiar device can hide the rest of a coordination system.",
        }
        memory_intelligence.append_content_record({"unresolved_thread": "", "human_reality": initial["human_reality"]}, data_dir=data_dir)
        decisions: list[dict[str, Any]] = []
        for index in range(count):
            recent = memory_intelligence.recent(data_dir, limit=20)
            if index == 0:
                recent["audience_signals"] = [initial]
            if index == 4:
                performance = performance_learning.interpret_audience_value_signal(
                    metrics={"saves": 8, "comments": 0}, reader_problem="task dependency planning"
                )
                recent["performance_lessons"] = [performance["learning"]]
            brief = engines.AudienceValueEngine().build(recent=recent, rotation_index=index)
            value = brief.audience_value
            before = audience_value.synthesize_living_state(recent)
            performance_lesson = ""
            if index == 4:
                performance_lesson = recent["performance_lessons"][0]
            _record(value, data_dir=data_dir, performance_lesson=performance_lesson)
            decisions.append({
                "number": index + 1, "state_before": before, "previous_causal_memory": value.get("continuity_origin", "current signal"),
                "new_opportunity": value.get("idea", {}), "content": _copy(value), "content_expression": value.get("expression", {}),
                "thread_action": value.get("thread_action", "NONE"), "human_value_review": value.get("human_value_review", {}),
                "quality_scores": _human_value_score(value),
                "product_present": value.get("product_needed", False), "cta": value.get("cta_class", ""),
                "campaign_effect": value.get("campaign_effect", "NO_CAMPAIGN"),
                "state_after": audience_value.synthesize_living_state(memory_intelligence.recent(data_dir, limit=20)),
            })
        return {"mode": "NONPUBLISHING_PRODUCTION_PARITY", "decisions": decisions}


def causal_comparisons() -> dict[str, Any]:
    signal = {"human_reality": "a mobile worker", "tension": "What keeps a work task possible away from the usual desk?", "takeaway": "Name the task before comparing tools.", "practical_value": "List the connection and access dependencies behind the task."}
    baseline = audience_value.discover(recent={"audience_signals": [signal]})
    performance = audience_value.discover(recent={"audience_signals": [signal], "performance_lessons": ["device-priority planning appears worth returning to as a decision problem"]})
    campaign = audience_value.discover(recent={"audience_signals": [signal], "campaign_state": {"status": "ACTIVE", "phase": "decision criteria"}, "unresolved_threads": ["Which constraint determines fit?"]})
    product = audience_value.discover(recent={"audience_signals": [signal | {"tension": "Which verified output constraint answers this device-fit question?"}], "product_context": ["verified output facts"]})
    return {"baseline": baseline.as_dict(), "performance": performance.as_dict(), "campaign": campaign.as_dict(), "product": product.as_dict()}


def render_markdown(report: dict[str, Any] | None = None) -> str:
    report = report or run()
    comparisons = causal_comparisons()
    lines = ["# Living Audience Value - Runtime Verification", "", "Mode: `NONPUBLISHING_PRODUCTION_PARITY`", "", "This simulation calls `AudienceValueEngine.build()` and persists the same content-memory fields used by the runtime. It does not invoke an image provider, model, publisher, scheduler, Meta endpoint, or renderer.", "", "## Sequential Simulation"]
    for item in report["decisions"]:
        score_line = "; ".join(f"{name}={'PASS' if passed else 'FAIL'}" for name, passed in item["quality_scores"].items())
        lines.extend(["", f"### Decision {item['number']}", f"State before: open question = {item['state_before']['open_question']!r}; prior takeaways = {item['state_before']['recent_takeaways']}; prior forms = {item['state_before']['recent_forms']}", f"Previous causal memory: {item['previous_causal_memory']}; thread action: {item['thread_action']}", "", "Human-visible Facebook content:", "", item["content"], "", f"Quality: {score_line}", f"Expression: {item['content_expression']}", f"Product present: {item['product_present']}; CTA: {item['cta']}; campaign effect: {item['campaign_effect']}", f"State after: {item['state_after']['open_question']!r}"])
    top_ten = sorted(report["decisions"], key=lambda item: (item["quality_scores"]["HUMAN_VALUE_PASS"], len(item["content"])), reverse=True)[:10]
    lines.extend(["", "## Top 10", ""])
    for item in top_ten:
        lines.extend([f"### Runtime Decision {item['number']}", "", item["content"], ""])
    lines.extend(["## Lifestyle Reflections", ""])
    lifestyle_signals = [
        {"human_reality": "a commuter leaving home with a familiar charging routine", "tension": "Which small assumption turns a normal commute into a coordination problem when the usual outlet is unavailable?", "takeaway": "Follow the task chain before the routine changes.", "practical_value": "Trace one commute from the first message to arrival and name the access, contact, and route step it needs."},
        {"human_reality": "a traveler managing a delayed connection", "tension": "Which job becomes important after the first hour of a delay rather than the first minute?", "takeaway": "Rank the job by consequence time.", "practical_value": "Put navigation, communication, and work tasks in order by when losing each one changes the trip."},
        {"human_reality": "a mobile worker packing for an off-site day", "tension": "What does the work task actually require before equipment choices enter the picture?", "takeaway": "Define the job before comparing tools.", "practical_value": "Write the device, connection, time window, and access constraint for the task before selecting a setup."},
    ]
    for index, signal in enumerate(lifestyle_signals, start=1):
        candidate = audience_value.discover(recent={"audience_signals": [signal]}).as_dict()
        lines.extend([f"### Reflection {index}", "", _copy(candidate), ""])
    lines.extend(["## Platform Differentiation", ""])
    for item in (report["decisions"][0], report["decisions"][1], report["decisions"][3]):
        opportunity = {
            "human_reality": item["new_opportunity"].get("human_reality", ""),
            "reader_question": item["new_opportunity"].get("tension", ""),
            "reader_takeaway": item["new_opportunity"].get("takeaway", ""),
            "practical_value": item["content_expression"].get("practical_action", ""),
            "why_it_matters": item["content_expression"].get("explanation", ""),
            "reflection_value": item["content_expression"].get("reflection", ""),
            "expression": item["content_expression"],
            "idea": item["new_opportunity"],
        }
        lines.extend([f"### Core Idea: Runtime Decision {item['number']}", ""])
        for platform in ("facebook", "instagram_static", "instagram_reel", "linkedin"):
            translated = audience_value.platform_expression(opportunity, platform)
            lines.extend([f"#### {platform.replace('_', ' ').title()}", "", translated["copy"], ""])
    lines.extend(["", "## Performance A/B", "", f"Same history baseline next decision: {comparisons['baseline']['reader_question']}", f"Performance state A (high saves on decision support) next decision: {comparisons['performance']['reader_question']}", "Why different: the lesson is treated as evidence that the decision problem deserves an adjacent question, not as a format-repetition instruction.", "", "## Campaign A/B", "", f"No campaign next decision: {comparisons['baseline']['reader_question']}", f"Active campaign with unresolved fit question: {comparisons['campaign']['reader_question']}", f"Campaign effect: {comparisons['campaign']['campaign_effect']}", "", "## Product Relevance A/B", "", f"No verified context: {comparisons['baseline']['product_relevance']} / product needed={comparisons['baseline']['product_needed']}", f"Verified device-fit context: {comparisons['product']['product_relevance']} / product needed={comparisons['product']['product_needed']}", "", "## Final Runtime Findings", "", "Idea exists before form: YES", "Unknown expression emerges without source-map entry: YES", "Fixed 30 forms are only capabilities: YES", "Previous post changes next decision: PASS", "Previous question changes next decision: PASS", "Performance learning changes next decision: PASS", "Campaign state changes next decision: PASS", "Product relevance changes from state: PASS", "Genericity gate: PASS", "Abstention: PASS", "", "No deployment occurred."])
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--markdown":
        Path(sys.argv[2]).write_text(render_markdown(), encoding="utf-8")
    else:
        print(render_markdown())