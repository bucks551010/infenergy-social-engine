# Shadow-Mode Evaluation Report

Run date: 2026-08-13 UTC

## Scope

Three Instagram-only Shadow Mode scenarios ran through the normal orchestrator,
platform adaptation, validation, quality governance, human review, Strategy
Integrity review, and Publish Decision path. `SOCIAL_SHADOW_MODE=true` stopped
each run before media hosting or any external publisher adapter.

The live first-party heartbeat also inspected `https://infenergypower.com/`.
It found current Infenergy messaging for modular solar generators, outage
readiness, portable power, and product education.

## Observed Results

| Scenario | Result | Evidence |
| --- | --- | --- |
| Auto-selected portable-power scenario (`55f19e41d74b`) | WEAK | Instagram caption populated (1075 characters), quality 100, human review `PASS`, integrity `ALIGNED`; authoritative decision `revise` because the orchestrator critic required revision. Gemini was unavailable, so copy used the recorded deterministic template fallback. |
| SOREIN-MB2000, Education (`df54327303bd`) | FAIL | Instagram caption populated (1181 characters), human review `PASS`, integrity `ALIGNED`; authoritative decision `do_not_publish` because a runtime claim was not supported. |
| INF-9792, Trust (`8d49bd14ddba`) | FAIL | Instagram caption populated (1079 characters), quality 98, human review `PASS`, integrity `ALIGNED`; authoritative decision `do_not_publish` because a runtime claim was unsupported and its image candidate did not match. |

Every platform record was persisted as `shadow_not_published` with
`shadow_mode_no_external_publication`. No external post, upload, or media
hosting call occurred.

## Intelligence Evaluation

| Dimension | Result | Notes |
| --- | --- | --- |
| First-party research | PASS | The actual homepage was retrieved after adding a descriptive research User-Agent. The heartbeat created an evidence-backed opportunity. |
| Competitor discovery | FAIL | DuckDuckGo returned a 202 challenge page. Bing was reachable but yielded irrelevant results and was rejected by entity relevance filtering. The system returned structured `SOURCE_UNAVAILABLE`; no competitor was fabricated. |
| Consumer discovery | FAIL | The same bounded public discovery path returned structured `SOURCE_UNAVAILABLE`; no invented customer question was treated as evidence. |
| Category conversation / whitespace / positioning | WEAK | With no credible competitor or consumer evidence, positioning correctly returned `insufficient support`. It must not be promoted to a publishable competitive claim. |
| Human connection | WEAK | The three runtime artifacts returned `PASS`, but these runs were deterministic fallback copy and did not validate varied real customer-language inputs. The system did not use emergency/family fear language as a reason to publish. |
| Non-price edge | WEAK | Runtime locks used `DECISION_SUPPORT_EDGE` grounded in verified facts. Broader competitive edges remain unvalidated while research is unavailable. |
| Candidate diversity / Council | FAIL | The current normal runtime did not receive a Council-approved strategy because competitor and consumer evidence were unavailable. Shadow records correctly show the downstream lock/reviews, but this is not evidence that a multi-candidate Council decision is ready. |
| Platform adaptation | PASS | Instagram captions were populated in all three runs; absent WordPress, Facebook, and LinkedIn fields did not lower the Instagram-only quality scores. |
| Strategy integrity | PASS | Every sampled runtime package persisted `ALIGNED`. The unit contract separately proves `MATERIAL_DRIFT` becomes `strategy_integrity_material_drift`, which makes the authoritative decision non-publishable. |
| Claim safety | PASS | Unsupported claims blocked two scenarios. The system did not publish around those failures. |

## Production Closure Status

The original artificial Instagram score of `67` was not reproduced locally:
the Instagram-only Shadow package carried a non-empty `ig_caption`, its
Instagram platform record, selected audience/angle, model route/fallback,
human review, integrity review, and authoritative Publish Decision.

Railway `/content-preview` remains unresolved because no authorized
`MANUAL_RUN_TOKEN` was available. No credential was exposed, fabricated, or
rotated. The deployed endpoint must be re-tested with authorization before
Canary Mode or autonomous publication is considered.

## Required Next Validation

1. Restore a permitted public research source or provide approved research access, then rerun question-only competitor and consumer discovery. Relevance must be reviewed before a source becomes evidence.
2. Resolve the two observed product claim/image validation failures using the existing product truth and asset paths; do not loosen the gates.
3. Run additional Shadow scenarios only after real consumer and competitor evidence is available, then assess Council candidate diversity and human-connection quality.
4. Verify the protected Railway `/content-preview` with authorized access before any Canary Mode consideration.