from __future__ import annotations

import os
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

import audience_value_lab
import generate_posts
import audience_value_verification
import audience_value_runtime_simulation
import living_campaign_runtime_simulation
from social import audience_value, engines, living_intelligence, memory_intelligence, orchestrator, performance_learning


def test_lab_has_thirty_diverse_nonpublishing_value_concepts():
    result = audience_value_lab.run()

    assert result["mode"] == "NONPUBLISHING_AUDIENCE_VALUE_LAB"
    assert result["concept_count"] >= 30
    assert result["product_free_count"] >= 15
    assert result["no_cta_count"] >= 3
    assert len({concept["content_form"] for concept in result["concepts"]}) >= 24
    assert all("human_visible_copy" in item for item in result["representative_content"])


def test_audience_value_engine_uses_living_state_and_persists_takeaway_contract(tmp_path):
    brief = engines.AudienceValueEngine().build(
        recent={"audience_value_forms": ["tip_and_trick"], "reader_takeaways": []},
        rotation_index=2,
    )

    value = brief.audience_value
    assert value["content_form"] != "tip_and_trick"
    assert value["reader_question"]
    assert value["reader_takeaway"]
    assert not value["product_needed"]

    memory_intelligence.append_content_record(
        {
            "audience_value_form": value["content_form"],
            "human_reality": value["human_reality"],
            "reader_question": value["reader_question"],
            "reader_takeaway": value["reader_takeaway"],
        },
        data_dir=str(tmp_path),
    )
    recent = memory_intelligence.recent(str(tmp_path))
    assert recent["audience_value_forms"] == [value["content_form"]]
    assert recent["reader_questions"] == [value["reader_question"]]
    assert recent["reader_takeaways"] == [value["reader_takeaway"]]
    assert recent["human_realities"] == [value["human_reality"]]


def test_audience_value_engine_can_abstain_when_only_stale_takeaway_remains():
    stale_recent = {
        "audience_value_forms": [item[0] for item in audience_value._EXPERIENCES],
        "reader_takeaways": [item[2] for item in audience_value._TERRITORIES],
    }

    decision = audience_value.discover(recent=stale_recent, rotation_index=0)

    assert decision.abstain
    assert decision.abstain_reason == "no_fresh_audience_value_opportunity"


def test_representative_copy_is_valuable_without_product_or_purchase_cta():
    concept = audience_value.lab_concepts()[2]
    copy = audience_value.representative_copy(concept)

    assert not concept["product_needed"]
    assert "PowerPulse" not in copy
    assert "buy" not in copy.lower()
    assert concept["reader_takeaway"] in copy


def test_unverified_audience_value_idea_requires_research_instead_of_posting():
    decision = audience_value.discover(recent={"audience_signals": [{
        "human_reality": "a traveler relying on public charging",
        "tension": "Which airports currently provide reliable charging at every gate?",
        "takeaway": "Verify access before promising it.",
        "practical_value": "Avoid presenting an unverified travel-access claim as guidance.",
        "research_required": True,
        "research_question": "Current airport charging access by terminal and gate.",
    }]})

    assert decision.abstain
    assert decision.abstain_reason == "RESEARCH_REQUIRED"
    assert decision.research_question


def test_product_free_engine_b_contract_survives_orchestration_and_platform_bridge(tmp_path, monkeypatch):
    monkeypatch.setattr(orchestrator, "_llm_copy_beats", lambda *args: None)
    post = orchestrator.SocialIntelligenceOrchestrator(data_dir=str(tmp_path)).create_post(
        preferred_engine="B", record_memory=False
    )
    assert post.anchored_offering is None
    assert post.copy["cta"] == ""
    assert post.copy["strategy_lock"]["positioning"] == "product-free audience value"

    monkeypatch.setattr(generate_posts, "_living_strategy_for_generation", lambda: (None, {}))
    monkeypatch.setattr(generate_posts, "run_social_intelligence", lambda **kwargs: [post.as_dict()])
    legacy = generate_posts._route_generate_orchestrator("audience-value", preferred_engine="B")

    assert legacy["audience_value_only"] is True
    assert legacy["product_id"] is None
    assert legacy["destination_url"] == ""
    for package in legacy["platform_posts"].values():
        assert package["cta"] == ""
        assert package["destination_url"] == ""
        assert package["utm_url"] == ""
        assert "http" not in package["final_caption"]


