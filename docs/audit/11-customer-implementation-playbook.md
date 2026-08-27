# Document 11 - Customer Implementation Playbook

## Method: FRAMEWORK

**Find -> Record -> Analyze -> Model -> Engineer -> Review -> Work in shadow -> Release -> Keep improving**

| Stage | Customer responsibility | Consultant responsibility | Deliverable/gate |
|---|---|---|---|
| Find | sponsor, goals, stakeholders | identify workflows and value | signed discovery charter |
| Record | provide SOPs/data/access | map current state and exceptions | accepted process/data map |
| Analyze | validate baseline | risk, feasibility, ROI analysis | prioritized business case |
| Model | approve truth/voice/policy | build profile, evidence, schemas | knowledge acceptance |
| Engineer | sandbox access | configure/integrate/test | technical acceptance |
| Review | approvers participate | train and run UAT | approval/security sign-off |
| Work in shadow | compare outputs | operate without live actions | quality/SLO threshold met |
| Release | authorize production | controlled rollout/runbook | go-live decision |
| Keep improving | supply feedback/outcomes | report, experiment, change-control | quarterly value review |

## Onboarding inputs

Company/legal identity; goals/KPIs; products/services/prices/availability; audiences and customer evidence; brand/voice; approved and forbidden claims; legal/compliance policies; existing SOPs; channel accounts; OAuth authorization; website/CMS/CRM/DAM/analytics; historical content/performance; assets and licenses; approval hierarchy; incident contacts; data classification/retention; billing/procurement; accessibility/localization; seasonality/events; baseline labor and vendor costs.

## Discovery questionnaire

What outcome matters in 90 days? Who owns it? How is work performed today? Where does it wait or fail? Which decisions require judgment? What evidence makes a claim safe? Which actions require approval? What systems hold truth? Who can grant sandbox access? What data must never enter a model? What is the cost of delay/error? What baseline proves improvement? What happens when a platform/provider is unavailable? How is access revoked at offboarding?

## Technical implementation checklist

- Create organization/workspace and scoped roles.
- Register authoritative sources, owners, refresh cadence, and provenance.
- Ingest and validate offerings, audiences, brand rules, evidence, and prohibitions.
- Configure industry policy and customer overrides.
- Connect social/CMS/analytics in sandbox with least privilege.
- Build golden evaluation set: normal, edge, adversarial, unsupported-claim, duplicate, outage cases.
- Configure approval policy, live boundaries, budget, retention, alerts, and emergency pause.
- Run shadow mode and compare against human-reviewed baseline.
- Complete security/privacy/accessibility review.
- Obtain signed go-live acceptance and support contacts.

## Acceptance criteria

Zero cross-tenant leakage; zero unapproved actions; zero material unsupported claims in evaluation; >=95% golden-case acceptance before pilot; successful credential rotation; idempotent replay test; restore test; alert delivery; customer approvers trained; baseline and outcome measurement active.

## Training plan

Executives: outcomes, risk, governance, escalation.  
Operators: queue, review, edit, approve, retry, pause, incident procedure.  
IT/security: architecture, IAM, secrets, data flow, logging, vendor controls.  
Content owners: evidence, voice, claims, feedback, approval SLA.  
Support: triage, severity, reproduction, status communication.

## Customer success cadence

Week 1–2 daily launch checks; weekly operations and approvals for first 8 weeks; monthly outcome/cost report; quarterly business review and expansion decision; annual access, data, risk, and contract review.

## Offboarding

Pause schedules; confirm final external state; export customer-owned profiles/content/performance/audit data; transfer/revoke platform access; delete or retain by contract/legal hold; confirm deletion; preserve financial/security audit evidence; document unresolved incidents and portability limitations.

## Required agreements (counsel review)

NDA, MSA, SOW, DPA, SLA/support schedule, privacy notice, acceptable-use/AI disclosure, IP/content ownership, software license where applicable, security exhibit, subcontractor/provider schedule, and offboarding/data-return terms. Questions include approval liability, claim-source responsibility, model-provider use, indemnity, licensing of customer assets, incident notice, service credits, and generated-content ownership.
