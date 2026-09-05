"""Dispatcher for additive agents.

Provides a single entry point `run_agent(name, data_dir, params)` used by
`worker.py` to serve `/agents/run?name=<agent>&token=...&<param>=<value>`
requests and by tests to invoke agents uniformly.
"""

from __future__ import annotations

import inspect
from typing import Any, Callable

from . import (
    ab_variant_orchestrator,
    alt_text_accessibility,
    brand_voice_drift,
    candidate_pool,
    content_forensic,
    carousel_slide_writer,
    crisis_relevance,
    cross_post_recycler,
    engagement_ingestion,
    hashtag_intelligence,
    learning_ingestion,
    on_image_text_author,
    on_image_typography_designer,
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
    "content_forensic": content_forensic.run,
    "performance_reflection": performance_reflection.run,
    "learning_ingestion": learning_ingestion.run,
    "on_image_text_author": on_image_text_author.run,
    "on_image_typography_designer": on_image_typography_designer.run,
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

_PARAMETER_ALIASES: dict[str, dict[str, str]] = {
    "carousel_slide_writer": {
        "archetype": "archetype_key",
        "audience_archetype": "archetype_key",
        "brief": "creative_brief",
        "idea": "creative_brief",
        "objective": "creative_brief",
        "product_data": "product",
        "slides": "slide_count",
    },
    "hashtag_intelligence": {
        "archetype": "archetype_key",
        "audience_archetype": "archetype_key",
        "product_data": "product",
    },
    "product_intelligence": {
        "audience": "audience_segment",
        "product_data": "product",
    },
    "product_matcher": {
        "archetype": "archetype_key",
        "audience_archetype": "archetype_key",
    },
    "visual_qa_reviewer": {"visual_direction": "direction"},
    "on_image_text_author": {"factual_brief": "brief"},
    "on_image_typography_designer": {"image": "image_path", "text": "headline"},
}


def available_agents() -> list[str]:
    return sorted(_REGISTRY.keys())


def agent_contracts() -> dict[str, dict[str, Any]]:
    contracts: dict[str, dict[str, Any]] = {}
    for name, fn in sorted(_REGISTRY.items()):
        signature = inspect.signature(fn)
        parameters = [
            parameter.name
            for parameter in signature.parameters.values()
            if parameter.name != "data_dir"
            and parameter.kind not in {inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD}
        ]
        contracts[name] = {
            "parameters": parameters,
            "aliases": dict(_PARAMETER_ALIASES.get(name, {})),
            "accepts_additional_parameters": any(
                parameter.kind == inspect.Parameter.VAR_KEYWORD
                for parameter in signature.parameters.values()
            ),
        }
    return contracts


def _coerce(value: Any) -> Any:
    if not isinstance(value, str):
        return value
    low = value.strip().lower()
    if low in ("true", "false"):
        return low == "true"
    try:
        if "." in value:
            return float(value)
        return int(value)
    except ValueError:
        return value


def _normalize_parameters(name: str, fn: Callable[..., dict], params: dict, query_params: bool) -> tuple[dict[str, Any], dict[str, Any] | None]:
    aliases = _PARAMETER_ALIASES.get(name, {})
    kwargs: dict[str, Any] = {}
    parameter_sources: dict[str, str] = {}
    for key, values in params.items():
        if key in {"token", "ts", "name"} or values is None or values == "" or values == []:
            continue
        normalized_key = aliases.get(key, key)
        if normalized_key in kwargs and parameter_sources[normalized_key] != key:
            return {}, {
                "error": f"agent_argument_error:{name}",
                "detail": f"conflicting_parameters:{parameter_sources[normalized_key]},{key}",
            }
        raw = values[0] if query_params and isinstance(values, list) else values
        kwargs[normalized_key] = _coerce(raw)
        parameter_sources[normalized_key] = key

    signature = inspect.signature(fn)
    accepts_additional = any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in signature.parameters.values()
    )
    accepted = {
        parameter.name
        for parameter in signature.parameters.values()
        if parameter.name != "data_dir"
        and parameter.kind not in {inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD}
    }
    unexpected = sorted(set(kwargs) - accepted) if not accepts_additional else []
    if unexpected:
        return {}, {
            "error": f"agent_argument_error:{name}",
            "detail": f"unexpected_parameters:{','.join(unexpected)}",
            "accepted_parameters": sorted(accepted),
            "aliases": dict(aliases),
        }
    return kwargs, None


def run_agent(
    name: str,
    data_dir: str,
    params: dict | None = None,
    *,
    query_params: bool = False,
) -> dict:
    fn = _REGISTRY.get(name)
    if not fn:
        return {"error": f"unknown_agent:{name}", "available": available_agents()}
    kwargs, validation_error = _normalize_parameters(name, fn, params or {}, query_params)
    if validation_error:
        return validation_error
    try:
        return fn(data_dir, **kwargs)
    except TypeError as e:
        return {"error": f"agent_argument_error:{name}", "detail": str(e)}
    except Exception as e:
        return {"error": f"agent_runtime_error:{name}", "detail": str(e)[:500]}
