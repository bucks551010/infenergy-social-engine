"""Cross-agent interoperability and data-sufficiency conference."""

from __future__ import annotations

import glob
import json
import os
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from . import paths


@dataclass(frozen=True)
class AgentSpec:
    name: str
    team: str
    role: str
    provides: tuple[str, ...]
    requires: tuple[str, ...]
    optional: tuple[str, ...] = ()


_OPERATIONAL: tuple[AgentSpec, ...] = (
    AgentSpec("conversion_strategist", "operational", "Plans funnel-stage conversion strategy", ("conversion_brief", "audience_direction", "cta_direction"), ("business_profile", "product_catalog", "audience_model"), ("performance_history",)),
    AgentSpec("candidate_pool", "operational", "Builds and maintains pre-validated publishing candidates", ("candidate_pool", "candidate_availability"), ("creative_context", "product_catalog", "post_history")),
    AgentSpec("content_forensic", "operational", "Audits generation decisions and identifies blocking gates", ("generation_forensics", "gate_failure_analysis"), ("post_history", "creative_context")),
    AgentSpec("engagement_ingestion", "operational", "Imports channel engagement metrics", ("engagement_metrics",), ("post_history", "published_platform_ids"), ("meta_credentials",)),
    AgentSpec("performance_reflection", "operational", "Finds winning and losing creative patterns", ("performance_patterns",), ("post_history", "engagement_metrics")),
    AgentSpec("learning_ingestion", "operational", "Turns outcomes into reusable learning signals", ("learning_signals",), ("post_history", "engagement_metrics")),
    AgentSpec("topic_intelligence", "operational", "Maintains timely topic opportunities", ("topic_opportunities",), ("topic_queue", "content_territories"), ("external_research_access",)),
    AgentSpec("carousel_slide_writer", "operational", "Expands approved narratives into carousel slides", ("carousel_copy",), ("creative_context", "audience_model")),
    AgentSpec("visual_qa_reviewer", "operational", "Checks visual quality and brand compliance", ("visual_qa",), ("visual_dna",), ("generated_visuals",)),
    AgentSpec("product_matcher", "operational", "Matches content opportunities to catalog products", ("product_match",), ("product_catalog", "product_briefs", "audience_model")),
    AgentSpec("brand_voice_drift", "operational", "Detects copy that drifts from voice DNA", ("voice_drift_review",), ("voice_dna", "post_history")),
    AgentSpec("hashtag_intelligence", "operational", "Builds relevant hashtag sets", ("hashtag_sets",), ("content_territories", "post_history"), ("performance_patterns",)),
    AgentSpec("alt_text_accessibility", "operational", "Produces accessible image descriptions", ("alt_text",), ("visual_context",)),
    AgentSpec("posting_time_optimizer", "operational", "Recommends channel timing", ("posting_schedule",), ("post_history",), ("engagement_metrics",)),
    AgentSpec("product_intelligence", "operational", "Normalizes product truth and claim boundaries", ("product_briefs", "verified_product_facts", "forbidden_claims"), ("product_catalog",)),
    AgentSpec("ab_variant_orchestrator", "operational", "Plans controlled creative variants", ("experiment_variants",), ("creative_context",), ("performance_patterns",)),
    AgentSpec("crisis_relevance", "operational", "Checks crisis and event relevance", ("crisis_relevance_review",), ("topic_opportunities",), ("external_research_access",)),
    AgentSpec("cross_post_recycler", "operational", "Adapts proven posts without repetition", ("recycled_candidates",), ("post_history", "creative_context"), ("performance_patterns",)),
    AgentSpec("retention", "operational", "Maintains history and retention policy", ("retained_memory",), ()),
)


_MARKETING: tuple[AgentSpec, ...] = (
    AgentSpec("research_agent", "marketing", "Synthesizes market position and competitive edges", ("market_research",), ("business_profile", "product_catalog"), ("external_research_access",)),
    AgentSpec("audience_agent", "marketing", "Builds audience priorities and triggers", ("audience_model",), ("business_profile", "market_research")),
    AgentSpec("voice_agent", "marketing", "Defines brand voice rules", ("voice_dna",), ("business_profile", "founder_manifesto")),
    AgentSpec("offer_agent", "marketing", "Connects audience needs to offers", ("offer_strategy",), ("product_catalog", "audience_model")),
    AgentSpec("copy_agent", "marketing", "Creates core messages, hooks, and CTAs", ("core_copy",), ("voice_dna", "offer_strategy", "audience_model")),
    AgentSpec("creative_agent", "marketing", "Creates visual concepts and prompts", ("visual_context",), ("visual_dna", "core_copy")),
    AgentSpec("channel_ops_agent", "marketing", "Adapts strategy by channel", ("channel_plan",), ("core_copy", "visual_context")),
    AgentSpec("seo_agent", "marketing", "Builds search themes and clusters", ("seo_strategy",), ("product_catalog", "core_copy")),
    AgentSpec("lifecycle_email_agent", "marketing", "Builds lifecycle email journeys", ("lifecycle_strategy",), ("core_copy", "audience_model")),
    AgentSpec("experimentation_agent", "marketing", "Defines measurable growth experiments", ("experiment_plan",), ("core_copy", "channel_plan"), ("performance_patterns",)),
    AgentSpec("qa_agent", "marketing", "Validates the complete marketing strategy", ("marketing_qa",), ("market_research", "audience_model", "voice_dna", "offer_strategy", "core_copy", "visual_context", "channel_plan")),
)


