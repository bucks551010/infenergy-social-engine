# TOTAL SYSTEM REPAIR — Find Everything, Fix Everything, Ship

## Mission

This repository is repaired on the deployed `master` baseline. Discovery precedes behavior changes; safety and governance are restored first; no live publication or infrastructure change is made during the repair; deployment requires a final explicit go/no-go gate.

## Binding Constraints

- Preserve `generate_posts.py` structure; do not refactor it.
- Restore the deleted final claim-evidence governance path and preserve its specification tests.
- Treat source code as authoritative over prior documentation.
- Do not invent electrical specifications, endpoints, or environment variables.
- Do not remove safety gates, delete tests, use a permanent duplicate override, publish live, or deploy.
- Use focused commits with test evidence for each confirmed concern.

## Required Operations

1. Audit every pre-publish drop path, anti-repeat satisfiability and retry behavior, claims, governance deletion set, history durability, fallback provenance, sanitization, scoring, publish safety, and silent failure paths.
2. Record confirmed findings in `docs/DEFECT_REGISTER.md` with evidence, severity, classification, impact, and repair.
3. Repair confirmed defects in dependency order: governance, other deleted safety capabilities, root blockers, anti-repeat, claims, scoring, sanitization, attribution, publish safety, durability preparation, regression tests, CI, and source-verified runbook.
4. Verify with the full suite, dry runs, governance bad/good proofs, generated-content review, and a projected publication-rate comparison.
5. Write `docs/TOTAL_REPAIR_REPORT.md` and stop at the deployment approval gate.

## Confirmed Inputs

- `social.claim_governance` existed at `7187ab0` and was deleted by `a81f9d7`.
- `origin/master` currently includes `97515dd`, which makes duplicate-only outcomes retryable and unlocks duplicate product conflicts.
- The source deployment configuration currently does not declare persistent Railway storage.

The complete user-provided mandate is retained in the VS Code conversation attachment; this repository copy records its operative requirements and constraints.