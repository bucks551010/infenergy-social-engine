# Document 13 - Product Roadmap and Expansion Opportunities

## Current state

**VERIFIED:** deployed single-tenant Railway service; legacy/orchestrator/best-of generation; deterministic conversion/governance; Gemini text/image; Meta/LinkedIn/WordPress publishers; local-volume JSON/SQLite state; operator HTTP controls; incomplete analytics; no runtime client approval gate; dry run observed active.

## Stage roadmap

| Stage | Technical milestones | Commercial milestones | Exit gate |
|---|---|---|---|
| 1 Harden | repair analytics; approval gate; typed contracts; visual diversity; idempotent reconciliation; alerts | operate Infenergy with measured baseline | 30 days stable, zero unapproved/duplicate posts |
| 2 Modularize | split generation/publishing; central model gateway; schema versions; config hierarchy | document repeatable delivery and true costs | modules independently tested and metered |
| 3 Reuse | PostgreSQL, object storage, queue, organization model, encrypted OAuth | 3–5 paid pilots in two industries | no code forks; healthy margins and retention signals |
| 4 Configure | operator UI, industry packs, onboarding compiler, approvals, audit | standardized packages and training | new customer configured mostly through data/UI |
| 5 Platform | client portal, API, RBAC/SSO, billing/metering, integration SDK | partner/reseller and managed-platform tier | tenant/security/SLA evidence |
| 6 Enterprise | policy engine, regional deployment, advanced DR, compliance program | multi-location/mid-market contracts | procurement/security acceptance and reference customers |

## Priority sequence

P0 safety and truth -> P1 reliable operations -> P2 measured outcomes -> P3 multi-customer isolation -> P4 operator leverage -> P5 customer self-service. Do not reverse this sequence to build an attractive portal on unreliable foundations.

## Adjacent products from the existing architecture

| Opportunity | Reused assets | New work | Priority |
|---|---|---|---|
| Evidence-governed sales enablement | business profile, offerings, claims, copy | CRM, seller approval, collateral analytics | High |
| Catalog claim auditor | product ingestion, evidence/forbidden claims | bulk UI, compliance reporting | High |
| Executive content system | voice/profile, strategy, approval | interview ingestion, executive workflow | High |
| Customer-service knowledge agent | profile/evidence, retrieval contracts | ticket/chat integrations, answer citations | Medium |
| Marketing campaign operations | campaign, copy, visual, publishers | email/ads, attribution, budgets | Medium |
| Competitive/research briefing | BI sources/evidence/research | reliable collection, source ranking, analyst workflow | Medium |
| Employee training/content | business knowledge, generation, QA | LMS, assessments, permissions | Medium |
| Multi-location local marketing | config hierarchy, platform adapters | tenancy, location data, local approvals | After platform hardening |
| Regulated communications | claim governance | dedicated policy packs, legal review, monitoring | Future only |

## Build/buy/partner

Build the business profile, evidence compiler, strategy/governance, evaluation, and delivery method. Buy commodity IAM, secrets, queue, observability, billing, object storage, and transactional database capabilities. Partner for legal/compliance, platform API certification, specialized analytics, and vertical distribution.

## Metrics by stage

Technical: availability, publish success, duplicate/unapproved incidents, claim precision/recall, latency, provider fallback, cost per approved package, analytics freshness.  
Commercial: qualified pipeline, close rate, onboarding time, operator hours, gross margin, revision rate, adoption, retention, expansion, realized customer value.

## Long-term vision

A tenant-aware operating platform that turns governed company knowledge into approved actions across channels. Social content is the first vertical workflow, not the final product boundary. Expansion should reuse the same evidence, permissions, approvals, and outcome events rather than create disconnected “agents.”
