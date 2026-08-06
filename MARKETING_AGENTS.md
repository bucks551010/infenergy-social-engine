# Marketing Agent Team

This repo now includes a collaborative marketing-agent system built around your brand data and product catalog.

## What It Produces

- Brand profile (voice, authority, demographics, psychographics, color direction)
- Audience segments with triggers and objections
- Offer strategy and value stack
- Conversion copy pack (hero, hooks, CTA bank, ad angles)
- Creative direction (image prompts + short video concepts)
- Channel operations plan and QA checklist

Outputs are written to `data/marketing/` as timestamped JSON + Markdown.

It also supports a weekly planner that builds a 7-day, 3-slot campaign sequence from the latest bundle.

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

8. `conversion_qa_agent`:
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

## Notes

- The system uses persuasion principles inspired by high-energy motivational and value-driven direct-response frameworks.
- It avoids direct imitation of specific living public figures while still producing strong conversion copy.
