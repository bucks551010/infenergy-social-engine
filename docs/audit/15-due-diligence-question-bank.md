# Document 15 - Executive Due-Diligence Question Bank

## CTO and enterprise architecture

**What is the actual production architecture?** VERIFIED: one Railway Python service with in-process HTTP/scheduling, subprocess slot execution, mounted-volume JSON/SQLite/media, and external Gemini/social/CMS calls.  
**Is it a distributed multi-agent platform?** No. It is a pipelined rule/model system with an orchestrator and utility agents.  
**What breaks at 100 customers?** Process-local locks, shared files, no tenancy, no durable queue, credentials, O(N) history, operator approval, and observability.  
**Can it be rebuilt?** Yes; Documents 02, 03, 04, and 07 define components, contracts, and target order.  
**Is vendor lock-in controlled?** Partially. Deterministic fallback reduces Gemini dependency; publisher APIs and provider-specific visual behavior remain coupled.

## Investor and board

**What has been proven?** A substantial deployed engine, candidate generation, integrations, tests, and single-brand operation.  
**What has not?** External customer demand, retention, CAC, gross margin, outcome lift, multi-client security, and a closed learning loop.  
**What is the moat?** Current code/method/operating learning are moderate; durable moat requires proprietary outcome data, benchmarks, vertical packs, workflow integration, and trust.  
**What capital milestone matters most?** Three to five paid pilots with measured economics and safe operation, followed by multi-tenant hardening.  
**Is it venture-scale?** MISSING/UNKNOWN. Managed service can be valuable; venture scale requires repeatable acquisition, software-like margins, low implementation variance, and expansion evidence.

## Customer and procurement

**Who owns our data and content?** Must be defined in contract; current repository does not settle customer commercial rights.  
**Can we export and delete it?** Not as a complete active workflow today; required before platform sale.  
**Do we approve actions?** The service plan says yes; runtime enforcement is missing and must be implemented/contracted.  
**What SLA exists?** None verified. Proposed initial approved-publish target is >=98%.  
**Which subprocessors receive data?** At least Railway, Google Gemini, and connected social/CMS providers; final list depends on configuration.  
**How do you measure value?** Customer baseline plus hours/vendor costs/errors/attributable gross profit; live analytics must first be repaired.

## Cybersecurity and privacy

**How are tenants isolated?** They are not; current system is single-tenant.  
**How are secrets stored?** Primarily deployment environment; Meta state may persist on volume. Query-token auth is a known risk.  
**Can prompt injection publish content?** Direct model output passes gates, but generation and publisher privileges are insufficiently separated. Harden before multi-client use.  
**Are logs/audits complete?** No. Basic stdout/status/history exist; immutable actor/action audit is missing.  
**Has it been penetration tested?** MISSING/UNKNOWN.  
**Are backups/restores tested?** MISSING/UNKNOWN.

## Legal and IP

**Who owns the code?** MISSING/UNKNOWN without contributor agreements and repository ownership review.  
**Is it patentable?** Unknown; candidates exist but require prior-art and counsel analysis.  
**Are generated images and references licensed?** MISSING/UNKNOWN per asset; create an asset/license register.  
**Who is liable for a wrong claim?** Must be allocated in MSA/SOW and approval terms; technical gates do not replace legal accountability.  
**Are AI disclosures/privacy terms adequate?** No verified customer legal package exists.

## Sales and go-to-market

**Why will a customer switch?** Managed accountability and grounded context can remove work, but switching evidence is not yet measured.  
**What is the beachhead?** Low-regulation owner-led service businesses with valuable leads and inconsistent content.  
**What is the sales cycle/CAC?** MISSING/UNKNOWN.  
**What should never be promised?** Virality, guaranteed leads, fully autonomous human-quality judgment, closed-loop optimization today, or enterprise readiness.  
**What proves repeatability?** Two industries, no code fork, standardized onboarding, target operator hours, retained customers, and measurable outcomes.

## Operations and employees

**Who handles a failed post at night?** MISSING; define support hours and severity/on-call policy.  
**Can another operator run it?** Partially with repository docs; access, dashboard, approval, and incident tooling are not mature.  
**What is the founder bottleneck?** Knowledge approval, customer review, sales, and exception handling.  
**What must be documented before hiring?** access matrix, daily/weekly runbook, approval SOP, incident response, customer configuration, billing/change control, and quality calibration.  
**How are changes released?** Git/Railway deployment exists; formal staging, migration, rollback, and change approval are incomplete.

## Competitor and acquirer

**Can a competitor copy the features?** Many features yes; copying validated business context, evaluations, data, integrations, and delivery discipline is harder.  
**What assets survive model commoditization?** evidence/profile schemas, workflow, policy, integrations, outcome data, evaluation corpus, and customer relationships.  
**What would an acquirer inspect first?** IP ownership, customer contracts/revenue, retention/margins, security, code quality, provider terms, data rights, incidents, and founder dependency.  
**What technical liabilities reduce value?** single-tenancy, JSON state, no queue/approval audit, analytics failure, schema ambiguity, and weak observability.  
**What increases strategic value fastest?** paid reference customers plus reliable, isolated, measurable operation.

## Questions requiring immediate evidence

1. Are any external paying customers live, and what revenue is external versus related-party/internal?
2. What are actual model, infrastructure, labor, support, and revision costs per approved post/customer?
3. Which branch/commit and Railway variables constitute the authoritative production configuration?
4. Who contributed code/design and are assignments complete?
5. Which customer/product claims have authoritative sources and review dates?
6. What caused current Meta analytics 400s, and when will LinkedIn analytics be configured?
7. Can one approved content version be proven identical to the published version?
8. Can state be restored from backup into a clean environment within the target RTO/RPO?
9. What objective experiment proves orchestrator/best-of outperforms the legacy path?
10. What operator/client load can the current service sustain before quality or response time degrades?

Until answered, these should remain explicit diligence conditions, not optimistic assumptions.
