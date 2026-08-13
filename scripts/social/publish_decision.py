"""One authoritative decision contract for content publication.

Critics retain their own measurements, but only this module decides whether a
candidate is published, revised, regenerated, or not published. Its stored
fields explain that decision rather than creating a second content schema.
"""

from __future__ import annotations

from typing import Any


PUBLISH_SCORE = 82.0
REVISE_SCORE = 75.0
CONVERSION_SCORE = 80.0


def decide(
    *,
    legacy_score: dict[str, Any],
    validation: dict[str, Any],
    duplicates: dict[str, Any],
    conversion_quality_score: float = 100.0,
    orchestrator_quality: dict[str, Any] | None = None,
    visual_errors: list[str] | None = None,
) -> dict[str, Any]:
    """Return the only publish decision consumed by the runtime."""
    legacy_total = float(legacy_score.get("total") or 0)
    critic_total = (orchestrator_quality or {}).get("overall")
    critic_total = float(critic_total) if critic_total is not None else None
    reasons: list[str] = []
    critic_component_scores = dict((orchestrator_quality or {}).get("factors") or {})
    critic_findings = [str(item) for item in (orchestrator_quality or {}).get("reasons", []) if str(item)]

    if not validation.get("passed", False):
        reasons.extend(str(error) for error in validation.get("errors", []))
    if not duplicates.get("ok", True):
        reasons.extend(str(reason) for reason in duplicates.get("reasons", []))
    if visual_errors:
        reasons.extend(visual_errors)
    if reasons:
        decision = "do_not_publish"
    elif legacy_total < REVISE_SCORE:
        decision = "do_not_publish"
        reasons.append("runtime_quality_below_regeneration_floor")
    elif critic_total is not None and critic_total < REVISE_SCORE:
        decision = "regenerate"
        reasons.append("orchestrator_critic_below_regeneration_floor")
    elif legacy_total < PUBLISH_SCORE or conversion_quality_score < CONVERSION_SCORE:
        decision = "regenerate"
        reasons.append("candidate_needs_regeneration")
    elif critic_total is not None and critic_total < PUBLISH_SCORE:
        decision = "revise"
        reasons.append("orchestrator_critic_requires_revision")
    else:
        decision = "publish"

    return {
        "decision": decision,
        "publishable": decision == "publish",
        "legacy_score": legacy_total,
        "orchestrator_critic_score": critic_total,
        "critic_total_score": critic_total,
        "critic_component_scores": critic_component_scores,
        "critic_findings": critic_findings,
        "critic_evidence": {name: value for name, value in critic_component_scores.items() if float(value) < 0.82},
        "critic_decision_reason": "publish_threshold_met" if critic_total is None or critic_total >= PUBLISH_SCORE else "critic_score_below_publish_threshold",
        "conversion_quality_score": float(conversion_quality_score),
        "reasons": reasons,
        "platform_results": legacy_score.get("platform_results", {}),
    }