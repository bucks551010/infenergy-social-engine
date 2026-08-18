# Human Truth Engine v2 Audit

**Audited:** 2026-08-18  
**Source of truth:** `docs/HUMAN_TRUTH_ENGINE.md`  
**Scope:** Current repository implementation and completed pool forensic work.

## Current Verdict

The prior work correctly established that repeated duplicate failures were caused by candidate
pool lifecycle, not weak content generation. The pool quarantine repair is deployed. It does
not, however, complete the Human Truth Engine plan.

Phase 0 publishing has evidence of successful historic publishes. Persistence across a Railway
redeploy remains unverified, so the Phase 0 persistence requirement is still open.

## Completed In This Audit

- Preserved the governing plan unchanged at `docs/HUMAN_TRUTH_ENGINE.md`.
- Added `docs/HUMAN_MATERIAL_INTAKE.md`, an owner-facing verbatim-only intake sheet.
- Added the static Human Truth repository skeleton under `data/marketing/human_truth/`:
  - `tension_library.json`
  - `human_material_reserve.json`
  - `reader_value_criteria.json`
  - `trust_behaviors.json`
- Added `scripts/social/static_repository.py` and tests that reject code-managed writes to
  the Human Truth static repository while allowing living-data writes.

No lived memories, founder narrative, customer quotes, local knowledge, tensions, captions, or
hooks were invented. The owner must supply those entries verbatim.

## Implementation Map

| Requirement | Status | Evidence | Gap |
|---|---|---|---|
| Candidate pool / duplicate safety | Partial | `scripts/social/candidate_pool.py`, `scripts/run_engine.py` | Quarantine is post-failure; a current-slot fresh-generation fallback is not implemented. |
| Static/living boundary | Partial | `scripts/social/static_repository.py` | The new Human Truth static files are guarded; existing generation code does not yet consume them. |
| Human Material Reserve and intake | Structure complete | `docs/HUMAN_MATERIAL_INTAKE.md`, `data/marketing/human_truth/human_material_reserve.json` | Owner material is intentionally empty. |
| Tension-first selection | Absent | Existing emotional-driver and strategy modules are adjacent only | No tension selection, moment selection, or product-optional flow in production generation. |
| Explicit job dimension | Partial | Existing strategic briefs | Required jobs, including honest-limit and skeptic-answer work, are not selected or recorded consistently. |
| Reader Value and trust signals | Definitions complete, runtime absent | `reader_value_criteria.json`, `trust_behaviors.json` | `score_content.py` does not score/gate these dimensions; candidates can still enter the pool without them. |
| Capability-not-fear ethical gate | Partial | `scripts/social/human_connection_review.py` | Keyword-based exploitation detection does not distinguish fear leverage from capability framing robustly. |
| Structured art direction | Partial | `scripts/social/visual_intelligence.py`, `scripts/social/visual_provider.py` | Art direction exists, but its source is not yet tension-first. |
| Prompt governance before render | Absent and critical | `scripts/social/visual_provider.py` calls `social_visuals.generate_visuals()` directly | No fail-closed prompt-text gate for visual claims, prohibited scenes, or disaster spectacle. |
| Three prompts, one render | Unverified / partial | Visual orchestration | No enforced three-direction score-and-select contract. |
| Visual novelty telemetry | Partial | Visual intelligence metadata | No 30-day scene/environment/composition/palette/time-of-day trend. |
| Seasonal lookahead | Absent | Candidate-pool batch builder | No hurricane-window pre-staging or coverage alert. |
| Pool depth early refill | Partial | `scripts/build_candidate_pool.py`, `/status` | Depth is visible but no verified automatic low-depth batch trigger. |
| Token and Gemini budget pre-checks | Partial / absent | Meta refresh support | No seven-day token warning, token-age status field, or Gemini budget pre-flight. |
| Engagement ingestion | Partial | `scripts/social/analytics_ingestion.py`, `performance_learning.py` | Real Railway metric pulls and attribution to candidate/tension/job/Reader Value are unverified. |
| Exploration reserve | Absent | Rotation code | No enforced 25-30% allocation to untested territory. |
| Anti-ossification guards | Absent | Basic rotation tests only | No copy/visual novelty floor, prompt-governance, Reader Value, or exploration-reserve guard tests. |

## Required Owner Inputs

1. Raw lived memories, founder origin, customer voice, local knowledge, and convictions through
   `docs/HUMAN_MATERIAL_INTAKE.md`.
2. Owner-approved tension entries in `tension_library.json`.
3. Brand Truth and Visual Identity content derived from existing owner-authored materials or
   supplied explicitly where current files are thin.
4. Approval of any future system proposal to modify static Human Truth files.

## Next Implementation Order

1. Wire tension selection, Reader Value scoring, trust signals, and the capability-not-fear
   gate into candidate creation; then validate 10 Railway decisions before allowing pool entry.
2. Add prompt governance directly before every `social_visuals.generate_visuals()` call, with
   a guard test proving failed prompts cannot render.
3. Add seasonal lookahead and pool coverage for the upcoming hurricane window.
4. Verify real platform analytics ingestion and join outcomes to `candidate_id`, tension, job,
   Reader Value, trust signals, and visual scene.
5. Add anti-ossification telemetry and the final report only after the preceding gates have
   measured real Railway runs.

## Known Validation Status

- `tests/test_static_repository.py`: 2 passed.
- `tests/test_phase13_phase14.py`: 29 passed before this audit's static-repository additions.
- Full test suite was previously 394 passed, 1 unrelated business-intelligence roster failure.
- The deployed manual-run dry-run protection is pending Railway deployment confirmation before
  any platform-forced production validation is attempted.