# Final Deploy

## Remaining Architecture Items

5. Deferred visual rendering and candidate consumption: required, implemented.
6. Honest run outcomes and pool depth observability: required, implemented.
7. Local simulation/reporting plus Railway verification: local portion complete; Railway proof is required before go-live.

## Evidence-Based Exclusion Contract

The selection layer is the inventory catalog returned by `inventory.db` and the BI offering list
used by the orchestrator. Both now call `social.product_eligibility.filter_evidence_eligible_products`.
It loads the existing `data/product_briefs/*.json` files, matches on `product_id`, and selects an
entry only when `verified_facts` contains at least one nonblank value. The rule is data-derived:
adding verified facts to a brief makes that product eligible on the next selection without code or
list changes.

The current inventory evidence is `49` catalog products, `49` matching briefs, `36` eligible
products, and `13` zero-fact exclusions. Each batch records `product_selection_exclusions` with
the excluded IDs, reasons, and eligible-pool size in `candidate_pool.json`.

The exclusion simulation creates 49 brief-backed products, derives 36 eligible products from the
brief facts, then selects 21 unique products without exhaustion.

## Railway Gate

Do not push this revision while Railway remains in live mode. Safe deployment requires setting
`SOCIAL_DRY_RUN=true` in Railway first, then running the real-Gemini batch and dry-run consumption
checks described in the deployment request. The active terminal still lacks `MANUAL_RUN_TOKEN`, so
the authenticated batch/slot endpoints cannot be called from this session.