"""Claim intelligence + risk-based verification (Master Build §16, §17, §50).

Extracts material factual claims from copy, classifies risk, and returns
verification requirements. Complements the existing
``scripts.conversion.claims`` module (which flags language patterns);
this module produces the structured claim ledger.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable


LOW_RISK = "LOW_RISK"
MEDIUM_RISK = "MEDIUM_RISK"
HIGH_RISK = "HIGH_RISK"


HIGH_RISK_DOMAINS = (
    "safety", "health", "electrical hazard", "battery safety",
    "financial savings", "legal", "regulatory", "environmental",
    "product performance", "statistic", "certification",
    "medical", "FDA", "guarantee",
)

MEDIUM_RISK_MARKERS = (
    "efficiency", "watt-hour", "runtime", "cycles", "capacity",
    "temperature range", "output", "input", "charge time",
)


# --- Claim record ------------------------------------------------------------


@dataclass
class Claim:
    claim_text: str
    claim_type: str
    confidence: float
    risk: str
    verification_required: bool
    source: str | None = None
    verification_status: str = "unverified"
    provenance: str = "UNVERIFIED_INFERENCE"
    rejection_reason: str | None = None
    source_concept_ids: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "claim": self.claim_text,
            "type": self.claim_type,
            "confidence": self.confidence,
            "risk": self.risk,
            "verification_required": self.verification_required,
            "source": self.source,
            "verification_status": self.verification_status,
            "provenance": self.provenance,
            "rejection_reason": self.rejection_reason,
            "source_concept_ids": list(self.source_concept_ids),
        }


# --- Extraction --------------------------------------------------------------


_STAT_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s?(%|hours?|watts?|watt-hours?|wh|w|amps?|amp-hours?|ah|mah|cycles?|degrees?|°[cf]|feet|inches|days?|years?)", re.IGNORECASE)
_DERIVATION_RE = re.compile(r"\b\d+(?:\.\d+)?\s*(?:x|\*|/|per)\s*\d+(?:\.\d+)?\b|\b0\.\d+\b", re.IGNORECASE)
_DERIVATION_CONTEXT = ("efficiency", "factor", "convert", "runtime", "estimate", "load", "coverage", "savings", "cost", "compare", "performance", "rate")


def remove_unsupported_numeric_claims(text: str, verified_facts: Iterable[str]) -> tuple[str, list[str]]:
    """Remove whole sentences with numeric claims absent from product evidence.

    Revision must never turn an unsupported measurement into a newly invented
    estimate. Returning the removed sentences lets the caller retain audit
    evidence while ensuring the revised candidate is evaluated on safe text.
    """
    verified_tokens = {
        f"{match.group(1).replace(',', '').lower()} {match.group(2).lower()}"
        for fact in verified_facts
        for match in _STAT_RE.finditer(str(fact or ""))
    }
    kept: list[str] = []
    removed: list[str] = []
    for sentence in re.split(r"(?<=[.!?])\s+", str(text or "").strip()):
        tokens = [
            f"{match.group(1).replace(',', '').lower()} {match.group(2).lower()}"
            for match in _STAT_RE.finditer(sentence)
        ]
        unsupported_derivation = bool(_DERIVATION_RE.search(sentence)) and any(
            marker in sentence.lower() for marker in _DERIVATION_CONTEXT
        )
        if (tokens and any(token not in verified_tokens for token in tokens)) or unsupported_derivation:
            removed.append(sentence)
        elif sentence:
            kept.append(sentence)
    return " ".join(kept), removed


def _classify_claim_type(text: str) -> str:
    low = text.lower()
    if any(d in low for d in ("safe", "safety", "hazard", "risk of", "danger")):
        return "safety_claim"
    if any(d in low for d in ("cures", "cure", "prevents", "treats", "medical", "fda")):
        return "health_claim"
    if any(d in low for d in ("waterproof", "shockproof", "military-grade", "certified", "certification")):
        return "certification_claim"
    if any(d in low for d in ("save", "savings", "cheaper", "$", "cost")):
        return "financial_claim"
    if any(d in low for d in ("compared to", "vs.", "vs ", "versus", "outperforms", "best in class", "fastest", "highest")):
        return "comparative_claim"
    if _STAT_RE.search(text):
        return "quantitative_technical_fact"
    if any(d in low for d in ("study", "research", "scientist")):
        return "research_claim"
    return "general_informational"


def _risk_for(claim_type: str, text: str) -> str:
    low = text.lower()
    if any(d in low for d in HIGH_RISK_DOMAINS):
        return HIGH_RISK
    if claim_type in {"safety_claim", "health_claim", "certification_claim", "research_claim"}:
        return HIGH_RISK
    if claim_type in {"quantitative_technical_fact", "financial_claim", "comparative_claim"}:
        return MEDIUM_RISK
    if any(m in low for m in MEDIUM_RISK_MARKERS):
        return MEDIUM_RISK
    return LOW_RISK


def _confidence_for(risk: str) -> float:
    return {LOW_RISK: 0.9, MEDIUM_RISK: 0.7, HIGH_RISK: 0.5}[risk]


def extract_claims(text: str) -> list[Claim]:
    """Extract material claims from a block of copy.

    A material claim is any sentence containing a stat, comparison, or
    domain marker. Purely tonal sentences ("we care about you") are not
    considered material.
    """
    if not text:
        return []
    sents = re.split(r"(?<=[.!?])\s+", text.strip())
    out: list[Claim] = []
    for s in sents:
        s = s.strip()
        if not s:
            continue
        low = s.lower()
        if (
            not _STAT_RE.search(s)
            and low.startswith(("start with", "then check", "check the", "use the", "compare the"))
        ):
            continue
        has_stat = bool(_STAT_RE.search(s))
        has_domain = any(d in low for d in HIGH_RISK_DOMAINS + MEDIUM_RISK_MARKERS)
        if not (has_stat or has_domain):
            continue
        ctype = _classify_claim_type(s)
        risk = _risk_for(ctype, s)
        out.append(
            Claim(
                claim_text=s,
                claim_type=ctype,
                confidence=_confidence_for(risk),
                risk=risk,
                verification_required=risk != LOW_RISK,
            )
        )
    return out


# --- Verification against verified_facts ------------------------------------


def _fact_matches(claim: Claim, verified_facts: Iterable[str]) -> bool:
    low = claim.claim_text.lower()
    for fact in verified_facts:
        if not fact:
            continue
        fl = str(fact).lower()
        tokens = [t for t in re.findall(r"\w+", fl) if len(t) > 3]
        if tokens and sum(1 for t in tokens if t in low) >= max(1, len(tokens) // 3):
            return True
    return False


def _numeric_tokens(text: str) -> set[str]:
    return {f"{match.group(1).replace(',', '').lower()} {match.group(2).lower()}" for match in _STAT_RE.finditer(text)}


def _claim_provenance(claim: Claim, verified_facts: Iterable[str]) -> tuple[str, str | None]:
    claim_numbers = _numeric_tokens(claim.claim_text)
    if _DERIVATION_RE.search(claim.claim_text) and any(marker in claim.claim_text.lower() for marker in _DERIVATION_CONTEXT):
        return "PROHIBITED_OR_UNSUPPORTED", "derived_claim_has_no_verified_formula"
    for fact in verified_facts:
        fact_numbers = _numeric_tokens(str(fact or ""))
        if claim_numbers and claim_numbers <= fact_numbers:
            return "VERIFIED_PRODUCT_FACT", None
    if claim_numbers:
        return "PROHIBITED_OR_UNSUPPORTED", "numeric_claim_not_present_in_verified_facts"
    if _fact_matches(claim, verified_facts):
        return "VERIFIED_PRODUCT_FACT", None
    return "UNVERIFIED_INFERENCE", "claim_not_supported_by_verified_facts"


@dataclass
class ClaimLedger:
    claims: list[Claim] = field(default_factory=list)
    unverified_high_risk: list[Claim] = field(default_factory=list)
    verified: list[Claim] = field(default_factory=list)
    unverified_medium: list[Claim] = field(default_factory=list)

    def summary(self) -> dict[str, Any]:
        return {
            "total": len(self.claims),
            "verified": len(self.verified),
            "unverified_high_risk": len(self.unverified_high_risk),
            "unverified_medium": len(self.unverified_medium),
            "publish_blocking": bool(self.unverified_high_risk),
        }

    def as_dict(self) -> dict[str, Any]:
        return {
            "claims": [c.as_dict() for c in self.claims],
            "summary": self.summary(),
        }


def build_ledger(
    text: str,
    *,
    verified_facts: Iterable[str] = (),
    forbidden_claims: Iterable[str] = (),
    source_concepts: dict[str, str] | None = None,
) -> ClaimLedger:
    ledger = ClaimLedger()
    for c in extract_claims(text):
        c.source_concept_ids = tuple(
            concept_id
            for source_text, concept_id in (source_concepts or {}).items()
            if source_text and (c.claim_text in source_text or source_text in c.claim_text)
        )
        provenance, rejection_reason = _claim_provenance(c, verified_facts)
        c.provenance = provenance
        c.rejection_reason = rejection_reason
        if provenance == "VERIFIED_PRODUCT_FACT":
            c.verification_status = "verified"
            c.source = "product_verified_facts"
            ledger.verified.append(c)
        else:
            if c.risk == HIGH_RISK:
                ledger.unverified_high_risk.append(c)
            elif c.risk == MEDIUM_RISK:
                ledger.unverified_medium.append(c)
        ledger.claims.append(c)
    low = text.lower()
    for fc in forbidden_claims:
        if not fc:
            continue
        if str(fc).lower() in low:
            forbidden = Claim(
                claim_text=str(fc),
                claim_type="forbidden",
                confidence=1.0,
                risk=HIGH_RISK,
                verification_required=True,
                source="brand_forbidden_claims",
                verification_status="forbidden",
                provenance="PROHIBITED_OR_UNSUPPORTED",
                rejection_reason="brand_forbidden_claim",
            )
            ledger.claims.append(forbidden)
            ledger.unverified_high_risk.append(forbidden)
    return ledger
