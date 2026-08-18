# LIVING CONTENT SYSTEM — Phase 1 Forensic Report

> **Forensic completed:** 2026-08-18T15:54 UTC  
> **Environment:** Railway production (isolated state snapshot)  
> **Safety confirmed:** 0 images generated, 0 publisher calls, no production state contamination

---

## PHASE 0 — SYSTEM STATUS

### Deployed SHA
The system is running on Railway at `jubilant-harmony-production-5bd1.up.railway.app`.
- `dry_run: false`, `shadow_mode: false` — system is in live mode
- Recent successful publishes confirmed in `/history`
- Candidate pool depth was 1 at forensic start time

### Publishing Capability
**CONFIRMED.** Production history shows successful external publishes:

| Post ID | Platform | Quality | Hook | Status |
|---------|----------|---------|------|--------|
| `97758313fbdc` | multi | 84.14 | "Can a phone serve as a true mobile power reserve..." | success |
| `7d1fc8fec8d6` | instagram_feed | 80.32 | "Can your current power bank actually handle..." | success |
| `31c65514b678` | instagram_feed | 79.52 | "Why does your laptop screen go black..." | success |
| `6100564cf861` | instagram_feed | 79.78 | "Ever notice how your laptop battery drains..." | success |

All posts used real Gemini for copy generation (`social_intelligence_orchestrator`) and real Gemini for image generation (`gemini-2.5-flash-image`). Claims were verified against `product_verified_facts`. Visual artifacts were created at correct dimensions.

### Data Persistence
**UNCONFIRMED.** Pool and history files exist in `/data/`. Persistence across redeploy not yet verified.

## 🛑 GATE 0 RESULT: **PASSED** — system publishes confirmed

---

## PHASE 1 — THE FORENSIC

### 1.1 Experiment Design

The forensic agent generated 10 autonomous content decisions on Railway with full instrumentation:
- Isolated state snapshot (no production contamination)
- Text-only mode (image generation boundary intercepted)
- All gates exercised: validation, quality, duplicate, presentation

### 1.2 Raw Results

```
10 requested decisions
├─ 10 passed validation (0 claim blocks)
├─ 10 passed quality (0 critic rejections)
├─ 10 reached duplicate checking
│  ├─ 1 became TEXT_READY
│  └─ 9 were blocked: duplicate_exact_caption_within_window
├─ 0 recovered into text-ready content
├─ 0 image-provider calls
├─ 0 publisher calls
└─ 0 production-state changes
```

### 1.3 Critical Finding: NOT 10 Independent Content Decisions

**All 10 runs selected the exact same pooled candidate:**

| Run | Slot | Candidate ID | Caption Signature | Result |
|-----|------|--------------|-------------------|--------|
| 1 | morning | `4f6c68a8-fd14-4469-bf82-e1aa94a80de9` | `3baca66a8419b2600f68f331eaa6fca5` | TEXT_READY |
| 2 | midday | `4f6c68a8-fd14-4469-bf82-e1aa94a80de9` | `3baca66a8419b2600f68f331eaa6fca5` | FAILED_DUPLICATE |
| 3 | evening | `4f6c68a8-fd14-4469-bf82-e1aa94a80de9` | `3baca66a8419b2600f68f331eaa6fca5` | FAILED_DUPLICATE |
| 4 | morning | `4f6c68a8-fd14-4469-bf82-e1aa94a80de9` | `3baca66a8419b2600f68f331eaa6fca5` | FAILED_DUPLICATE |
| 5 | midday | `4f6c68a8-fd14-4469-bf82-e1aa94a80de9` | `3baca66a8419b2600f68f331eaa6fca5` | FAILED_DUPLICATE |
| 6 | evening | `4f6c68a8-fd14-4469-bf82-e1aa94a80de9` | `3baca66a8419b2600f68f331eaa6fca5` | FAILED_DUPLICATE |
| 7 | morning | `4f6c68a8-fd14-4469-bf82-e1aa94a80de9` | `3baca66a8419b2600f68f331eaa6fca5` | FAILED_DUPLICATE |
| 8 | midday | `4f6c68a8-fd14-4469-bf82-e1aa94a80de9` | `3baca66a8419b2600f68f331eaa6fca5` | FAILED_DUPLICATE |
| 9 | evening | `4f6c68a8-fd14-4469-bf82-e1aa94a80de9` | `3baca66a8419b2600f68f331eaa6fca5` | FAILED_DUPLICATE |
| 10 | morning | `4f6c68a8-fd14-4469-bf82-e1aa94a80de9` | `3baca66a8419b2600f68f331eaa6fca5` | FAILED_DUPLICATE |

**Generated candidates: 0 across all 10 runs**

This is not evidence of 9 independent duplicate collisions. This is evidence of a **pool quarantine gap**.

### 1.4 Root Cause: Pool Lifecycle Bug

The causal structure:

```
┌─────────────────────────────────────────────────────────────────┐
│ Candidate pool contains 1 available candidate                   │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ Engine selects first available candidate from pool              │
└────────────────────────┬────────────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────────────┐
│ Validation passes, quality passes, duplicate gate evaluates     │
└────────────────────────┬────────────────────────────────────────┘
                         │
         ┌───────────────┴───────────────┐
         ▼                               ▼
┌─────────────────────┐    ┌─────────────────────────────────────┐
│ Run 1: No history   │    │ Runs 2-10: Caption matches history  │
│ match → TEXT_READY  │    │ → FAILED_DUPLICATE_FRESHNESS        │
└─────────┬───────────┘    └────────────────────┬────────────────┘
          │                                     │
          ▼                                     ▼
┌─────────────────────┐    ┌─────────────────────────────────────┐
│ Candidate consumed  │    │ Candidate remains "available"       │
│ (text-ready result) │    │ (no platform result → no consume)   │
└─────────────────────┘    └────────────────────┬────────────────┘
                                                │
                                                ▼
                           ┌─────────────────────────────────────┐
                           │ Next run selects SAME candidate     │
                           │ → Same content → Same duplicate     │
                           └─────────────────────────────────────┘
```

**The bug:** `CandidatePool.consume()` is called only after a `published` or `dry-run` platform result. A duplicate-blocked candidate has no platform result, so it remains `available` and gets re-selected indefinitely.

### 1.5 Failure Distribution (CORRECTED)

| Failure mode | Count /10 |
|---|---:|
| Unsupported benefit bridge (feature → unverified value claim) | 0 |
| Research needed for a fact already in the catalog | 0 |
| Revision reintroduced the original problem | 0 |
| Insufficient human/contextual material to write from | 0 |
| Generic or weak hook | 0 |
| Opportunities too similar to each other | 0 |
| **Pool quarantine gap (same candidate re-selected)** | **9** |
| Passed cleanly | 1 |

### 1.6 Content Quality Evidence (from production history)

The system **can** generate diverse, high-quality content. Production posts show:

- **Different hooks** on consecutive posts (not templated)
- **Quality scores 79-84%** (band: "strong" to "revise")
- **Claims verified** against `product_verified_facts`
- **Critic feedback** used for revision objectives
- **Real Gemini visuals** generated with product overlays
- **Diverse products** across the catalog (PowerPulse Pro 200 featured in recent posts)

Sample claim verification from history:
```json
{
  "claim": "The PowerPulse Pro 200 provides a reliable 154Wh capacity and 41,600mAh reservoir",
  "verification_status": "verified",
  "provenance": "VERIFIED_PRODUCT_FACT",
  "source": "product_verified_facts"
}
```

---

## PHASE 1.3 — THE DESIGN VERDICT

### **(D) Neither — the bottleneck is elsewhere.**

The forensic does not support building Content Readiness Packages to solve claim friction or creative starvation:

| Hypothesis | Evidence | Verdict |
|------------|----------|---------|
| **(A) Claim friction dominates** | 0/10 validation failures, 0 high-risk claim blocks | **NOT SUPPORTED** |
| **(B) Creative starvation dominates** | 0/10 quality failures, production shows diverse hooks | **NOT SUPPORTED** |
| **(C) Both** | Neither dominates | **NOT SUPPORTED** |
| **(D) Bottleneck is elsewhere** | 9/10 were same-candidate re-selection, not independent failures | **SUPPORTED** |

**The actual bottleneck is a pool lifecycle control-flow bug, not a content-generation capability problem.**

---

## 🛑 GATE 1 RESULT: Do NOT proceed to Phase 2 (Content Readiness Packages)

The forensic does not justify building packages. Building packages would be solving the wrong problem.

---

## REQUIRED FIX: Pool Quarantine

Before proceeding to Phase 2, fix the pool lifecycle so duplicate-blocked candidates are quarantined:

### Option A: Quarantine on duplicate block
When a candidate fails the duplicate gate, mark it `status: "quarantined"` with reason and timestamp. It should not be selectable again until:
- The matching history record ages out of the 180-day window, OR
- An operator manually releases it

### Option B: Discard and regenerate
When a candidate fails the duplicate gate, mark it `status: "discarded"` and trigger fresh generation for the current slot.

### Option C: Fallback to fresh generation
When the only available pool candidate fails duplicate checking, bypass the pool and generate fresh content for this slot.

**Recommendation: Option C** — it provides immediate recovery without manual intervention and matches the "never produce silence" principle.

---

## POST-FIX FORENSIC REQUIREMENT

After the pool quarantine fix is deployed:

1. Clear the candidate pool or manually quarantine the stuck candidate
2. Run the forensic agent again with 10 fresh decisions
3. Confirm the 10 runs produce 10 different content decisions
4. Re-evaluate the failure distribution against Phase 1.2 categories
5. Only then determine if Phase 2 (Content Readiness Packages) is justified

---

## APPENDIX: Safety Confirmation

```
Experiment ID: content_generation_10_run_20260818T152856Z
Started: 2026-08-18T15:29:30 UTC
Finished: 2026-08-18T15:29:45 UTC

Configuration:
  post_text_only: true
  social_dry_run: true
  channels_forced_off_only_inside_isolated_process: true

Safety metrics:
  image_provider_calls: 0
  image_generation_boundary_intercepts: 10
  publisher_calls: 0
  production_state_contaminated: false
```

The forensic ran in complete isolation. No external posts were made. No production state was modified.

---

## APPENDIX: Duplicate Policy (current)

```
Active blocking signature: exact_caption only
Comparison window: 180 days
Advisory telemetry (non-blocking):
  - topic_signature
  - hook_signature
  - cta_signature
  - product_signature
  - scenario_signature
  - lesson_signature
```

The duplicate policy is correctly narrow. The problem is not the policy — it's that rejected pool candidates are retried instead of replaced.