def test_state_derived_idea_can_invent_a_form_before_expression_selection():
    decision = audience_value.discover(recent={"audience_signals": [{
        "human_reality": "a family coordinating a late pickup",
        "tension": "One task depends on a phone, map, contact, and car cable.",
        "takeaway": "Trace the task, not the device.",
        "practical_value": "Map the chain from message to completed pickup.",
        "structure_hint": "dependency_map",
    }]})

    assert decision.content_form == "dependency map"
    assert decision.expression["expression_structure"]
    assert "dependency_map" not in decision.content_form
    assert "invented" in decision.state_reason


def test_nonpublishing_verification_proves_coverage_and_meaningful_continuity():
    report = audience_value_verification.run()

    assert len(report["novel_form_examples"]) >= 5
    assert all(item["invented_creative_form"] not in {form[0] for form in audience_value._EXPERIENCES} for item in report["novel_form_examples"])
    assert len(report["human_value_examples"]) >= 15
    assert len(report["sequential_simulation"]) == 12
    assert len({item["content_experience"]["full_idea"] for item in report["sequential_simulation"]}) == 12
    assert {item["lifecycle"] for item in report["campaign_simulation"]} >= {"START", "CONTINUE", "EVOLVE", "PAUSE", "END"}
    assert all(item["classification"] == "RESEARCH_REQUIRED" for item in report["research_cases"])


def test_audience_value_performance_learning_preserves_problem_not_format():
    learning = performance_learning.interpret_audience_value_signal(
        metrics={"saves": 9, "comments": 0}, reader_problem="device-priority planning"
    )

    assert "decision problem" in learning["learning"]
    assert "not another checklist" in learning["next_decision"]


def test_previous_unresolved_thread_causally_changes_next_runtime_idea():
    first = audience_value.discover(recent={"audience_signals": [{
        "human_reality": "a traveler rerouting a trip",
        "tension": "A charged phone is only useful when the route, contact, and next step still work.",
        "takeaway": "Trace the task, not the device.",
        "practical_value": "Map the chain from route change to completed arrival.",
    }]})
    second = audience_value.discover(recent={
        "reader_takeaways": [first.reader_takeaway],
        "human_realities": [first.human_reality],
        "unresolved_threads": ["What dependency matters after the device is charged?"],
    })

    assert second.continuity_origin == first.reader_takeaway
    assert second.reader_question != first.reader_question
    assert second.thread_action == "CONTINUE"
    assert second.continuity_thread["status"] == "RESOLVED"


def test_performance_and_campaign_state_causally_change_runtime_idea():
    baseline = {"audience_signals": [{
        "human_reality": "a mobile worker",
        "tension": "What keeps a work task possible away from the usual desk?",
        "takeaway": "Name the task before comparing tools.",
        "practical_value": "List the connection and access dependencies behind the task.",
    }]}
    high_saves = audience_value.discover(recent=baseline | {"performance_lessons": ["device-priority planning appears worth returning to as a decision problem"]})
    weak_signal = audience_value.discover(recent=baseline)
    campaign = audience_value.discover(recent=baseline | {"campaign_state": {"status": "ACTIVE", "phase": "decision criteria"}, "unresolved_threads": ["Which constraint determines fit?"]})

    assert high_saves.continuity_origin
    assert high_saves.reader_question != weak_signal.reader_question
    assert campaign.campaign_effect == "CONTINUE"
    assert campaign.reader_question != weak_signal.reader_question


def test_product_relevance_emerges_from_state_not_expression_type():
    signal = {"human_reality": "a person comparing device fit", "tension": "Which verified output constraint answers this device-fit question?", "takeaway": "Match the capability to the job.", "practical_value": "Define the device job before comparing a verified offering."}
    absent = audience_value.discover(recent={"audience_signals": [signal]})
    earned = audience_value.discover(recent={"audience_signals": [signal], "product_context": ["Verified output and compatibility facts"]})

    assert absent.product_relevance == "NOT_RELEVANT"
    assert not absent.product_needed
    assert earned.product_relevance == "NATURALLY_RELEVANT"
    assert earned.product_needed


