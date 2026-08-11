"""Public façade for the Business Intelligence Foundation (§60).

Downstream systems import from ``business_intelligence.api`` — never
from the internal modules directly.
"""

from __future__ import annotations

from typing import Any

from . import (
    bootstrap as bootstrap_mod,
    compilers,
    critic,
    evidence,
    learning,
    profile as profile_mod,
    research,
)


# --- Read-side ---------------------------------------------------------


def get_business_profile() -> dict[str, Any]:
    return profile_mod.load_current() or _asdict(profile_mod.assemble())


def get_business_identity() -> dict[str, Any]:
    return get_business_profile().get("identity", {})


def get_brand_context() -> dict[str, Any]:
    p = get_business_profile()
    return {
        "identity": p.get("identity", {}),
        "why": p.get("why", {}),
        "positioning": p.get("positioning", {}),
        "promise": p.get("promise", {}),
        "reputation": p.get("reputation", {}),
        "voice": p.get("voice", {}),
        "visual": p.get("visual", {}),
        "posture": p.get("posture", {}),
    }


def get_audience_segment(segment_id: str) -> dict[str, Any] | None:
    for s in get_business_profile().get("audience_segments", []):
        if s.get("segment_id") == segment_id:
            return s
    return None


def get_offering(offering_id: str) -> dict[str, Any] | None:
    for o in get_business_profile().get("offerings", []):
        if o.get("offering_id") == offering_id or o.get("sku") == offering_id:
            return o
    return None


# --- Compilation -------------------------------------------------------


def compile_conversion_context(*, segment_id: str = "", offering_id: str = "") -> dict[str, Any]:
    return compilers.compile_conversion_context(segment_id=segment_id, offering_id=offering_id)


def compile_creative_context(*, territory_id: str = "", segment_id: str = "") -> dict[str, Any]:
    return compilers.compile_creative_context(territory_id=territory_id, segment_id=segment_id)


def compile_orchestrator_context() -> dict[str, Any]:
    return compilers.compile_orchestrator_context()


# --- Write-side --------------------------------------------------------


def register_owner_assertion(*, subject: str, field: str, value: Any, reason: str = "", persistent: bool = True) -> dict[str, Any]:
    rec = evidence.make_record(
        subject=subject,
        field=field,
        value=value,
        information_type="OWNER_ASSERTION",
        source_id="owner",
        domain="business_purpose",
        notes=reason,
    )
    evidence.append(rec)
    ov = learning.register_override(
        subject=subject,
        field_path=f"{subject}.{field}" if not field.startswith(subject) else field,
        value=value,
        reason=reason,
        persistent=persistent,
    )
    from dataclasses import asdict
    return {"evidence_id": rec.evidence_id, "override_id": ov.override_id, "override": asdict(ov)}


def register_performance_learning(*, scope: str, subject: str, signal: str, weight: float = 1.0, source_post_id: str = "") -> dict[str, Any]:
    rec = learning.record_signal(
        scope=scope,
        subject=subject,
        signal=signal,
        weight=weight,
        source_post_id=source_post_id,
    )
    from dataclasses import asdict
    return asdict(rec)


def register_knowledge_gap(**kwargs: Any) -> dict[str, Any]:
    from dataclasses import asdict
    return asdict(research.register_gap(**kwargs))


def register_hypothesis(statement: str, *, domain: str, confidence: float = 0.3) -> dict[str, Any]:
    from dataclasses import asdict
    return asdict(research.register_hypothesis(statement, domain=domain, confidence=confidence))


# --- Bootstrap ---------------------------------------------------------


def rebuild_profile(*, reset_evidence: bool = False) -> dict[str, Any]:
    return bootstrap_mod.run(reset_evidence=reset_evidence)


def critic_review() -> dict[str, Any]:
    v = critic.review(get_business_profile())
    return {"passed": v.passed, "failures": v.failures, "warnings": v.warnings, "checks": v.checks}


# --- Helpers ---------------------------------------------------------


def _asdict(obj: Any) -> Any:
    from dataclasses import asdict
    try:
        return asdict(obj)
    except TypeError:
        return obj
