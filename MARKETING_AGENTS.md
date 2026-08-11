# Marketing Agent Team

This repo now includes a collaborative marketing-agent system built around your brand data and product catalog.

## What It Produces

- Brand profile (voice, authority, demographics, psychographics, color direction)
- Audience segments with triggers and objections
- Offer strategy and value stack
- Conversion copy pack (hero, hooks, CTA bank, ad angles)
- Creative direction (image prompts + short video concepts)
- Channel operations playbooks and message matrix
- SEO pillar clusters and internal-link strategy
- Lifecycle email flow blueprint
- Growth experimentation queue (weekly tests)
- Execution pack for direct handoff to posting systems
- QA score with improvement actions

Outputs are written to `data/marketing/` as timestamped JSON + Markdown, including:

- `marketing_strategy_*.json` (full strategy graph)
- `execution_pack_*.json` (operator-ready payload)
- `marketing_summary_*.md` (human summary)
- `weekly_plan_*.json` / `weekly_plan_*.md` (7-day sequence)
- `campaign_plan_*.json` (runtime funnel + schedule + guardrails)

It also supports a weekly planner that builds a 7-day, 3-slot campaign sequence from the latest strategy snapshot.

## Agent Roles

1. `market_research_agent`:
- Interprets market position and buyer jobs.

2. `audience_psychology_agent`:
- Maps pain points, drivers, objections, and triggers by segment.

3. `brand_voice_agent`:
- Defines your conversion voice using principle-based persuasion.

4. `offer_strategy_agent`:
- Builds offer framing, value stack, and risk-reversal structure.

5. `copywriter_agent`:
- Generates hero copy, subject lines, social hooks, and CTA bank.

6. `creative_director_agent`:
- Produces image prompts and video concept directions.

7. `channel_editor_agent`:
- Adapts messaging for Facebook, Instagram, LinkedIn, and email.

8. `seo_content_agent`:
- Creates pillar clusters and metadata strategy.

9. `lifecycle_email_agent`:
- Designs lead nurture and reactivation flows.

10. `growth_experimentation_agent`:
- Produces test hypotheses, variants, and success metrics.

11. `conversion_qa_agent`:
- Runs quality checks before publishing.

## Run

```bash
python scripts/run_marketing_team.py
python scripts/run_marketing_weekly.py
```

Optional environment variables:

- `BRAND_SITE_URL` (default: https://www.infenergypower.com)
- `MARKETING_PRODUCTS_DIR` (default: data/products)
- `MARKETING_OUTPUT_DIR` (default: data/marketing)
- `GEMINI_API_KEY` (enables AI refinement in copy agent)
- `GEMINI_MODEL` (default: gemini-2.5-flash)
- `IG_CATEGORY_FALLBACKS_JSON` (optional JSON map for category-level image fallbacks)
- `IG_VALIDATE_IMAGE_URLS` (default: true; preflight-check image URLs before Instagram publish)
- `ENABLE_FACEBOOK_SLOTS`, `ENABLE_INSTAGRAM_SLOTS`, `ENABLE_LINKEDIN_SLOTS`, `ENABLE_WORDPRESS_SLOTS` (comma-separated slot allowlists, e.g. `morning,midday`)
- `SKIP_RECENT_SUCCESS_HOURS` (if > 0, skip live channel publish when a recent success exists in the same slot)
- `ANTI_REPEAT_HOOK_WINDOW` / `ANTI_REPEAT_CTA_WINDOW` (history window sizes for rotation)
- `UTM_CAMPAIGN_NAME` (default: `infenergy_engine`)

## Worker Runtime Visibility

- `GET /status` now includes recent quality summary.
- `GET /history?limit=20` returns recent run history with score metadata.
- `GET /campaign` returns the latest campaign plan artifact metadata.

## Notes

- The system uses persuasion principles inspired by high-energy motivational and value-driven direct-response frameworks.
- It avoids direct imitation of specific living public figures while still producing strong conversion copy.