def roster() -> list[AgentSpec]:
    return list(_OPERATIONAL + _MARKETING)


def _json_count(path: str, candidate_keys: tuple[str, ...]) -> int:
    if not os.path.isfile(path):
        return 0
    try:
        with open(path, "r", encoding="utf-8") as fh:
            value = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return 0
    if isinstance(value, list):
        return len(value)
    if isinstance(value, dict):
        for key in candidate_keys:
            child = value.get(key)
            if isinstance(child, (list, dict)):
                return len(child)
        return len(value)
    return 0


def _history_has_engagement(path: str) -> bool:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            posts = json.load(fh).get("posts", [])
    except (OSError, json.JSONDecodeError, AttributeError):
        return False
    for post in posts:
        metrics = post.get("engagement_metrics", {}) if isinstance(post, dict) else {}
        if not isinstance(metrics, dict):
            continue
        for platform in ("facebook", "instagram", "linkedin"):
            values = metrics.get(platform, {})
            if isinstance(values, dict) and any(isinstance(value, (int, float)) for value in values.values()):
                return True
    return False


def _history_has_platform_ids(path: str) -> bool:
    try:
        with open(path, "r", encoding="utf-8") as fh:
            posts = json.load(fh).get("posts", [])
    except (OSError, json.JSONDecodeError, AttributeError):
        return False
    invalid = {"", "skipped", "dry-run"}
    return any(
        str(post.get(key, "")).strip() not in invalid
        for post in posts if isinstance(post, dict)
        for key in ("fb_id", "ig_id", "li_id")
    )


def _inventory_product_count() -> int:
    db_path = paths.inventory_db_path()
    if not os.path.isfile(db_path):
        return 0
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        count = int(conn.execute("SELECT COUNT(*) FROM products").fetchone()[0])
        conn.close()
        return count
    except (sqlite3.Error, TypeError, ValueError):
        return 0


def inspect_data() -> dict[str, dict[str, Any]]:
    data = paths.data_dir()
    bi_profile = os.path.join(paths.profile_dir(), "current_profile.json")
    product_csvs = glob.glob(os.path.join(paths.products_csv_dir(), "*.csv"))
    briefs = glob.glob(os.path.join(paths.product_briefs_dir(), "*.json"))
    marketing_outputs = glob.glob(os.path.join(paths.marketing_dir(), "marketing_strategy_*.json"))
    social_files = glob.glob(os.path.join(data, "social", "*.json"))
    visuals = glob.glob(os.path.join(data, "generated_visuals", "**", "*.*"), recursive=True)
    post_count = _json_count(paths.post_history_path(), ("posts", "history"))
    topic_count = _json_count(os.path.join(data, "topic_queue.json"), ("topics", "queue"))
    profile_data: dict[str, Any] = {}
    if os.path.isfile(bi_profile):
        try:
            with open(bi_profile, "r", encoding="utf-8") as fh:
                profile_data = json.load(fh)
        except (OSError, json.JSONDecodeError):
            profile_data = {}
    offering_count = len(profile_data.get("offerings", []))
    audience_count = len(profile_data.get("audience_segments", []))
    territory_count = len(profile_data.get("content_territories", []))
    checks = {
        "business_profile": (bool(profile_data), f"profile={'present' if profile_data else 'missing'}"),
        "founder_manifesto": (os.path.isfile(paths.founder_manifesto_path()), paths.founder_manifesto_path()),
        "product_catalog": (bool(product_csvs) or _inventory_product_count() > 0 or offering_count > 0, f"csvs={len(product_csvs)}, inventory_products={_inventory_product_count()}, profile_offerings={offering_count}"),
        "product_briefs": (bool(briefs), f"briefs={len(briefs)}"),
        "audience_model": (audience_count > 0, f"segments={audience_count}"),
        "content_territories": (territory_count > 0, f"territories={territory_count}"),
        "creative_context": (bool(profile_data.get("voice")) and territory_count > 0, "voice + territories"),
        "voice_dna": (bool(profile_data.get("voice")), "profile.voice"),
        "visual_dna": (bool(profile_data.get("visual")), "profile.visual"),
        "post_history": (post_count > 0, f"records={post_count}"),
        "published_platform_ids": (_history_has_platform_ids(paths.post_history_path()), "post_history fb_id/ig_id/li_id"),
        "engagement_metrics": (_history_has_engagement(paths.post_history_path()), "post_history.engagement_metrics"),
        "topic_queue": (topic_count > 0, f"topics={topic_count}"),
        "generated_visuals": (bool(visuals), f"assets={len(visuals)}"),
        "marketing_outputs": (bool(marketing_outputs), f"strategies={len(marketing_outputs)}"),
        "social_libraries": (bool(social_files), f"libraries={len(social_files)}"),
        "meta_credentials": (bool(os.environ.get("META_PAGE_ACCESS_TOKEN")), "META_PAGE_ACCESS_TOKEN"),
        "external_research_access": (bool(os.environ.get("GEMINI_API_KEY")), "GEMINI_API_KEY"),
    }
    return {key: {"available": available, "detail": detail} for key, (available, detail) in checks.items()}


