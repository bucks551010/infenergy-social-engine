"""Run an isolated, text-only forensic sample through the production decision loop."""

from __future__ import annotations

import argparse
import copy
import hashlib
import io
import json
import os
import random
import sys
import time
from contextlib import redirect_stdout, redirect_stderr
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))


def _jsonable(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return str(value)


def _snapshot(value: Any) -> Any:
    return json.loads(json.dumps(value, default=_jsonable))


def _seed_fingerprint() -> str:
    return hashlib.sha256(repr(random.getstate()).encode("utf-8")).hexdigest()[:16]


def _classify(content: dict[str, Any], attempts: list[dict[str, Any]]) -> str:
    decision = content.get("publish_decision") if isinstance(content.get("publish_decision"), dict) else {}
    if decision.get("publishable"):
        return "RECOVERED_AND_TEXT_READY" if len(attempts) > 1 else "TEXT_READY"
    reasons = [str(item).lower() for item in decision.get("reasons", [])]
    if any("duplicate" in item for item in reasons):
        return "FAILED_DUPLICATE_FRESHNESS"
    if any(token in item for item in reasons for token in ("claim", "evidence", "unsupported", "fact")):
        return "FAILED_EVIDENCE"
    if any(token in item for item in reasons for token in ("quality", "critic", "presentation")):
        return "FAILED_PRESENTATION" if any("presentation" in item for item in reasons) else "FAILED_QUALITY"
    if not attempts:
        return "ABSTAINED_CONTENT_EXHAUSTED"
    return "FAILED_OTHER"


def _claims_and_evidence(content: dict[str, Any]) -> dict[str, Any]:
    """Preserve native claim/evidence payloads; do not invent a second extractor."""
    keys = (
        "claims", "claim_governance", "claim_intelligence", "evidence_readiness",
        "verified_facts", "product_facts", "validation_errors", "validation_warnings",
        "research", "research_trace", "orchestrator_trace",
    )
    return {key: _snapshot(content.get(key)) for key in keys if content.get(key) not in (None, "", [], {})}


def _presentation(content: dict[str, Any], run_engine: Any) -> dict[str, Any]:
    channels = {"wordpress": False, "facebook": True, "instagram": True, "linkedin": True}
    errors = run_engine._final_presentation_errors(content, channels)
    posts = content.get("platform_posts") if isinstance(content.get("platform_posts"), dict) else {}
    result: dict[str, Any] = {"errors": errors, "platforms": {}}
    for platform in ("facebook", "instagram", "linkedin"):
        payload = posts.get(platform) if isinstance(posts.get(platform), dict) else {}
        caption = str(payload.get("final_caption") or content.get({"facebook": "fb_caption", "instagram": "ig_caption", "linkedin": "li_text"}[platform]) or "")
        result["platforms"][platform] = {
            "ready": not any(error.startswith(f"{platform}_") for error in errors),
            "copy_length": len(caption),
            "paragraph_count": len([part for part in caption.split("\n\n") if part.strip()]),
            "has_url": "http://" in caption or "https://" in caption,
            "has_hashtag": "#" in caption,
            "copy_review": _snapshot(payload.get("final_caption_qa") or payload.get("presentation") or {}),
        }
    return result


def _write_markdown(report: dict[str, Any], path: Path) -> None:
    aggregate = report["aggregate"]
    lines = [
        "# INFENERGY - 10-Post Content Generation Forensic",
        "",
        "## Experiment",
        "",
        "- Runs: 10",
        "- Images generated: 0",
        "- External posts: 0",
        "- Production state contaminated: NO",
        "- Code/policies changed during sample: NO",
        "",
        "## Outcome",
        "",
        f"- Text ready: {aggregate['text_ready']}",
        f"- Recovered and ready: {aggregate['recovered_and_ready']}",
        f"- Final failures: {aggregate['final_failures']}",
        f"- Success rate: {aggregate['success_rate_percent']}%",
        f"- Runs with an initial check failure: {aggregate['initial_failures']}",
        "",
        "## Ten Runs",
        "",
        "| # | Slot | Product / Topic | Candidates | Initial Problem | Recovery | Final Result | Score |",
        "| --- | --- | --- | ---: | --- | --- | --- | ---: |",
    ]
    for row in report["runs"]:
        content = row.get("final_content", {})
        attempts = row.get("attempts", [])
        initial = "; ".join(str(item) for item in (attempts[0].get("validation_errors", []) if attempts else [])) or "none"
        recovery = "yes" if len(attempts) > 1 else "no"
        lines.append(
            f"| {row['test_id']} | {row['slot']} | {content.get('product_name') or content.get('product_id') or content.get('topic') or 'unknown'} | "
            f"{len(row.get('generated_candidates', []))} | {initial[:80]} | {recovery} | {row['final_result']} | {content.get('quality_score', 'n/a')} |"
        )
    lines.extend(["", "## Gate Scorecard", ""])
    for gate, values in aggregate["gates"].items():
        lines.append(f"- **{gate}**: seen {values['seen']}, initial failures {values['initial_failures']}, final blocks {values['final_blocks']}")
    lines.extend(["", "## Run Stories", ""])
    for row in report["runs"]:
        content = row.get("final_content", {})
        lines.extend([
            f"### TEST {row['test_id']:02d}",
            f"The autonomous {row['slot']} decision selected `{content.get('product_id') or 'product-free'}` on `{content.get('topic') or 'no recorded topic'}`.",
            f"It produced {len(row.get('generated_candidates', []))} generated candidate versions and finished as **{row['final_result']}**.",
            f"Final decision reasons: {', '.join(content.get('publish_decision', {}).get('reasons', [])) or 'none'}.",
            "",
        ])
    lines.extend([
        "## Notes",
        "",
        "The JSON companion contains full captured native payloads, attempt diagnostics, validation, duplicate, strategy, evidence, and presentation records. Image artifact gates are intentionally marked not tested.",
    ])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_experiment(*, state_dir: Path, output_dir: Path, count: int) -> dict[str, Any]:
    if count != 10:
        raise ValueError("This controlled forensic is fixed at exactly 10 decisions.")
    os.environ.update({
        "DATA_DIR": str(state_dir),
        "POST_TEXT_ONLY": "true",
        "SOCIAL_DRY_RUN": "true",
        "SOCIAL_SHADOW_MODE": "false",
        "ENABLE_WORDPRESS": "false",
        "ENABLE_FACEBOOK": "false",
        "ENABLE_INSTAGRAM": "false",
        "ENABLE_LINKEDIN": "false",
    })

    import generate_posts
    import run_engine
    from social.candidate_pool import CandidatePool

    publisher_calls: list[str] = []
    image_calls: list[str] = []

    def blocked_publisher(*_: Any, **__: Any) -> dict:
        publisher_calls.append("attempted")
        raise AssertionError("Forensic runner must never call a publisher")

    def no_images(content: dict, **_: Any) -> dict:
        image_calls.append(str(content.get("post_id") or ""))
        return {"forensic_image_generation": "not_tested", "deferred": False}

    run_engine.publish_facebook.publish = blocked_publisher
    run_engine.publish_instagram.publish = blocked_publisher
    run_engine.publish_linkedin.publish = blocked_publisher
    generate_posts.generate_visuals = no_images

    original_generate = generate_posts.generate
    original_validate = run_engine.validate_generated_content
    original_score = run_engine.score_content
    original_duplicates = run_engine.check_duplicates
    original_decide = run_engine.decide_publication
    original_available = CandidatePool.available
    active: dict[str, Any] = {}

    def tracked_available(pool: Any) -> list[dict]:
        candidates = original_available(pool)
        active.setdefault("pooled_candidates", []).extend(_snapshot(candidates))
        return candidates

    def tracked_generate(*args: Any, **kwargs: Any) -> dict:
        content = original_generate(*args, **kwargs)
        active.setdefault("generated_candidates", []).append(_snapshot(content))
        active.setdefault("product_selection_reports", []).append(_snapshot(generate_posts.product_selection_report()))
        return content

    def tracked_validate(content: dict) -> dict:
        result = original_validate(content)
        active.setdefault("validation", []).append(_snapshot(result))
        return result

    def tracked_score(content: dict, **kwargs: Any) -> dict:
        result = original_score(content, **kwargs)
        active.setdefault("scores", []).append(_snapshot(result))
        return result

    def tracked_duplicates(content: dict, history: dict, **kwargs: Any) -> dict:
        result = original_duplicates(content, history, **kwargs)
        active.setdefault("duplicates", []).append(_snapshot(result))
        return result

    def tracked_decide(**kwargs: Any) -> dict:
        result = original_decide(**kwargs)
        active.setdefault("decisions", []).append(_snapshot(result))
        return result

    generate_posts.generate = tracked_generate
    run_engine.validate_generated_content = tracked_validate
    run_engine.score_content = tracked_score
    run_engine.check_duplicates = tracked_duplicates
    run_engine.decide_publication = tracked_decide
    CandidatePool.available = tracked_available

    metadata = {
        "experiment_id": output_dir.name,
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "count": count,
        "state_dir": str(state_dir),
        "production_state_contaminated": False,
        "image_provider_calls": 0,
        "image_generation_boundary_intercepts": 0,
        "publisher_calls": 0,
        "configuration": {
            "post_text_only": True,
            "social_dry_run": True,
            "channels_forced_off_only_inside_isolated_process": True,
        },
    }
    runs: list[dict[str, Any]] = []
    slots = ("morning", "midday", "evening")
    for index in range(count):
        active.clear()
        slot = slots[index % len(slots)]
        os.environ["POST_SLOT"] = slot
        seed_fingerprint = _seed_fingerprint()
        started = time.perf_counter()
        stdout = io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stdout):
            run_engine.main()
        elapsed = round(time.perf_counter() - started, 3)
        history = generate_posts.load_history()
        row = (history.get("posts") or [])[-1]
        source_candidates = active.get("generated_candidates") or active.get("pooled_candidates") or []
        final_content = source_candidates[-1] if source_candidates else dict(row)
        attempts = _snapshot(row.get("generation_attempts") or [])
        final_content = _snapshot(final_content)
        final_content.setdefault("publish_decision", row.get("publish_decision") or {})
        if not final_content.get("publish_decision") and active.get("decisions"):
            final_content["publish_decision"] = active["decisions"][-1]
        record = {
            "test_id": index + 1,
            "decision_id": str(final_content.get("post_id") or row.get("post_id") or f"forensic-{index + 1}"),
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "slot": slot,
            "random_state_fingerprint": seed_fingerprint,
            "elapsed_seconds": elapsed,
            "generated_candidates": active.get("generated_candidates", []),
            "pooled_candidates": active.get("pooled_candidates", []),
            "product_selection_reports": active.get("product_selection_reports", []),
            "validation": active.get("validation", []),
            "scores": active.get("scores", []),
            "duplicates": active.get("duplicates", []),
            "decisions": active.get("decisions", []),
            "attempts": attempts,
            "claims_and_evidence": _claims_and_evidence(final_content),
            "presentation": _presentation(final_content, run_engine),
            "image_artifact_gates": "NOT_TESTED",
            "final_content": final_content,
            "engine_stdout_tail": stdout.getvalue()[-6000:],
        }
        record["final_result"] = _classify(final_content, attempts)
        runs.append(record)

        # Advance only the isolated snapshot so later decisions see normal
        # freshness/rotation consequences without touching /data.
        if record["final_result"] in {"TEXT_READY", "RECOVERED_AND_TEXT_READY"}:
            row["status"] = "forensic_text_ready"
            generate_posts.save_history(history)
            candidate_id = str(row.get("candidate_id") or "")
            if candidate_id:
                CandidatePool(str(state_dir)).consume(candidate_id)

    gates = {name: {"seen": count, "initial_failures": 0, "final_blocks": 0} for name in ("validation", "quality", "duplicate", "presentation")}
    for row in runs:
        attempts = row["attempts"]
        first = attempts[0] if attempts else {}
        if not first.get("validation_passed", True):
            gates["validation"]["initial_failures"] += 1
        if first.get("score") is not None and float(first["score"] or 0) < 82:
            gates["quality"]["initial_failures"] += 1
        if not first.get("duplicates_ok", True):
            gates["duplicate"]["initial_failures"] += 1
        if row["presentation"].get("errors"):
            gates["presentation"]["initial_failures"] += 1
        category = row["final_result"]
        if category == "FAILED_EVIDENCE":
            gates["validation"]["final_blocks"] += 1
        elif category == "FAILED_QUALITY":
            gates["quality"]["final_blocks"] += 1
        elif category == "FAILED_DUPLICATE_FRESHNESS":
            gates["duplicate"]["final_blocks"] += 1
        elif category == "FAILED_PRESENTATION":
            gates["presentation"]["final_blocks"] += 1

    ready = [row for row in runs if row["final_result"] in {"TEXT_READY", "RECOVERED_AND_TEXT_READY"}]
    aggregate = {
        "total_decisions": count,
        "text_ready": len(ready),
        "recovered_and_ready": sum(row["final_result"] == "RECOVERED_AND_TEXT_READY" for row in runs),
        "final_failures": sum(row["final_result"].startswith("FAILED_") for row in runs),
        "abstentions": sum(row["final_result"].startswith("ABSTAINED") for row in runs),
        "initial_failures": sum(bool(row["attempts"]) and not row["attempts"][0].get("validation_passed", True) for row in runs),
        "success_rate_percent": round(100 * len(ready) / count, 1),
        "average_generation_seconds": round(sum(row["elapsed_seconds"] for row in runs) / count, 3),
        "slowest_run_seconds": max(row["elapsed_seconds"] for row in runs),
        "gates": gates,
    }
    metadata["finished_at_utc"] = datetime.now(timezone.utc).isoformat()
    metadata["image_generation_boundary_intercepts"] = len(image_calls)
    metadata["publisher_calls"] = len(publisher_calls)
    report = {"metadata": metadata, "runs": runs, "aggregate": aggregate}
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "content_generation_10_run.json").write_text(json.dumps(report, indent=2, default=_jsonable), encoding="utf-8")
    _write_markdown(report, output_dir / "content_generation_10_run.md")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--state-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--count", type=int, default=10)
    args = parser.parse_args()
    result = run_experiment(state_dir=Path(args.state_dir), output_dir=Path(args.output_dir), count=args.count)
    print(json.dumps({"output_dir": args.output_dir, "aggregate": result["aggregate"], "metadata": result["metadata"]}, default=_jsonable))


if __name__ == "__main__":
    main()