def test_genericity_gate_rejects_thin_advice_and_platform_expression_is_native():
    generic = audience_value.discover(recent={"audience_signals": [{
        "human_reality": "everyone", "tension": "Be prepared?", "takeaway": "Plan ahead.", "practical_value": "Make better choices.",
    }]})
    specific = audience_value.discover(recent={"audience_signals": [{
        "human_reality": "a parent coordinating a late pickup", "tension": "Which missing dependency stops a pickup plan after the phone is charged?", "takeaway": "Trace the task, not the device.", "practical_value": "Map the contact, route, cable, and next action before the delay happens.",
    }]})

    assert generic.abstain and generic.abstain_reason == "human_value_gate_rejected"
    expressions = {platform: audience_value.platform_expression(specific, platform)["copy"] for platform in ("facebook", "instagram_static", "instagram_reel", "linkedin")}
    assert len(set(expressions.values())) == 4
    assert all(specific.reader_takeaway in text or platform == "instagram_reel" for platform, text in expressions.items())


def test_production_parity_simulation_calls_real_engine_b_with_persisted_memory():
    result = audience_value_runtime_simulation.run()

    assert result["mode"] == "NONPUBLISHING_PRODUCTION_PARITY"
    assert len(result["decisions"]) == 12
    assert result["decisions"][1]["previous_causal_memory"]
    assert result["decisions"][1]["state_before"]["open_question"]
    assert all(not item["product_present"] for item in result["decisions"])


def test_planning_language_cannot_reenter_as_an_audience_continuity_question():
    state = audience_value.synthesize_living_state({
        "unresolved_threads": ["Answer the unresolved question created after the last post."],
        "human_realities": ["a traveler rerouting a trip"],
    })

    assert state["open_threads"] == []
    assert state["open_question"] == ""


def test_semantic_successor_advances_concept_then_resolves_its_thread():
    first = audience_value.discover(recent={"audience_signals": [{
        "human_reality": "a parent coordinating a delayed pickup",
        "tension": "Which invisible dependency can stop a pickup plan after the phone is charged?",
        "takeaway": "Trace the task, not the device.",
        "practical_value": "Map the contact, route, cable, and next action before the delay happens.",
    }]})
    next_state = {
        "continuity_threads": [first.continuity_thread],
        "reader_takeaways": [first.reader_takeaway],
        "human_realities": [first.human_reality],
    }
    second = audience_value.discover(recent=next_state)

    assert second.thread_action == "CONTINUE"
    assert second.idea["current_concept"] == "priority"
    assert second.reader_question == "Which part of this routine would matter first if access changed?"
    assert second.continuity_thread["status"] == "RESOLVED"
    assert "previous" not in second.reader_question.lower()


def test_performance_lesson_is_consumed_after_it_changes_one_runtime_decision():
    lesson = "device-priority planning appears worth returning to as a decision problem"
    state = {
        "performance_lessons": [lesson],
        "human_realities": ["a mobile worker"],
    }
    first = audience_value.discover(recent=state)
    second = audience_value.discover(recent=state | {
        "performance_lessons_applied": [first.performance_lesson_applied],
    })

    assert first.continuity_origin == "performance lesson"
    assert first.performance_lesson_applied == lesson
    assert second.continuity_origin != "performance lesson"


def test_real_runtime_sequence_has_no_recursive_system_language_or_single_expression_loop():
    result = audience_value_runtime_simulation.run()
    decisions = result["decisions"]
    questions = [item["new_opportunity"].get("tension", "") for item in decisions]
    expressions = [item["content_expression"].get("expression_family", "") for item in decisions]
    realities = [item["new_opportunity"].get("human_reality", "") for item in decisions]
    content = "\n".join(item["content"] for item in decisions).lower()

    assert len(decisions) == 12
    assert not any("answer the unresolved" in question.lower() for question in questions)
    assert "previous question" not in content
    assert len(set(expressions)) >= 4
    assert len(set(realities)) >= 4
    assert any(item["previous_causal_memory"] == "performance lesson" for item in decisions)


