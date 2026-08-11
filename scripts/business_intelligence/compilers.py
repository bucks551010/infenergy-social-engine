"""Context compilers — the layer downstream systems consume.

Master Build §43-§46.

* :func:`compile_conversion_context` — feeds ``scripts/conversion/*``
* :func:`compile_creative_context` — feeds the social/creative
  orchestrator in ``scripts/social/*``
* :func:`compile_orchestrator_context` — the master routing view

All three cache under ``data/business_intelligence/compiled/`` so
downstream code can either use the cached JSON or recompile on demand.
"""

from __future__ import annotations

import json
import os
from typing import Any

from . import paths, profile as profile_mod


def _cache(name: str, payload: dict[str, Any]) -> None:
    p = os.path.join(paths.compiled_dir(), name)
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)


def _load_profile() -> dict[str, Any]:
    current = profile_mod.load_current()
    if current:
        return current
    return _asdict_profile(profile_mod.assemble())


def _asdict_profile(profile: Any) -> dict[str, Any]:
    from dataclasses import asdict
    return asdict(profile)


# --- Conversion context (§44) -----------------------------------------


def compile_conversion_context(*, segment_id: str = "", offering_id: str = "") -> dict[str, Any]:
    p = _load_profile()
    seg = _pick_segment(p, segment_id)
    off = _pick_offering(p, offering_id)
    payload = {
        "business_identity": p.get("identity", {}),
        "brand_promise": p.get("promise", {}),
        "positioning": p.get("positioning", {}),
        "voice": {
            "brand_personality": p.get("voice", {}).get("brand_personality"),
            "voice_principles": p.get("voice", {}).get("voice_principles", []),
            "preferred_phrases": p.get("voice", {}).get("preferred_phrases", []),
            "prohibited_phrases": p.get("voice", {}).get("prohibited_phrases", []),
            "cta_style": p.get("voice", {}).get("cta_style"),
            "claims_language": p.get("voice", {}).get("claims_language"),
        },
        "audience_segment": seg,
        "offering": off,
        "objections": (seg or {}).get("objections", []),
        "decision_criteria": (seg or {}).get("decision_criteria", []),
        "trust_requirements": (seg or {}).get("trust_requirements", []),
        "forbidden_claims": (off or {}).get("forbidden_claims", []),
        "verified_facts": (off or {}).get("verified_facts", []),
        "brand_prohibitions": p.get("voice", {}).get("prohibited_phrases", []),
    }
    _cache("conversion_context.json", payload)
    return payload


# --- Creative context (§45) -------------------------------------------


def compile_creative_context(*, territory_id: str = "", segment_id: str = "") -> dict[str, Any]:
    p = _load_profile()
    territories = p.get("content_territories", [])
    territory = next((t for t in territories if t.get("territory_id") == territory_id), None) if territory_id else None
    seg = _pick_segment(p, segment_id)
    payload = {
        "business_identity": p.get("identity", {}),
        "why": p.get("why", {}),
        "worldview": p.get("worldview", {}),
        "positioning": p.get("positioning", {}),
        "reputation": p.get("reputation", {}),
        "voice": p.get("voice", {}),
        "visual": p.get("visual", {}),
        "posture": p.get("posture", {}),
        "social_mandate": p.get("social_mandate", {}),
        "content_territories": territories,
        "focus_territory": territory,
        "audience_segment": seg,
        "customer_moments": p.get("customer_moments", []),
        "transformations": p.get("transformations", []),
        "brand_prohibitions": {
            "voice": p.get("voice", {}).get("prohibited_phrases", []),
            "visual": p.get("visual", {}).get("prohibited_visual_patterns", []),
        },
        "learning_state": p.get("learning_state", {}),
    }
    _cache("creative_context.json", payload)
    return payload


# --- Orchestrator context (§46) --------------------------------------


def compile_orchestrator_context() -> dict[str, Any]:
    p = _load_profile()
    payload = {
        "business_identity": p.get("identity", {}),
        "social_mandate": p.get("social_mandate", {}),
        "content_territories": p.get("content_territories", []),
        "audience_segments": [{"segment_id": s.get("segment_id"), "name": s.get("name"), "confidence": s.get("confidence", 0.5)} for s in p.get("audience_segments", [])],
        "offerings_summary": {
            "total": len(p.get("offerings", [])),
            "categories": sorted({o.get("category", "") for o in p.get("offerings", []) if o.get("category")}),
        },
        "current_priorities": p.get("current_priorities", {}),
        "learning_state": p.get("learning_state", {}),
        "research_policy": p.get("research_policy", {}),
        "open_gaps": p.get("knowledge_gaps", []),
    }
    _cache("orchestrator_context.json", payload)
    return payload


# --- Helpers ---------------------------------------------------------


def _pick_segment(p: dict[str, Any], segment_id: str) -> dict[str, Any] | None:
    segments = p.get("audience_segments", [])
    if segment_id:
        for s in segments:
            if s.get("segment_id") == segment_id:
                return s
    return segments[0] if segments else None


def _pick_offering(p: dict[str, Any], offering_id: str) -> dict[str, Any] | None:
    offerings = p.get("offerings", [])
    if offering_id:
        for o in offerings:
            if o.get("offering_id") == offering_id or o.get("sku") == offering_id:
                return o
    return offerings[0] if offerings else None
