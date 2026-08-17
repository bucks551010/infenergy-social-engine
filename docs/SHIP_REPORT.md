# Ship Report

**Status: NO-GO — do not merge or deploy.**

## Branch and SHA

- Branch: `repair/governance-restore`
- Remote SHA: `13cdec9ab8cedf6f1b1d1ec1c8f57dedf9480a45`
- Base: `origin/master` at `97515dd`

## Changes Applied

1. `f103fd1` restores final claim governance. `claim_governance.assess()` is passed into all runtime publication decisions and `publish_decision` blocks non-ready evidence. The recovered governance specifications pass: `11 passed`.
2. `13cdec9` declares `pytest>=8.0.0` in `requirements.txt`.
3. `13cdec9` makes anti-repeat configurable in `data/marketing/anti_repeat_config.json`: CTA checking is disabled, exact-caption remains strict, and one non-caption collision is tolerated. The prior CTA window was 14 days, or $14 \times 3 = 42$ planned posts, and was therefore unsatisfiable for a small CTA set.
4. `13cdec9` releases strategy state for retryable hook/topic/scenario/lesson duplicate conflicts; product conflicts still release the product lock.
5. `13cdec9` adds LinkedIn receipt handling: a pending receipt precedes the platform call, confirmed receipts are reused, and an unresolved pending receipt blocks a repeat call.

Focused validation passed:

- `tests/test_final_governance.py tests/test_evidence_safe_remediation.py`: `11 passed`
- `tests/test_phase13_phase14.py`: `26 passed`
- `tests/test_publish_safety_presentation.py tests/test_publishers_visuals.py`: `28 passed`

## Full Suite

Not green. The collected suite contains 383 tests. Two complete-run attempts terminated with `KeyboardInterrupt` during execution:

- `156 passed, 8 subtests passed in 83.37s`
- `179 passed, 13 subtests passed in 160.77s`

No test failure was reported before either interruption. This is still incomplete verification and blocks deployment.

## Dry-Run Results

`SOCIAL_DRY_RUN=true` was set. No publisher call was permitted.

| Slot | Result | Duplicate block | Decision reasons |
|---|---|---|---|
| morning | `skipped_validation_or_quality` | none | `hook-payoff mismatch`, `conversation_potential_weak`, `orchestrator_critic_requires_revision` |
| midday | `skipped_validation_or_quality` | none | `hook-payoff mismatch`, `conversation_potential_weak`, `orchestrator_critic_requires_revision` |
| evening | `skipped_validation_or_quality` | none | `hook-payoff mismatch`, `conversation_potential_weak`, `orchestrator_critic_requires_revision` |

The local environment also lacked `GEMINI_API_KEY`, a LinkedIn token, and valid Meta credentials. The resulting network-free candidates used `social_intelligence_orchestrator`; anti-repeat did not block them. The final critic gate did. Therefore the requested clean three-slot proof is not available.

## Governance Proof

The restored unmodified specifications prove both outcomes:

- A central unsupported medium-risk conclusion yields `RESEARCH_REQUIRED` and `do_not_publish`.
- A candidate with published `154Wh` and `200W` facts yields `READY` and is publishable under the decision contract.

## Verified Facts

The repository has 51 product briefs. Sixteen have zero `verified_facts` and are not usable for numeric claims: `03534566804e`, `7bc1f4586234`, `7dee4a7c5b2a`, `7ecefbd82dc7`, `901f9e73a136`, `c736078f2e72`, `GENERAL-PREPAREDNESS`, `SM-PRO-1`, `SM-PRO-2`, `SOREIN-AC200`, `SOREIN-FSP`, `SOREIN-MB2000`, `SOREIN-MBC`, `SOREIN-ORMC`, `SOREIN-PGP`, and `SOREIN-PH`.

No specifications were invented. The runtime removes unsupported numeric sentences before validation, then governance/quality may block the remaining candidate. These briefs need owner-supplied source-verified data or a separate selection-exclusion decision.

## Owner Actions Required

1. Investigate and resolve the full-suite `KeyboardInterrupt`; a complete test run is required.
2. Provide a non-live verification environment with valid Gemini and platform-readiness credentials, then rerun all three slots to publishability without live calls.
3. Confirm and configure Railway persistent storage. `railway.json` does not declare a volume.
4. Supply verified facts for the 16 zero-fact briefs.

## Deferred Debt

Full attribution logging and `/block-report`; regression armor and CI; documentation reconciliation; token refresh automation; failed-post queue; Gemini budget ceiling; scoring unification.

## Rollback

If deployment is later approved and a regression appears, use Railway Deployments to redeploy the prior production deployment, then restore `master` to its previous deployed SHA through the standard reviewed Git workflow. Do not use the stale local `master` worktree.