# Document 06 - Security, Governance and Reliability Assessment

## Executive assessment

The system is suitable for supervised single-brand experimentation, not enterprise multi-client operation. It has meaningful claim controls, safe URL handling, constant-time token comparison, bounded retries, dry-run behavior, and provider fallbacks. It lacks tenant isolation, role-based access, durable approvals, enterprise secret handling, full auditability, rate limiting, reliable orchestration, and proven disaster recovery.

## Risk register

| Risk | State | Likelihood/impact | Control and required action |
|---|---|---|---|
| Unapproved publication | VERIFIED design gap | Medium/Critical | Keep dry run; implement immutable approval gate |
| Cross-customer leakage | MISSING tenancy | High/Critical after commercialization | PostgreSQL RLS/app scoping, tenant tests, per-tenant secrets/storage |
| Query-token exposure | VERIFIED | Medium/High | Replace URL tokens with short-lived authenticated sessions |
| Prompt injection from sites/feeds/catalog | INFERRED | Medium/High | Treat retrieved text as data, delimit, sanitize, allowlist tools, validate outputs |
| Unsupported claims | VERIFIED runtime examples | High/High | Source coverage, hard material-claim block, human escalation |
| Platform side effect without local record | VERIFIED architectural window | Medium/High | Idempotency key, durable job/receipt transaction, reconciliation worker |
| Gemini cost/runaway calls | MISSING complete ledger | Medium/High | Per-tenant budgets, call caps, central gateway, alerts |
| Gemini/provider outage | VERIFIED graceful fallback | Medium/Medium | Test fallbacks; distinguish degraded output visibly |
| Analytics blind spot | VERIFIED live | High/High | Repair Meta, configure LinkedIn, source-health SLO |
| Repetitive visuals | VERIFIED live | High/Medium | diversity gate, reference rotation, scene/archetype constraints |
| JSON corruption/schema drift | VERIFIED risk | Medium/High | typed schemas, atomic writes, migrations, database transactions |
| Missed scheduled jobs | VERIFIED | Medium/High | durable scheduler/queue and replay policy |
| Single founder/operator dependency | INFERRED | High/High | runbooks, access escrow, cross-training, on-call plan |

## Threat boundaries

Untrusted inputs include HTTP parameters/bodies, RSS/site text, CSV/HTML product descriptions, remote images, model outputs, platform responses, and customer-uploaded assets. Publisher credentials and destructive delete operations require a narrower trust boundary than generation. **RECOMMENDED:** separate generation and publishing identities/services so a compromised prompt/model path cannot publish.

## Governance controls

- Business facts require provenance, owner status, confidence, and review date.
- Material product/safety/performance claims require verified evidence.
- Model output is always untrusted until deterministic validation.
- New customers start approval-required; sensitive content never graduates to autopilot.
- Every approval/publish/delete/credential change needs actor, timestamp, reason, object version, and correlation ID.
- Human review must be called “human” only when a person acted; automated human-connection review is an evaluator.
- Emergency pause must work per organization, campaign, and platform.

## Reliability objectives

| SLI | Initial target |
|---|---:|
| API availability | 99.9% monthly |
| Approved posts published in window | >=98% |
| Duplicate live publications | 0 |
| Material unsupported claims published | 0 |
| Approval-to-content version mismatch | 0 |
| Source/analytics collection success | >=95% per supported platform |
| Recovery point objective | <=15 minutes for transactional state |
| Recovery time objective | <=4 hours initially |

## Architecture scores

| Dimension | Score/10 | Explanation |
|---|---:|---|
| Security | 5 | Basic secret/auth/URL controls, but URL tokens and no IAM/tenancy |
| Reliability | 6 | Good local fallback/retry behavior, weak durable orchestration |
| Observability | 4 | Health/status/history exist; no metrics/traces/alerts/cost completeness |
| Data architecture | 5 | Rich data model concepts, weak runtime schemas and transactions |
| Memory architecture | 5 | Several useful memories, conflicting ownership and incomplete feedback |
| AI architecture | 7 | Strong deterministic fallback and evidence intent; prompt/cost governance incomplete |
| Agent design | 7 | Clear specialization; “agent” labels overstate some deterministic roles |
| Maintainability | 6 | Tests/modules help; mega-module and dictionary contracts hurt |
| Cost efficiency | 6 | Deterministic operation can be cheap; actual call/unit economics unknown |
| Reusability | 7 | Core logic is configurable, runtime remains Infenergy/single-tenant |
| Commercial readiness | 4 | Managed pilot possible under supervision; metrics/approval/tenancy missing |
| Enterprise readiness | 3 | Major IAM, compliance, DR, audit, SLA, isolation work remains |

## Control roadmap

P0: dry-run default, approval gate, external-state reconciliation, analytics repair, secret rotation, visual diversity.  
P1: typed schemas, PostgreSQL, durable jobs, tenant isolation, structured logs/alerts, backups/restore tests.  
P2: RBAC/SSO, encrypted per-tenant OAuth vault, audit export, DPA workflows, vulnerability management, penetration test.  
P3: formal SLOs, incident drills, vendor risk, SOC 2 readiness only after controls operate consistently.

## Responsible AI

Document model limitations; disclose AI assistance contractually; permit customer opt-out for sensitive workflows; minimize customer data sent to providers; prevent training reuse where provider terms allow; test demographic and fear-based persuasion harms; prohibit fabricated testimonials and exploitative targeting; preserve an accountable human decision maker.