def test_expression_packet_has_specific_nonrepeating_action_anchor_and_takeaway():
    dependency = audience_value.discover(recent={"audience_signals": [{
        "human_reality": "a parent coordinating a delayed pickup",
        "tension": "Which invisible dependency can stop a pickup plan after the phone is charged?",
        "takeaway": "Trace the task, not the device.",
        "practical_value": "Map the contact, route, cable, and next action before the delay happens.",
    }]})
    priority = audience_value.discover(recent={"audience_signals": [{
        "human_reality": "a mobile worker",
        "tension": "Which job becomes important first when access changes?",
        "takeaway": "Rank work by consequence, not convenience.",
        "practical_value": "List the jobs that cannot wait during a travel delay.",
    }]})

    for decision in (dependency, priority):
        expression = decision.expression
        assert expression["practical_action"] == decision.practical_value
        assert expression["memory_anchor"] == decision.desired_memory_anchor
        assert expression["hook"].lower().strip(" ?.") != decision.reader_takeaway.lower().strip(" ?.")
        assert expression["explanation"] != decision.practical_value
        assert "audit a routine" not in decision.practical_value.lower()
    assert dependency.practical_value != priority.practical_value
    assert dependency.desired_memory_anchor != priority.desired_memory_anchor


def test_branch_retains_a_deferred_successor_without_reopening_it_immediately():
    first = audience_value.discover(recent={"audience_signals": [{
        "human_reality": "a traveler rerouting a trip",
        "tension": "Which dependency keeps a route change from becoming a missed arrival?",
        "takeaway": "Trace the task, not the device.",
        "practical_value": "Map the route, contact, cable, and next action behind the arrival.",
    }]})
    state = audience_value.synthesize_living_state({"continuity_threads": [first.continuity_thread]})

    assert first.thread_action == "BRANCH"
    assert first.continuity_thread["branch_successors"]
    assert state["open_threads"][0]["unresolved_concept"] == "priority"
    assert len(state["deferred_threads"]) == 1
    assert state["deferred_threads"][0]["unresolved_concept"] == "requirements"


def test_deferred_and_closed_threads_do_not_reopen_as_active_opportunities():
    deferred = {
        "thread_id": "requirements:travel", "status": "DEFERRED", "unresolved_concept": "requirements",
        "unresolved_question": "What does the important job need in order to keep working?",
        "defer_reason": "A stronger opportunity is current.", "revisit_condition": "After priority resolves.",
    }
    closed = {
        "thread_id": "tradeoff:travel", "status": "CLOSED", "unresolved_concept": "tradeoff",
        "unresolved_question": "Which tradeoff matters after you know what fits?",
        "close_reason": "The semantic question is resolved.",
    }
    state = audience_value.synthesize_living_state({"continuity_threads": [deferred, closed]})

    assert state["open_threads"] == []
    assert state["deferred_threads"] == [deferred]
    assert state["closed_threads"] == [closed]


def test_terminal_tradeoff_uses_close_lifecycle_action():
    decision = audience_value.discover(recent={"audience_signals": [{
        "human_reality": "a commuter carrying a daily work setup",
        "tension": "Which tradeoff can this routine realistically carry every day?",
        "takeaway": "Choose the constraint the routine can keep honoring.",
        "practical_value": "Name the size, access, and upkeep tradeoff you can manage repeatedly.",
    }]})

    assert decision.thread_action == "CLOSE"
    assert decision.continuity_thread["status"] == "CLOSED"
    assert decision.continuity_thread["close_reason"]


def test_campaign_runtime_lifecycle_starts_evolves_pauses_resumes_and_ends():
    seed = {"objective": "help travelers make a resilient coordination decision", "human_problem": "a delayed trip depends on more than a charged phone"}
    started = living_intelligence.campaign_runtime_decision(seed, audience_signals=[{"human_reality": "a traveler rerouting a trip"}])
    evolved = living_intelligence.campaign_runtime_decision(started["campaign_state"], performance_lessons=["saves show the decision problem deserves deeper support"])
    paused = living_intelligence.campaign_runtime_decision(evolved["campaign_state"], stronger_opportunity=True)
    resumed = living_intelligence.campaign_runtime_decision(paused["campaign_state"], audience_signals=[{"human_reality": "a traveler rerouting a trip"}])
    ended = living_intelligence.campaign_runtime_decision(resumed["campaign_state"] | {"questions_answered": ["What matters first?"], "threads_open": []})

    assert started["decision"] == "START"
    assert evolved["decision"] == "EVOLVE"
    assert paused["decision"] == "PAUSE" and paused["campaign_state"]["revisit_condition"]
    assert resumed["decision"] == "CONTINUE"
    assert ended["decision"] == "END"