def _provider_map(specs: list[AgentSpec]) -> dict[str, list[str]]:
    providers: dict[str, list[str]] = {}
    for spec in specs:
        for capability in spec.provides:
            providers.setdefault(capability, []).append(spec.name)
    return providers


def run_conference(*, persist: bool = True) -> dict[str, Any]:
    specs = roster()
    data = inspect_data()
    providers = _provider_map(specs)
    assessments: list[dict[str, Any]] = []
    unresolved: set[str] = set()
    collaboration_edges: list[dict[str, str]] = []

    for spec in specs:
        missing_data = [key for key in spec.requires if not data.get(key, {}).get("available", False)]
        missing_optional = [key for key in spec.optional if not data.get(key, {}).get("available", False) and key not in providers]
        requests: list[dict[str, Any]] = []
        for need in missing_data:
            candidates = providers.get(need, [])
            if candidates:
                requests.append({"need": need, "request_from": candidates, "resolution": "agent_can_supply"})
                for candidate in candidates:
                    collaboration_edges.append({"from": spec.name, "to": candidate, "needs": need})
            else:
                requests.append({"need": need, "request_from": [], "resolution": "external_input_required"})
                unresolved.add(need)
        if not missing_data:
            status = "ready"
        elif all(providers.get(need) for need in missing_data):
            status = "ready_after_collaboration"
        else:
            status = "blocked"
        assessments.append({
            "agent": spec.name,
            "team": spec.team,
            "role": spec.role,
            "status": status,
            "provides": list(spec.provides),
            "required_data": {key: data.get(key, {"available": False, "detail": "unknown"}) for key in spec.requires},
            "optional_gaps": missing_optional,
            "cross_agent_requests": requests,
        })

    counts = {status: sum(1 for item in assessments if item["status"] == status) for status in ("ready", "ready_after_collaboration", "blocked")}
    generation_blockers = {"business_profile", "founder_manifesto", "product_catalog", "product_briefs", "audience_model", "content_territories", "creative_context", "voice_dna", "visual_dna", "topic_queue"}
    report = {
        "conference_version": "agent-conference.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "agents_present": len(specs),
            "teams_present": sorted({spec.team for spec in specs}),
            "can_work_together": counts["blocked"] == 0,
            "generation_ready": not bool(unresolved & generation_blockers),
            "learning_cycle_ready": data["engagement_metrics"]["available"],
            "status_counts": counts,
            "unresolved_external_inputs": sorted(unresolved),
        },
        "data_inventory": data,
        "agent_assessments": assessments,
        "collaboration_edges": collaboration_edges,
        "conference_decisions": _decisions(data, counts, unresolved),
    }
    if persist:
        _persist(report)
    return report


def _decisions(data: dict[str, dict[str, Any]], counts: dict[str, int], unresolved: set[str]) -> list[dict[str, str]]:
    decisions: list[dict[str, str]] = []
    if counts["blocked"] == 0:
        decisions.append({"priority": "P0", "decision": "All agents may collaborate through their declared capability contracts."})
    for key in sorted(unresolved):
        decisions.append({"priority": "P0", "decision": f"Supply missing external input: {key}."})
    if not data["meta_credentials"]["available"]:
        decisions.append({"priority": "P1", "decision": "Meta engagement ingestion remains local/offline until META_PAGE_ACCESS_TOKEN is configured."})
    if not data["external_research_access"]["available"]:
        decisions.append({"priority": "P1", "decision": "External research remains disabled; use repository evidence and owner assertions only."})
    if not data["generated_visuals"]["available"]:
        decisions.append({"priority": "P1", "decision": "Generate a visual sample set before relying on visual QA performance conclusions."})
    decisions.append({"priority": "P2", "decision": "Re-run this conference after material catalog, audience, performance, or credential changes."})
    return decisions


def _persist(report: dict[str, Any]) -> None:
    directory = os.path.join(paths.bi_dir(), "conference")
    os.makedirs(directory, exist_ok=True)
    with open(os.path.join(directory, "latest.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
