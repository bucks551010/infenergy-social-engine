"""Evidence ledger + authority rules + conflict detection.

Master Build §6-§9, §65.

* Every extracted fact is stored in an append-only JSONL ledger
  (:func:`append`).
* The authority of a given field-value combination depends on the
  *domain* per §8 — brand voice, technical spec, and current market
  info have different source-priority rules.
* :func:`detect_conflict` compares an incoming record with existing
  evidence for the same ``(subject, field)`` and creates a
  ``ConflictRecord`` when they disagree.
"""

from __future__ import annotations

import json
import os
import uuid
from dataclasses import asdict
from typing import Any, Iterable

from . import paths
from .information_types import AUTHORITY_WEIGHT, INFORMATION_TYPES, confidence_from_type
from .schemas import ConflictRecord, EvidenceRecord, validate_evidence


# --- Ledger files --------------------------------------------------------


def ledger_path() -> str:
    return os.path.join(paths.evidence_dir(), "evidence_ledger.jsonl")


def conflicts_path() -> str:
    return os.path.join(paths.evidence_dir(), "conflicts.json")


# --- Authority rules (§8) ----------------------------------------------


# Higher score = stronger authority for a given (domain, information_type).
_DOMAIN_AUTHORITY: dict[str, dict[str, float]] = {
    "business_purpose": {
        "OWNER_ASSERTION": 1.0,
        "DOCUMENTED_CLAIM": 0.7,
        "OPERATOR_CONTEXT": 0.5,
        "STRATEGIC_INFERENCE": 0.4,
    },
    "product_specification": {
        "CATALOG_FACT": 1.0,
        "VERIFIED_FACT": 0.95,
        "DOCUMENTED_CLAIM": 0.6,
        "OWNER_ASSERTION": 0.55,
        "STRATEGIC_INFERENCE": 0.2,
    },
    "market_current": {
        "EXTERNAL_RESEARCH": 1.0,
        "OWNER_ASSERTION": 0.6,
        "PERFORMANCE_LEARNING": 0.6,
        "STRATEGIC_INFERENCE": 0.4,
    },
    "brand_voice": {
        "OWNER_ASSERTION": 1.0,
        "DOCUMENTED_CLAIM": 0.85,
        "STRATEGIC_INFERENCE": 0.35,
    },
    "customer_response": {
        "PERFORMANCE_LEARNING": 1.0,
        "EXTERNAL_RESEARCH": 0.65,
        "STRATEGIC_INFERENCE": 0.3,
    },
    "safety_or_health": {
        "VERIFIED_FACT": 1.0,
        "EXTERNAL_RESEARCH": 0.85,
        "CATALOG_FACT": 0.6,
        "OWNER_ASSERTION": 0.4,
    },
}


def domain_authority(domain: str, information_type: str) -> float:
    dom = _DOMAIN_AUTHORITY.get(domain)
    if dom and information_type in dom:
        return dom[information_type]
    return AUTHORITY_WEIGHT.get(information_type, 0.0)


# --- Public API --------------------------------------------------------


def make_record(
    *,
    subject: str,
    field: str,
    value: Any,
    information_type: str,
    source_id: str,
    source_location: str = "",
    domain: str = "",
    risk_level: str = "LOW",
    freshness_required: bool = False,
    observed_at: str = "",
    verified_at: str = "",
    expires_at: str | None = None,
    notes: str = "",
) -> EvidenceRecord:
    if information_type not in INFORMATION_TYPES:
        raise ValueError(f"unknown information_type {information_type!r}")
    conf = domain_authority(domain, information_type) if domain else confidence_from_type(information_type)
    rec = EvidenceRecord(
        evidence_id=uuid.uuid4().hex[:12],
        subject=subject,
        field=field,
        value=value,
        information_type=information_type,
        source_id=source_id,
        source_location=source_location,
        source_authority=(domain or "general"),
        confidence=conf,
        risk_level=risk_level,
        freshness_required=freshness_required,
        observed_at=observed_at,
        verified_at=verified_at,
        expires_at=expires_at,
        notes=notes,
    )
    validate_evidence(rec)
    return rec


def append(rec: EvidenceRecord) -> None:
    with open(ledger_path(), "a", encoding="utf-8") as fh:
        fh.write(json.dumps(asdict(rec), ensure_ascii=False) + "\n")


def append_many(records: Iterable[EvidenceRecord]) -> int:
    n = 0
    with open(ledger_path(), "a", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(asdict(rec), ensure_ascii=False) + "\n")
            n += 1
    return n


def read_all() -> list[EvidenceRecord]:
    p = ledger_path()
    if not os.path.isfile(p):
        return []
    out: list[EvidenceRecord] = []
    with open(p, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(EvidenceRecord(**json.loads(line)))
            except (json.JSONDecodeError, TypeError):
                continue
    return out


def by_subject(subject: str) -> list[EvidenceRecord]:
    return [r for r in read_all() if r.subject == subject]


def by_field(subject: str, field: str) -> list[EvidenceRecord]:
    return [r for r in read_all() if r.subject == subject and r.field == field]


def strongest_value(subject: str, field: str) -> EvidenceRecord | None:
    """Return the single evidence record with the highest confidence."""
    candidates = by_field(subject, field)
    if not candidates:
        return None
    return max(candidates, key=lambda r: r.confidence)


def reset_ledger() -> None:
    """Test helper — clears the ledger (leaves the directory alone)."""
    p = ledger_path()
    if os.path.isfile(p):
        os.remove(p)


# --- Conflicts (§9) ---------------------------------------------------


def load_conflicts() -> list[ConflictRecord]:
    p = conflicts_path()
    if not os.path.isfile(p):
        return []
    try:
        with open(p, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return []
    return [ConflictRecord(**c) for c in data.get("conflicts", [])]


def save_conflicts(conflicts: Iterable[ConflictRecord]) -> None:
    with open(conflicts_path(), "w", encoding="utf-8") as fh:
        json.dump({"conflicts": [asdict(c) for c in conflicts]}, fh, indent=2)


def _values_disagree(a: Any, b: Any) -> bool:
    if a is None or b is None:
        return False
    if isinstance(a, str) and isinstance(b, str):
        return a.strip().lower() != b.strip().lower()
    return a != b


def detect_and_record_conflict(new_rec: EvidenceRecord) -> ConflictRecord | None:
    existing = by_field(new_rec.subject, new_rec.field)
    disagreeing = [r for r in existing if _values_disagree(r.value, new_rec.value)]
    if not disagreeing:
        return None
    values = [{"value": r.value, "source": r.source_id, "information_type": r.information_type, "confidence": r.confidence}
              for r in disagreeing + [new_rec]]
    conflict = ConflictRecord(
        conflict_id=uuid.uuid4().hex[:12],
        subject=new_rec.subject,
        field=new_rec.field,
        values=values,
        status="requires_verification",
    )
    existing_conflicts = load_conflicts()
    existing_conflicts.append(conflict)
    save_conflicts(existing_conflicts)
    return conflict