def test_campaign_state_is_causal_and_product_relevance_remains_earned():
    signal = {"human_reality": "a mobile worker", "tension": "What keeps a work task possible away from the usual desk?", "takeaway": "Name the task before comparing tools.", "practical_value": "List the connection and access dependencies behind the task."}
    inactive = audience_value.discover(recent={"audience_signals": [signal]})
    campaign = living_intelligence.campaign_runtime_decision({"objective": "move from recognition to decision support", "human_problem": signal["tension"]}, audience_signals=[signal])
    active = audience_value.discover(recent={"audience_signals": [signal], "campaign_state": campaign["campaign_state"] | {"unresolved_question": "Which constraint determines fit?"}})
    absent = audience_value.discover(recent={"audience_signals": [signal | {"tension": "Which output constraint determines fit?"}]})
    earned = audience_value.discover(recent={"audience_signals": [signal | {"tension": "Which verified output constraint determines fit?"}], "product_context": ["verified output facts"]})

    assert active.reader_question != inactive.reader_question
    assert absent.product_relevance == "NOT_RELEVANT"
    assert earned.product_relevance == "NATURALLY_RELEVANT" and earned.product_needed


def test_nonpublishing_living_campaign_runtime_proves_product_free_entry_removal_and_pause():
    report = living_campaign_runtime_simulation.run()
    scenarios = {scenario["name"]: scenario for scenario in report["scenarios"]}
    product_free = scenarios["product_free"]["posts"]
    earned = scenarios["earned_product"]["posts"]
    paused = scenarios["pause_for_fresh_value"]["posts"]

    assert report["mode"] == "NONPUBLISHING_LIVING_CAMPAIGN_RUNTIME"
    assert all(not post["product_present"] and post["cta_class"] == "NO_CTA" for post in product_free)
    assert [post["product_relevance"] for post in earned[:3]] == ["NOT_RELEVANT", "NATURALLY_RELEVANT", "NOT_RELEVANT"]
    assert earned[1]["product_present"] and not earned[2]["product_present"]
    assert paused[1]["lifecycle"] == "PAUSE"
    assert all(post["quality"]["HUMAN_VALUE_PASS"] for scenario in scenarios.values() for post in scenario["posts"])


def test_earned_product_narrative_role_stays_light_and_answers_campaign_question():
    value = audience_value.discover(recent={"campaign_state": {
        "status": "ACTIVE", "human_reality": "a mobile worker on an off-site day",
        "audience_understanding": "the task and its constraints are already defined",
        "unresolved_question": "How can you tell whether an option fits the job you defined?",
    }, "product_context": ["Verified output and compatibility facts answer the fit question."]})
    campaign = {"current_audience_understanding": "the task and its constraints are already defined", "content_roles_used": ["DECISION_SUPPORT"]}
    narrative = living_intelligence.product_narrative_decision(campaign, value.as_dict(), verified_facts=["Verified output and compatibility facts answer the fit question."], product_name="the verified mobile-work option")
    copy = living_intelligence.product_entry_copy(value.as_dict(), narrative)

    assert value.product_relevance == "NATURALLY_RELEVANT"
    assert narrative["role"] == "FIT_DEMONSTRATION"
    assert narrative["commercial_intensity"] == "LIGHT"
    assert narrative["cta_class"] == "COMPARE"
    assert narrative["product_entry_question"] == value.reader_question
    assert value.human_reality in copy and narrative["verified_fact"] in copy
    assert "buy" not in copy.lower()


def test_product_narrative_rejects_a_hijack_without_question_reality_or_evidence():
    rejected = living_intelligence.product_narrative_decision(
        {"content_roles_used": ["DECISION_SUPPORT"]},
        {"product_relevance": "NATURALLY_RELEVANT"},
        verified_facts=[],
    )

    assert rejected["narrative_hijack"]
    assert rejected["role"] == "NONE"
    assert "NARRATIVE_HIJACK" in rejected["reason"]