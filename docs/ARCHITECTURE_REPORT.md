# Architecture Rebuild Report

## Implemented

- `scripts/social/candidate_pool.py` provides a JSON-backed pool at
  `data/social/candidate_pool.json`, a history-derived rotation ledger, cooldown-aware LRU
  selection, expiration, and explicit LRU fallback when a pool is exhausted.
- `scripts/build_candidate_pool.py` generates text-only candidates, applies claim-boundary,
  validation, quality, evidence-readiness, and publication-decision checks before persistence,
  and rejects in-batch rotation collisions. It does not generate visuals.
- `scripts/generate_posts.py` supports `POST_TEXT_ONLY=true`; all legacy and orchestrator visual
  generation paths defer rendering in that mode. Legacy automatic product and general-topic
  selection use the shared history-backed LRU selector.
- `scripts/social/product_eligibility.py` derives eligibility from each matching product brief's
  non-empty `verified_facts` and filters both inventory-catalog and BI-offering source pools before
  selection. Current inventory evidence: 49 catalog products, 36 eligible products, 13 zero-fact
  exclusions.
- `scripts/run_engine.py` loads an available candidate before generating a new one, rechecks it
  through the ordinary slot-time path, generates a deferred visual only after final runtime gates,
  records candidate and image telemetry in history, and consumes the candidate only after a
  platform outcome is persisted.
- `worker.py` runs the batch builder on the existing scheduler at `10:00 UTC`, exposes
  `candidate_pool_depth` on `/status`, and reports `published`, `blocked_no_publish`, or
  `generation_failed` instead of treating every zero-exit run as success.

## Selection Coverage

| Selection site | State |
| --- | --- |
| Legacy automatic product selection (`_pick_product`) | Cooldown-aware LRU |
| Legacy general topic selection (`_pick_topic`) | Cooldown-aware LRU |
| Product-specific topic fit (`_pick_topic_for_product`) | Fit-ranked, then cooldown-aware LRU |
| Hook and CTA selection | Existing generators still use their current recent-hash APIs; CTA duplicate blocking remains disabled |
| Orchestrator selection | Its internal orchestrator path is not yet ledger-injected |

## Gate Split

Batch-time: claim-boundary correction, product-claim validation, quality score, evidence readiness,
and publication decision without time-sensitive duplicate checks.

Slot-time: channel eligibility, duplicate checks against current history, visual render and visual
review, then platform publication. A deferred visual is generated only after text passed the final
decision stack.

## Simulation

`tests/test_rotation_simulation.py` simulates 21 consecutive slots across 35 products and 30
topics. It verifies 21 unique product and topic selections with no exhaustion fallback. The model
would generate exactly one image per consumed candidate; the batch stage produces none.

The same test now derives a 36-product eligible pool from 49 brief-backed products with 13
zero-fact exclusions, then selects 21 unique products without exhaustion.

## Validation

- Focused candidate-pool and simulation tests: `4 passed`.
- Publisher and visual safety tests: `28 passed`.
- Full suite chunk one: `358 passed, 13 subtests passed`.
- Full suite chunk two: `30 passed`.
- Total full-suite result: `388 passed, 13 subtests passed`.

## Remaining Verification And Risk

- Railway has no declared persistent volume. A restart can erase `data/social/candidate_pool.json`
  and `post_history.json`, reducing rotation to empty-history behavior. Attach a Railway volume
  before treating cross-restart rotation as durable.
- This environment has no `GEMINI_API_KEY` and no active `MANUAL_RUN_TOKEN`; real-copy previews,
  batch generation, and Facebook publication must be verified on Railway after deployment.
- The selection exclusion rule deliberately does not write product specifications or mutate briefs;
  eligibility changes only when the owner supplies real `verified_facts`.