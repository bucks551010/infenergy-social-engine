"""End-to-end pipeline (Master Build §5).

DISCOVER → REGISTER → PARSE → NORMALIZE → EXTRACT → CLASSIFY →
PROVENANCE → CONFLICTS → ENTITIES → RELATIONSHIPS → GAPS →
SYNTHESIZE → CONFIDENCE → BUILD ALL MODELS → VALIDATE → VERSION →
PERSIST.

Safe to call multiple times — every side-effect writes to
``data/business_intelligence/``. All state can be regenerated from the
Infenergy source data plus any owner overrides.
"""

from __future__ import annotations

from typing import Any

from . import (
    critic,
    evidence,
    offerings as offering_mod,
    profile as profile_mod,
    research,
    sources,
)


def run(*, reset_evidence: bool = False) -> dict[str, Any]:
    """Full pipeline. Returns a summary dict for the caller."""
    if reset_evidence:
        evidence.reset_ledger()

    # 1. DISCOVER + REGISTER
    discovered = sources.discover_all()

    # 2. OFFERINGS (parse + normalize + graph + evidence)
    offering_list = offering_mod.build_from_csv()
    snapshot = offering_mod.catalog_snapshot(offering_list)
    edges = offering_mod.build_graph(offering_list)
    offering_mod.save(offering_list, edges, snapshot)
    evidence_count = offering_mod.emit_evidence(offering_list)

    # 3. RESEARCH seed
    research.save_policy(research.load_policy())
    research.seed_default_gaps()
    research.seed_default_hypotheses()

    # 4. ASSEMBLE profile
    profile = profile_mod.assemble()

    # 5. CRITIC review
    profile_dict = _asdict(profile)
    verdict = critic.review(profile_dict)

    # 6. PERSIST profile + version
    version = profile_mod.save_current(profile, change_reason="bootstrap")

    return {
        "sources_discovered": len(discovered),
        "offerings": len(offering_list),
        "offering_edges": len(edges),
        "evidence_records": evidence_count,
        "profile_version": version.profile_version,
        "verdict": {
            "passed": verdict.passed,
            "failures": verdict.failures,
            "warnings": verdict.warnings,
            "checks": len(verdict.checks),
        },
        "catalog_snapshot": snapshot,
    }


def _asdict(profile: Any) -> dict[str, Any]:
    from dataclasses import asdict
    return asdict(profile)
