"""Dispatcher for additive agents.

Provides a single entry point `run_agent(name, data_dir, params)` used by
`worker.py` to serve `/agents/run?name=<agent>&token=...&<param>=<value>`
requests and by tests to invoke agents uniformly.
"""

from __future__ import annotations

from typing import Any, Callable

from . import (
    ab_variant_orchestrator,
    alt_text_accessibility,
    brand_voice_drift,
    candidate_pool,
    carousel_slide_writer,
    crisis_relevance,
    cross_post_recycler,
    engagement_ingestion,
    hashtag_intelligence,
    learning_ingestion,
    performance_reflection,
    posting_time_optimizer,
    product_intelligence,
    product_matcher,
    retention,
    topic_intelligence,
    visual_qa_reviewer,
)


_REGISTRY: dict[str, Callable[..., dict]] = {
    "engagement_ingestion": engagement_ingestion.run,
    "candidate_pool": candidate_pool.run,
    "performance_reflection": performance_reflection.run,
    "learning_ingestion": learning_ingestion.run,
    "topic_intelligence": topic_intelligence.run,
    "carousel_slide_writer": carousel_slide_writer.run,
    "visual_qa_reviewer": visual_qa_reviewer.run,
    "product_matcher": product_matcher.run,
    "brand_voice_drift": brand_voice_drift.run,
    "hashtag_intelligence": hashtag_intelligence.run,
    "alt_text_accessibility": alt_text_accessibility.run,
    "posting_time_optimizer": posting_time_optimizer.run,
    "product_intelligence": product_intelligence.run,
    "ab_variant_orchestrator": ab_variant_orchestrator.run,
    "crisis_relevance": crisis_relevance.run,
    "cross_post_recycler": cross_post_recycler.run,
    "retention": retention.run,
}


def available_agents() -> list[str]:
    return sorted(_REGISTRY.keys())


def _coerce(value: str) -> Any:
    low = value.strip().lower()
    if low in ("true", "false"):
        return low == "true"
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def run_agent(name: str, data_dir: str, params: dict | None = None) -> dict:
    fn = _REGISTRY.get(name)
    if not fn:
        return {"error": f"unknown_agent:{name}", "available": available_agents()}
    kwargs: dict[str, Any] = {}
    for key, values in (params or {}).items():
        if key in {"token", "ts", "name"}:
            continue
        if not values:
            continue
        raw = values[0] if isinstance(values, list) else values
        kwargs[key] = _coerce(str(raw))
    try:
        return fn(data_dir, **kwargs)
    except TypeError as e:
        return {"error": f"agent_argument_error:{name}", "detail": str(e)}
    except Exception as e:
        return {"error": f"agent_runtime_error:{name}", "detail": str(e)[:500]}
