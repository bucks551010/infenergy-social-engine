"""Nonpublishing campaign verification using campaign policy plus real Engine B."""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from social import audience_value, engines, living_intelligence, memory_intelligence
from audience_value_runtime_simulation import _copy, _human_value_score


def _record(value: dict[str, Any], campaign: dict[str, Any], data_dir: str) -> None:
    memory_intelligence.append_content_record({
        "engine": "B", "audience_value_form": value.get("content_form", ""),
        "human_reality": value.get("human_reality", ""), "reader_question": value.get("reader_question", ""),
        "reader_takeaway": value.get("reader_takeaway", ""), "practical_value": value.get("practical_value", ""),
        "unresolved_thread": value.get("unresolved_question", ""), "continuity_thread": value.get("continuity_thread", {}),
        "question_answered": value.get("reader_question", ""), "question_created": value.get("unresolved_question", ""),
        "thread_action": value.get("thread_action", "NONE"), "campaign_state": campaign,
        "campaign_effect": value.get("campaign_effect", "NO_CAMPAIGN"),
        "product_relevance_change": value.get("product_relevance", "NOT_RELEVANT"),
        "product_narrative": value.get("product_narrative", {}),
        "audience_value_cta_class": value.get("cta_class", ""),
    }, data_dir=data_dir)


def _run_scenario(name: str, seed: dict[str, Any], *, count: int, product_at: int | None = None, pause_at: int | None = None) -> dict[str, Any]:
    with tempfile.TemporaryDirectory() as data_dir:
        campaign = dict(seed["campaign"])
        initial_signal = dict(seed["signal"])
        decisions: list[dict[str, Any]] = []
        for index in range(count):
            recent = memory_intelligence.recent(data_dir, limit=20)
            state = audience_value.synthesize_living_state(recent)
            stronger = pause_at == index
            meeting = living_intelligence.campaign_runtime_decision(
                campaign,
                audience_signals=[initial_signal] if index == 0 else ([seed["fresh_signal"]] if stronger else []),
                open_threads=state["open_threads"], deferred_threads=state["deferred_threads"],
                stronger_opportunity=stronger,
                performance_lessons=["saves identify a decision problem worth deepening"] if index == 1 and name == "product_free" else [],
            )
            decision_recent = living_intelligence.campaign_decision_input(recent, meeting)
            if index == 0 or stronger:
                decision_recent["audience_signals"] = [seed["fresh_signal"] if stronger else initial_signal]
            if product_at == index:
                decision_recent["product_context"] = list(seed["verified_facts"])
            brief = engines.AudienceValueEngine().build(recent=decision_recent, rotation_index=index)
            value = brief.audience_value
            narrative = living_intelligence.product_narrative_decision(
                meeting["campaign_state"], value,
                verified_facts=list(seed["verified_facts"]) if product_at == index else [],
                product_name=str(seed.get("product_name") or ""),
            )
            value["product_narrative"] = narrative
            old_copy = _copy(value)
            rendered_copy = living_intelligence.product_entry_copy(value, narrative) or old_copy
            campaign = living_intelligence.apply_campaign_post(meeting["campaign_state"], value)
            _record(value, campaign, data_dir)
            decisions.append({
                "number": index + 1, "lifecycle": meeting["decision"], "lifecycle_reason": meeting["reason"],
                "campaign_phase": campaign.get("current_phase", ""), "role": (campaign.get("content_roles_used") or [""])[-1],
                "state_before": meeting["campaign_state"], "human_reality": value.get("human_reality", ""),
                "question_answered": value.get("reader_question", ""), "question_created": value.get("unresolved_question", ""),
                "audience_understanding_before": meeting["campaign_state"].get("current_audience_understanding", ""),
                "audience_understanding_after": campaign.get("current_audience_understanding", ""),
                "product_relevance": value.get("product_relevance", "NOT_RELEVANT"), "product_present": value.get("product_needed", False),
                "cta_class": narrative.get("cta_class", value.get("cta_class", "")), "expression": value.get("expression", {}),
                "product_narrative": narrative, "old_facebook_copy": old_copy, "facebook_copy": rendered_copy,
                "quality": _human_value_score(value) | {"NARRATIVE_CONTINUITY": not narrative.get("narrative_hijack", False), "PRODUCT_ADDS_VALUE": not value.get("product_needed") or narrative.get("role") != "NONE", "PRODUCT_DOES_NOT_HIJACK": not narrative.get("narrative_hijack", False)}, "campaign_after": campaign,
            })
        return {"name": name, "posts": decisions, "final_campaign": campaign}


