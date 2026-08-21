from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import run_engine
from social import claim_governance, claim_intelligence, publish_decision


def _final_decision(readiness: dict) -> dict:
    return publish_decision.decide(
        legacy_score={"total": 97.0, "platform_results": {}},
        validation={"passed": True, "errors": []},
        duplicates={"ok": True, "reasons": []},
        conversion_quality_score=100.0,
        orchestrator_quality={"overall": 90.0, "critic_findings": []},
        evidence_readiness=readiness,
    )


def test_research_required_original_stays_blocked_and_requests_one_new_supported_angle():
    ledger = claim_intelligence.build_ledger(
        "Available output determines whether the work can proceed; capacity describes reserve after fit is established.",
        verified_facts=[],
        forbidden_claims=[],
    )
    readiness = claim_governance.assess(
        ledger,
        hook="Can this source support the work?",
        decision_insight={"relationship": "Available output determines whether the work can proceed; capacity describes reserve after fit is established."},
        takeaway="Establish fit before reserve.",
    )
    decision = _final_decision(readiness)
    feedback = run_engine._evidence_safe_remediation_feedback({"product_name": "PowerPulse Pro 200"})

    assert readiness["status"] == "RESEARCH_REQUIRED"
    assert decision["publishable"] is False
    assert decision["decision"] == "do_not_publish"
    assert len(feedback) == 4
    assert "materially new" in feedback[1]
    assert "only verified product facts" in feedback[1]


def test_verified_fact_remediation_is_ready_without_erasing_centrality_policy():
    ledger = claim_intelligence.build_ledger(
        "PowerPulse Pro 200 has published 154Wh and 200W specifications.",
        verified_facts=["154Wh", "200W"],
        forbidden_claims=[],
    )
    readiness = claim_governance.assess(
        ledger,
        hook="Pack published power details before travel.",
        decision_insight={},
        takeaway="Use published details as a packing reference.",
    )

    assert readiness["status"] == "READY"
    assert _final_decision(readiness)["publishable"] is True


def test_remediation_attempt_is_bounded_and_research_findings_stay_terminal_after_it():
    decision = {"decision": "do_not_publish", "reasons": ["RESEARCH_REQUIRED"]}

    assert run_engine._retryability_classification(decision, []) == "TERMINAL"
    assert "RESEARCH_REQUIRED" not in run_engine._evidence_safe_remediation_feedback({"product_id": "PPP-200"})[-1]


def test_manual_platform_override_enables_only_requested_platform():
    channels = {"wordpress": False, "facebook": True, "instagram": True, "linkedin": True}
    reasons = {platform: "enabled_for_run" for platform in channels}

    run_engine._apply_manual_platform_override(channels, reasons, ["linkedin"])

    assert channels == {"wordpress": False, "facebook": False, "instagram": False, "linkedin": True}
    assert reasons["facebook"] == "excluded_by_manual_override"
    assert reasons["instagram"] == "excluded_by_manual_override"
    assert reasons["linkedin"] == "enabled_for_run"


def test_final_channel_evidence_excludes_out_of_scope_wordpress_copy():
    content = {
        "selected_hook": "Review the published specification.",
        "product_metrics": ["100W"],
        "wp_content": "This device guarantees medical equipment during a prolonged outage.",
        "platform_posts": {
            "linkedin": {"final_caption": "Review the published 100W specification before choosing."},
        },
    }

    readiness = run_engine._final_channel_evidence_readiness(
        content,
        {"wordpress": False, "facebook": False, "instagram": False, "linkedin": True},
    )

    claims = content["final_channel_claim_ledger"]["claims"]
    assert all("medical equipment" not in str(claim) for claim in claims)
    assert readiness["status"] != "HIGH_RISK_UNVERIFIED"