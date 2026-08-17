# Architecture Rebuild

## Objective

Make social publication cooperative rather than rejection-driven:

1. Read published history before selecting a product or topic.
2. Generate a diverse text-only candidate pool off-peak.
3. Run all non-time-dependent quality, claim, and governance gates before a candidate enters the pool.
4. At slot time, re-check duplicate and scheduling rules, generate the image only for the selected winner, then publish.
5. Never report a no-publish run as success.

## Non-Negotiable Controls

- Claim governance and claim validation remain fail-closed.
- Exact-caption duplication remains a blocking protection.
- Cooldowns are read from `data/marketing/anti_repeat_config.json`.
- Candidate-pool exhaustion uses LRU fallback and is observable; it does not silently stop generation.
- Candidate persistence uses the existing `data/` JSON approach.
- A candidate is consumed only after publication history is persisted.
- Images are deferred during pool creation and generated only in the slot-time winner path.

## Delivery Scope

The implementation and remaining Railway verification are recorded in
`docs/ARCHITECTURE_REPORT.md`.