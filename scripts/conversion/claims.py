"""Claim integrity engine — Spec Section 25.

Classifies claims into 5 tiers. Complements the existing product-truth
validator in scripts/validate_product_claims.py by tagging language
patterns before the hard-fact validator runs.
"""

from __future__ import annotations

import re

CLAIM_TIERS = ("verified", "supported", "reasonable_inference", "unsupported", "prohibited")

# Language that is definitionally prohibited without explicit legal / regulatory backing.
PROHIBITED_PATTERNS = [
    r"\bcures?\b",
    r"\bFDA\s*approved\b",
    r"\bmedical(ly)?\s*(guaranteed|certified)\b",
    r"\blifetime\s*(free|guarantee)\b",
]

# Strong claims that need explicit spec/warranty backing to be "supported".
STRONG_CLAIM_PATTERNS = [
    r"\bguarantee(d|s)?\b",
    r"\b100\s*%\b",
    r"\bzero\s*risk\b",
    r"\binstant(ly)?\b",
    r"\bunlimited\b",
    r"\bfastest\b",
    r"\bbest\s*in\s*class\b",
    r"\bnever\s*fails?\b",
]

# Softer claims that are typically inferences from spec, safe with cautious language.
INFERENCE_PATTERNS = [
    r"\bhelps?\b",
    r"\bcan\b",
    r"\bmay\b",
    r"\btypically\b",
    r"\bdesigned\s*to\b",
    r"\bbuilt\s*for\b",
]


def classify_text(
    text: str,
    verified_facts: list[str] | None = None,
    warranty_available: bool = False,
) -> dict[str, list[str]]:
    """Scan text and bucket found phrases by tier."""
    result: dict[str, list[str]] = {t: [] for t in CLAIM_TIERS}
    if not text:
        return result

    for pat in PROHIBITED_PATTERNS:
        for m in re.finditer(pat, text, re.IGNORECASE):
            result["prohibited"].append(m.group(0))

    for pat in STRONG_CLAIM_PATTERNS:
        for m in re.finditer(pat, text, re.IGNORECASE):
            phrase = m.group(0)
            if warranty_available and re.search(r"warranty|guarantee", phrase, re.IGNORECASE):
                result["supported"].append(phrase)
            else:
                result["unsupported"].append(phrase)

    for pat in INFERENCE_PATTERNS:
        for m in re.finditer(pat, text, re.IGNORECASE):
            result["reasonable_inference"].append(m.group(0))

    for fact in (verified_facts or []):
        if fact and fact.lower() in text.lower():
            result["verified"].append(fact)

    return result


def worst_tier(scan: dict[str, list[str]]) -> str:
    """Return the worst (most dangerous) tier found; 'verified' if clean."""
    for tier in ("prohibited", "unsupported", "reasonable_inference", "supported", "verified"):
        if scan.get(tier):
            return tier
    return "verified"


def is_publishable(scan: dict[str, list[str]]) -> tuple[bool, list[str]]:
    """Publishing rules per §25.

    - prohibited: never publish
    - unsupported: never publish, must rewrite
    - reasonable_inference / supported / verified: publish
    """
    reasons = []
    if scan.get("prohibited"):
        reasons.append(f"prohibited_claim:{scan['prohibited'][0]}")
    if scan.get("unsupported"):
        reasons.append(f"unsupported_claim:{scan['unsupported'][0]}")
    return (not reasons, reasons)
