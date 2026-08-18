"""Build validated text-only social candidates for later slot-time publication."""

from __future__ import annotations

import os
from typing import Any

import generate_posts
import run_engine
from anti_repeat import load_anti_repeat_windows
from score_content import score_content
from social.candidate_pool import CandidatePool, ROTATION_DIMENSIONS, build_rotation_ledger
from social.publish_decision import decide as decide_publication
from validate_product_claims import validate_generated_content


def _rotation_selection(content: dict[str, Any]) -> dict[str, str]:
    brief = content.get("strategic_brief") if isinstance(content.get("strategic_brief"), dict) else {}
    return {
        "product_id": str(content.get("product_id") or ""),
        "topic": str(content.get("topic") or ""),
        "hook_category": str(content.get("hook_category") or content.get("selected_hook_type") or ""),
        "scenario": str(content.get("scenario") or ""),
        "lesson": str(content.get("lesson") or content.get("educational_lesson") or ""),
        "awareness_level": str(content.get("awareness_level") or brief.get("awareness_level") or ""),
        "emotional_driver": str(content.get("emotional_driver") or brief.get("emotional_driver") or ""),
        "copy_structure": str(content.get("copy_structure") or brief.get("copy_structure") or ""),
    }


def _has_batch_collision(selection: dict[str, str], used: dict[str, set[str]]) -> bool:
    return any(selection.get(dimension) and selection[dimension] in used[dimension] for dimension in ROTATION_DIMENSIONS)


def _record_batch_selection(selection: dict[str, str], used: dict[str, set[str]]) -> None:
    for dimension, value in selection.items():
        if value:
            used[dimension].add(value)


def build_pool(*, target_depth: int | None = None, max_attempts: int | None = None) -> dict[str, Any]:
    """Fill the pool with candidates that pass every gate independent of publish time."""
    target_depth = target_depth or int(os.environ.get("CANDIDATE_POOL_TARGET_DEPTH", "6"))
    max_attempts = max_attempts or int(os.environ.get("CANDIDATE_POOL_MAX_BATCH_ATTEMPTS", "10"))
    data_dir = generate_posts.DATA_DIR
    pool = CandidatePool(data_dir, ttl_days=int(os.environ.get("CANDIDATE_POOL_TTL_DAYS", "7")))
    history = generate_posts.load_history()
    generate_posts.load_products()
    selection_exclusions = generate_posts.product_selection_report()
    ledger = build_rotation_ledger(history, load_anti_repeat_windows())
    used = {dimension: set() for dimension in ROTATION_DIMENSIONS}
    accepted: list[str] = []
    rejected: list[dict[str, Any]] = []
    previous_text_only = os.environ.get("POST_TEXT_ONLY")
    os.environ["POST_TEXT_ONLY"] = "true"
    try:
        for _ in range(max_attempts):
            if pool.depth() >= target_depth:
                break
            content = generate_posts.generate(os.environ.get("CANDIDATE_POOL_SLOT", "morning"))
            selection = _rotation_selection(content)
            if _has_batch_collision(selection, used):
                rejected.append({"reason": "in_batch_rotation_collision", "rotation_selected": selection})
                continue

            creative_director = content.get("creative_director") if isinstance(content.get("creative_director"), dict) else {}
            human_truth_gate = creative_director.get("human_truth_gate") if isinstance(creative_director.get("human_truth_gate"), dict) else {}
            if human_truth_gate and not human_truth_gate.get("ready", False):
                rejected.append({"reason": "human_truth_gate_rejected", "rotation_selected": selection, "failures": human_truth_gate.get("failures", [])})
                continue

            run_engine._enforce_candidate_claim_boundary(content)
            validation = validate_generated_content(content)
            scoring = score_content(content)
            decision = decide_publication(
                legacy_score=scoring,
                validation=validation,
                duplicates={"ok": True, "reasons": []},
                conversion_quality_score=float((content.get("conversion_quality_score") or {}).get("total", 100) or 100),
                orchestrator_quality=content.get("orchestrator_quality"),
                evidence_readiness=run_engine._evidence_readiness(content),
            )
            gate_results = {
                "validation": validation,
                "quality_score": scoring.get("total"),
                "publish_decision": decision,
                "evidence_readiness": content.get("evidence_readiness", {}),
                "visual_generation_deferred": True,
            }
            if not decision.get("publishable"):
                rejected.append({"reason": "batch_gate_failed", "rotation_selected": selection, "batch_gate_results": gate_results})
                continue

            content["validation_status"] = "passed" if validation.get("passed") else "failed"
            content["validation_errors"] = validation.get("errors", [])
            content["quality_score"] = scoring.get("total")
            content["quality_component_scores"] = scoring.get("component_scores", {})
            content["publish_decision"] = decision
            candidate = pool.add(content, rotation=selection, batch_gate_results=gate_results)
            _record_batch_selection(selection, used)
            accepted.append(candidate["candidate_id"])
    finally:
        if previous_text_only is None:
            os.environ.pop("POST_TEXT_ONLY", None)
        else:
            os.environ["POST_TEXT_ONLY"] = previous_text_only

    result = {
        "pool_depth": pool.depth(),
        "target_depth": target_depth,
        "accepted_candidate_ids": accepted,
        "rejected": rejected,
        "ledger_unavailable": ledger["ledger_unavailable"],
        "product_selection_exclusions": selection_exclusions,
    }
    payload = pool._load()
    reports = payload.setdefault("batch_reports", [])
    reports.append(result)
    payload["batch_reports"] = reports[-30:]
    pool._save(payload)
    return result


if __name__ == "__main__":
    print(build_pool())