def run() -> dict[str, Any]:
    product_free = _run_scenario("product_free", {
        "campaign": {"objective": "help travelers identify fragile coordination dependencies", "human_problem": "a delayed trip depends on more than a charged phone", "narrative_thesis": "trace the task before comparing tools"},
        "signal": {"human_reality": "a traveler rerouting a trip", "tension": "Which invisible dependency can stop a rerouted trip after the phone is charged?", "takeaway": "Trace the task, not the device.", "practical_value": "Map the route, contact, cable, and next action behind the arrival."},
        "fresh_signal": {}, "verified_facts": [],
    }, count=4)
    earned_product = _run_scenario("earned_product", {
        "campaign": {"status": "ACTIVE", "objective": "move mobile workers from requirements to fit", "human_problem": "a work task has connection and access constraints", "human_reality": "a mobile worker on an off-site day", "narrative_thesis": "define the job before comparing capability", "current_audience_understanding": "Compare capability against the task, not a headline number.", "unresolved_question": "How can you tell whether an option fits the job you defined?"},
        "signal": {"human_reality": "a mobile worker", "tension": "How can you tell whether an option fits the job you defined?", "takeaway": "Compare capability against the real task instead of a headline number.", "practical_value": "Compare the defined device, connection, time window, and constraint before selecting an option."},
        "fresh_signal": {}, "product_name": "the verified mobile-work option", "verified_facts": ["Its verified output and compatibility facts answer the defined device-fit question."],
    }, count=4, product_at=1)
    pause = _run_scenario("pause_for_fresh_value", {
        "campaign": {"objective": "help commuters understand routine dependencies", "human_problem": "a commute can fail through a hidden coordination dependency", "narrative_thesis": "recognize the dependency before it becomes an interruption"},
        "signal": {"human_reality": "a commuter changing a pickup plan", "tension": "Which dependency can stop a pickup plan after the phone is charged?", "takeaway": "Trace the task, not the device.", "practical_value": "Map the contact, route, cable, and next action before the delay happens."},
        "fresh_signal": {"human_reality": "a traveler facing a long delay", "tension": "Which job becomes important after the first hour of a delay?", "takeaway": "Rank work by consequence, not convenience.", "practical_value": "Put navigation, communication, and work tasks in order by when losing each changes the trip."},
        "verified_facts": [],
    }, count=3, pause_at=1)
    return {"mode": "NONPUBLISHING_LIVING_CAMPAIGN_RUNTIME", "scenarios": [product_free, earned_product, pause]}


def render_markdown(report: dict[str, Any] | None = None) -> str:
    report = report or run()
    lines = ["# Living Campaign + Earned Product Relevance", "", "Mode: `NONPUBLISHING_LIVING_CAMPAIGN_RUNTIME`", "", "This report calls campaign_runtime_decision(), AudienceValueEngine.build(), and memory_intelligence.append_content_record(). It does not publish, call Meta, generate media, or render video."]
    for scenario in report["scenarios"]:
        lines.extend(["", f"## Scenario: {scenario['name']}"])
        for post in scenario["posts"]:
            quality = "; ".join(f"{key}={'PASS' if value else 'FAIL'}" for key, value in post["quality"].items())
            lines.extend(["", f"### Post {post['number']}", f"Lifecycle: {post['lifecycle']} - {post['lifecycle_reason']}", f"Phase: {post['campaign_phase']}; role: {post['role']}; human reality: {post['human_reality']}", f"Question answered: {post['question_answered']}", f"Question created: {post['question_created']}", f"Understanding before: {post['audience_understanding_before']}", f"Understanding after: {post['audience_understanding_after']}", f"Product relevance: {post['product_relevance']}; product present: {post['product_present']}; product role: {post['product_narrative'].get('role')}; intensity: {post['product_narrative'].get('commercial_intensity')}; CTA: {post['cta_class']}", "", "Facebook copy:", "", post["facebook_copy"], "", f"Quality: {quality}"])
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    import sys
    if len(sys.argv) == 3 and sys.argv[1] == "--markdown":
        Path(sys.argv[2]).write_text(render_markdown(), encoding="utf-8")
    else:
        print(render_markdown())