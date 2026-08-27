# Document 14 - Founder and Consultant Mastery Guide

## Mastery standard

You do not need to be the fastest programmer in the room. You must accurately explain the system, diagnose business fit, scope delivery, challenge unsafe claims, understand integration/security consequences, model ROI, and know when to involve specialists.

| Topic | What to know | Why | Required mastery | Customer question to answer |
|---|---|---|---|---|
| AI fundamentals | training vs inference, probabilistic output, evaluation, limits | avoid magical claims | Working | Why can the same prompt differ? |
| Generative AI | tokens, context, structured output, multimodal models, cost/latency | design reliable generation | Working | Which tasks need a model? |
| Agentic AI | orchestrators, tools, state, authority, approval, failure loops | explain architecture honestly | Advanced conceptual | Are these agents autonomous? |
| Prompt engineering | grounding, delimiters, schemas, injection, versioning | control model interaction | Working | How do you prevent invented facts? |
| Data | schemas, provenance, quality, retention, tenant isolation | data is the system’s truth | Advanced conceptual | Where does it know our business from? |
| APIs | OAuth, REST, webhooks, retries, rate limits, idempotency | integrations fail in real life | Working | What happens if Meta times out? |
| Automation | state machines, queues, retries, exceptions, human gates | operate safely | Advanced conceptual | How is a missed job recovered? |
| Software architecture | boundaries, contracts, databases, workers, observability | scope and lead technical teams | Advanced conceptual | What must change for 100 customers? |
| Cloud | deployment, volumes, managed services, backup/DR, regions | own availability/cost | Working | What does Railway host and persist? |
| Security | IAM, least privilege, secrets, encryption, threat modeling | pass buyer review | Advanced conceptual | Can one client see another’s data? |
| Responsible AI | hallucination, bias, disclosure, oversight, prohibited uses | protect people and brand | Advanced | Who is accountable for mistakes? |
| Business process | mapping, handoffs, exceptions, controls, baseline | find high-value workflows | Advanced | Which step should we automate first? |
| ROI | loaded labor, value capture, sensitivity, attribution | justify purchase honestly | Advanced | When does this pay back? |
| Consulting | discovery, scope, SOW, change control, governance | deliver repeatedly | Advanced | What do you need from us? |
| Sales | ICP, qualification, business case, objections, close | acquire viable customers | Advanced | Why not use ChatGPT/internal IT? |
| Change management | sponsor, adoption, training, resistance, operating cadence | technology alone does not create value | Working | How will employees use this safely? |
| Product strategy | segmentation, roadmap, moat, pricing, build/buy | allocate limited capital | Advanced | Is this service, SaaS, or platform? |

## System explanation you should own

Input business truth and runtime context -> deterministic strategy -> optional model generation -> evidence/quality controls -> approval policy -> platform action -> operational/performance events -> reviewed learning. Be able to state which links exist today and which are planned.

## 12-week curriculum

Weeks 1–2: run architecture walkthroughs and trace one request.  
Weeks 3–4: APIs/OAuth, failures, idempotency, Railway operations.  
Weeks 5–6: data/provenance, claims, security, multi-tenancy.  
Weeks 7–8: discovery, process maps, ROI and pricing.  
Weeks 9–10: demos, objections, proposals, change control.  
Weeks 11–12: incident tabletop, customer onboarding simulation, executive pitch and technical defense.

## Practical examinations

Explain a candidate from source evidence to publish decision; diagnose an ambiguous external publish timeout; reject an unsupported ROI claim; lead a discovery call; produce a scoped SOW; answer a security questionnaire; run a bad-content incident tabletop; compare managed service versus SaaS economics.

## Specialists to retain

Security architect/penetration tester, privacy and commercial counsel, patent/trademark counsel, accountant/finance advisor, platform API specialist, and vertical compliance expert as customer scope requires.
