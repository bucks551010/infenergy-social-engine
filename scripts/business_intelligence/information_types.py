"""Information-type classification (Master Build §6).

Every extracted intelligence value is tagged with one of these types so
downstream engines never confuse a marketing adjective with a verified
fact.
"""

from __future__ import annotations

from typing import Final


# Frozen tuple so it can be treated as an enum without importing Enum.
INFORMATION_TYPES: Final[tuple[str, ...]] = (
    "OWNER_ASSERTION",
    "VERIFIED_FACT",
    "CATALOG_FACT",
    "DOCUMENTED_CLAIM",
    "EXTERNAL_RESEARCH",
    "REASONABLE_INFERENCE",
    "STRATEGIC_INFERENCE",
    "HYPOTHESIS",
    "PERFORMANCE_LEARNING",
    "OPERATOR_CONTEXT",
    "UNKNOWN",
    "CONFLICTED",
    "PROHIBITED",
)


# Rough authority weights (higher = trust more when composing profile).
AUTHORITY_WEIGHT: Final[dict[str, float]] = {
    "OWNER_ASSERTION": 1.0,
    "VERIFIED_FACT": 0.95,
    "CATALOG_FACT": 0.9,
    "DOCUMENTED_CLAIM": 0.75,
    "EXTERNAL_RESEARCH": 0.7,
    "PERFORMANCE_LEARNING": 0.65,
    "REASONABLE_INFERENCE": 0.55,
    "STRATEGIC_INFERENCE": 0.5,
    "HYPOTHESIS": 0.35,
    "OPERATOR_CONTEXT": 0.4,
    "UNKNOWN": 0.0,
    "CONFLICTED": 0.0,
    "PROHIBITED": 0.0,
}


def is_publishable_as_fact(info_type: str) -> bool:
    """Only OWNER-ASSERTED / VERIFIED / CATALOG-verified content can be
    presented as a fact in downstream copy without further verification.
    """
    return info_type in {"OWNER_ASSERTION", "VERIFIED_FACT", "CATALOG_FACT"}


def confidence_from_type(info_type: str) -> float:
    return float(AUTHORITY_WEIGHT.get(info_type, 0.0))
