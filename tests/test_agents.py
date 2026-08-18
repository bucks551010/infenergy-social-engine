"""Focused unit tests for the additive agents package."""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = os.path.dirname(os.path.dirname(__file__))
SCRIPTS = os.path.join(ROOT, "scripts")
sys.path.insert(0, ROOT)
sys.path.insert(0, SCRIPTS)

from agents import (  # noqa: E402
    ab_variant_orchestrator,
    alt_text_accessibility,
    brand_voice_drift,
    carousel_slide_writer,
    crisis_relevance,
    cross_post_recycler,
    engagement_ingestion,
    hashtag_intelligence,
    learning_ingestion,
    performance_reflection,
    posting_time_optimizer,
    product_intelligence,
    product_matcher,
    retention,
    topic_intelligence,
    visual_qa_reviewer,
)
from agents.dispatcher import available_agents, run_agent  # noqa: E402
from agent_control_plane import validate_agent_output  # noqa: E402


def _make_history(tmp: str, rows: list[dict]) -> None:
    with open(os.path.join(tmp, "post_history.json"), "w", encoding="utf-8") as f:
        json.dump({"posts": rows}, f)


class AgentsTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="agents-")

    def test_dispatcher_lists_all_expected_agents(self) -> None:
        names = available_agents()
        for expected in (
            "engagement_ingestion",
            "performance_reflection",
            "learning_ingestion",
            "topic_intelligence",
            "carousel_slide_writer",
            "visual_qa_reviewer",
            "product_intelligence",
            "product_matcher",
            "brand_voice_drift",
            "hashtag_intelligence",
            "alt_text_accessibility",
            "posting_time_optimizer",
            "ab_variant_orchestrator",
            "crisis_relevance",
            "cross_post_recycler",
            "retention",
        ):
            self.assertIn(expected, names)

    def test_dispatcher_rejects_unknown_agent(self) -> None:
        result = run_agent("does_not_exist", self._tmp, {})
        self.assertIn("error", result)

    def test_engagement_ingestion_no_history_returns_zero(self) -> None:
        with patch.dict(os.environ, {"META_PAGE_ACCESS_TOKEN": ""}, clear=False):
            result = engagement_ingestion.run(self._tmp)
        self.assertEqual(result["posts_updated"], 0)
        self.assertFalse(result["page_token_present"])

    def test_engagement_ingestion_updates_recent_posts_when_token_present(self) -> None:
        _make_history(
            self._tmp,
            [
                {
                    "post_id": "p1",
                    "published_at": "2099-01-01T00:00:00+00:00",
                    "fb_id": "fb_123",
                    "ig_id": "ig_123",
                    "li_id": "skipped",
                }
            ],
        )
        with patch.object(engagement_ingestion, "_fb_metrics", return_value={"likes": 3, "comments": 1}), patch.object(
            engagement_ingestion, "_ig_metrics", return_value={"total_interactions": 7}
        ), patch.dict(os.environ, {"META_PAGE_ACCESS_TOKEN": "token"}, clear=False):
            result = engagement_ingestion.run(self._tmp)
        self.assertEqual(result["posts_updated"], 1)
        with open(os.path.join(self._tmp, "post_history.json"), "r", encoding="utf-8") as f:
            saved = json.load(f)
        self.assertEqual(saved["posts"][0]["engagement_metrics"]["facebook"]["likes"], 3)

    def test_performance_reflection_groups_by_dimensions(self) -> None:
        _make_history(
            self._tmp,
            [
                {
                    "post_id": f"p{i}",
                    "funnel_stage": "EDUCATION",
                    "hook_type": "question",
                    "logical_emotional_strategy": {
                        "principle_key": "contrapositive",
                        "archetype_key": "preparedness_buyer",
                    },
                    "engagement_metrics": {
                        "facebook": {"total_interactions": 5 + i},
                        "instagram": {"total_interactions": 2 + i},
                    },
                }
                for i in range(3)
            ],
        )
        result = performance_reflection.run(self._tmp)
        self.assertEqual(result["posts_analyzed"], 3)
        _, errors = validate_agent_output("performance_reflection", result)
        self.assertEqual(errors, [])

    def test_learning_ingestion_writes_recent_lessons_file(self) -> None:
        _make_history(
            self._tmp,
            [
                {
                    "post_id": "p1",
                    "status": "success",
                    "hook": "Do this or lose power",
                    "validation_errors": ["runtime_claim_not_supported"],
                    "quality_warnings": ["cta_adjusted:reason"],
                    "engagement_metrics": {
                        "facebook": {"total_interactions": 10},
                        "instagram": {"total_interactions": 2},
                    },
                }
            ],
        )
        result = learning_ingestion.run(self._tmp)
        lessons_path = os.path.join(self._tmp, "learning", "recent_lessons.json")
        self.assertTrue(os.path.exists(lessons_path))
        loaded = learning_ingestion.load_recent_lessons(self._tmp)
        self.assertGreaterEqual(len(loaded["winning_hooks"]), 1)
        self.assertEqual(result["posts_analyzed"], 1)

    def test_topic_intelligence_no_feeds_configured_is_noop(self) -> None:
        with patch.dict(os.environ, {"TOPIC_RSS_FEEDS": ""}, clear=False):
            result = topic_intelligence.run(self._tmp)
        self.assertEqual(result["imported_count"], 0)

    def test_carousel_slide_writer_fallback_returns_five_slides(self) -> None:
        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}, clear=False):
            result = carousel_slide_writer.run(
                self._tmp,
                principle_key="contrapositive",
                archetype_key="preparedness_buyer",
                product={"name": "PowerFlex", "metrics": ["400W"]},
            )
        self.assertEqual(len(result["slides"]), 5)
        _, errors = validate_agent_output("carousel_slide_writer", result)
        self.assertEqual(errors, [])

    def test_visual_qa_reviewer_no_gemini_returns_default_accept(self) -> None:
        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}, clear=False):
            result = visual_qa_reviewer.run(self._tmp, image_path="", platform="facebook")
        self.assertTrue(result["acceptable"])

    def test_product_matcher_ranks_by_archetype_keywords(self) -> None:
        with patch("inventory_db.fetch_products", return_value=[
                {"id": "A", "name": "Solar Panel", "categories": ["solar"], "metrics": ["100W"]},
                {"id": "B", "name": "Power Bank", "categories": ["charger"], "metrics": ["20000mAh"]},
            ]), patch("inventory_db.init_inventory_db"):
            result = product_matcher.run(
                self._tmp,
                topic="daily commute charging",
                funnel_stage="ATTENTION",
                archetype_key="mobile_professional",
            )
        self.assertEqual(result["top_choice"]["product_id"], "B")

    def test_product_intelligence_persists_case_specific_dossier(self) -> None:
        product = {
            "id": "WFS-001",
            "sku": "WFS-001",
            "name": "Wosfer Micron Water Filter Straw",
            "categories": ["Water Filtration"],
            "metrics": ["0.1 micron filtration"],
            "fact_snippet": "Portable filter for emergency and outdoor water preparation.",
            "image_url": "https://example.com/filter.jpg",
        }
        result = product_intelligence.run(
            self._tmp,
            product=product,
            topic="building an emergency water kit",
            funnel_stage="EDUCATION",
            audience_segment="Prepared Buyer",
        )

        brief = result["product_brief"]
        self.assertEqual(brief["product_type"], "portable_water_filter")
        self.assertIn("water", brief["primary_pain_point"].lower())
        self.assertNotIn("must-run devices", result["sales_copy_seed"])
        self.assertTrue(os.path.exists(os.path.join(self._tmp, "product_briefs", "WFS-001.json")))
        _, errors = validate_agent_output("product_intelligence", result)
        self.assertEqual(errors, [])

    def test_product_intelligence_uses_primary_type_for_multifunction_product(self) -> None:
        brief = product_intelligence.build_product_brief(
            {
                "id": "CAMP-FAN-12K",
                "name": "3-in-1 Portable Camping Fan with 12000mAh Battery, LED Light & Power Bank",
                "categories": ["Power Banks", "Outdoors & Camping"],
                "metrics": ["12000mAh"],
            }
        )

        self.assertEqual(brief["product_type"], "portable_fan")
        self.assertIn("airflow", brief["core_benefits"][0])
        self.assertNotIn("portable charging backup", brief["product_summary"])

    def test_product_intelligence_prefers_sellable_item_over_broad_category(self) -> None:
        cases = [
            ({"id": "AF-SOLAR", "name": "Aferiy Solar Panels", "categories": ["Solar Generators", "Solar Panels"]}, "solar_panel"),
            ({"id": "SGL-BULB", "name": "Portable Solar-Powered Light Bulb", "categories": ["Portable Power"]}, "solar_light"),
            ({"id": "WOSFER-DH-C10", "name": "Wosfer Portable Water Purifier Bottle", "categories": ["Portable Water Filters"]}, "portable_water_filter"),
            ({"id": "BW-1500W-60AH", "name": "Black Warrior 1500W - Long Range Edition", "categories": ["Electric Bikes"]}, "electric_bike"),
            ({"id": "SOREIN-EB200", "name": "Sorein Modular Power System - EB 200 Extra Battery"}, "expansion_battery"),
            ({"id": "SM-PRO-2", "name": "SolarMax Pro 5kW-10kW - 2 SolarMax Pros"}, "power_station"),
            ({"id": "AF-P210", "name": "AFERIY AF-P210", "categories": ["Power Stations", "Solar Panels"]}, "power_station"),
            ({"id": "b7ad9dc40179", "name": "PowerCharge Pro - Black", "categories": []}, "power_bank"),
        ]

        for product, expected_type in cases:
            with self.subTest(product_id=product["id"]):
                brief = product_intelligence.build_product_brief(product)
                self.assertEqual(brief["product_type"], expected_type)
                self.assertNotEqual(brief["role"], "preparedness product")

    def test_product_intelligence_rebuilds_entire_catalog(self) -> None:
        products = [
            {"id": "PS-1", "name": "Home Power Station", "categories": ["Power Stations"], "metrics": ["1000Wh"]},
            {"id": "WF-1", "name": "Trail Water Filter Straw", "categories": ["Water Filtration"], "metrics": ["0.1 micron"]},
        ]
        with patch("inventory_db.fetch_products", return_value=products), patch("inventory_db.init_inventory_db"):
            result = product_intelligence.run(self._tmp, product_id="all")

        self.assertEqual(result["mode"], "catalog_rebuild")
        self.assertEqual(result["briefs_written"], 2)
        self.assertTrue(os.path.exists(os.path.join(self._tmp, "product_briefs", "PS-1.json")))
        self.assertTrue(os.path.exists(os.path.join(self._tmp, "product_briefs", "WF-1.json")))

    def test_brand_voice_drift_flags_banned_hits(self) -> None:
        os.makedirs(os.path.join(self._tmp, "marketing"), exist_ok=True)
        with open(os.path.join(self._tmp, "marketing", "founder_brand_manifesto.json"), "w", encoding="utf-8") as f:
            json.dump({"banned_phrases": ["cheap knockoff"], "positioning": "reliable backup power"}, f)
        _make_history(
            self._tmp,
            [
                {"post_id": "p1", "fb_caption": "This is not a cheap knockoff. Real backup power."},
                {"post_id": "p2", "fb_caption": "Reliable backup power for your family."},
            ],
        )
        result = brand_voice_drift.run(self._tmp)
        self.assertGreater(result["total_banned_hits"], 0)
        self.assertIn(result["drift_status"], ("green", "yellow", "red"))

    def test_brand_voice_drift_reads_current_nested_manifesto_shape(self) -> None:
        os.makedirs(os.path.join(self._tmp, "marketing"), exist_ok=True)
        with open(os.path.join(self._tmp, "marketing", "founder_brand_manifesto.json"), "w", encoding="utf-8") as f:
            json.dump(
                {
                    "business_profile": {"positioning": "preparedness-first portable power"},
                    "guardrails": {"disallowed_claim_patterns": ["fear-only manipulation"]},
                },
                f,
            )
        _make_history(self._tmp, [{"post_id": "p1", "fb_caption": "Portable power without fear-only manipulation."}])

        result = brand_voice_drift.run(self._tmp)

        self.assertEqual(result["banned_phrase_count"], 1)
        self.assertEqual(result["total_banned_hits"], 1)
        self.assertGreater(result["per_caption"][0]["positioning_overlap"], 0)

    def test_hashtag_intelligence_respects_platform_limits(self) -> None:
        result = hashtag_intelligence.run(
            self._tmp,
            archetype_key="preparedness_buyer",
            product={"name": "PowerFlex", "categories": ["power station"]},
        )
        tags = result["hashtags_by_platform"]
        self.assertLessEqual(len(tags["facebook"]), 4)
        self.assertGreaterEqual(len(tags["instagram"]), 4)
        self.assertLessEqual(len(tags["instagram"]), 15)
        self.assertLessEqual(len(tags["linkedin"]), 5)
        _, errors = validate_agent_output("hashtag_intelligence", result)
        self.assertEqual(errors, [])

    def test_alt_text_accessibility_fallback_returns_bounded_sentence(self) -> None:
        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}, clear=False):
            result = alt_text_accessibility.run(
                self._tmp,
                platform="instagram",
                product_name="PowerFlex",
                scene_prompt="Dim kitchen at dusk with a countertop candle",
            )
        self.assertGreater(len(result["alt_text"]), 20)
        self.assertLessEqual(len(result["alt_text"]), 280)

    def test_posting_time_optimizer_produces_recommendations(self) -> None:
        _make_history(
            self._tmp,
            [
                {
                    "post_id": f"p{i}",
                    "published_at": "2026-08-05T14:00:00+00:00",
                    "engagement_metrics": {
                        "facebook": {"total_interactions": 5 + i},
                        "instagram": {"total_interactions": 3 + i},
                    },
                }
                for i in range(3)
            ],
        )
        result = posting_time_optimizer.run(self._tmp)
        self.assertGreater(len(result["recommendations_utc"]["facebook"]), 0)

    def test_ab_variant_orchestrator_creates_variants(self) -> None:
        _make_history(
            self._tmp,
            [
                {
                    "post_id": "p1",
                    "status": "success",
                    "logical_emotional_strategy": {
                        "principle_key": "contrapositive",
                        "archetype_key": "preparedness_buyer",
                    },
                    "product_id": "prod_1",
                    "topic": "outage prep",
                }
            ],
        )
        result = ab_variant_orchestrator.run(self._tmp, count=1)
        self.assertEqual(result["created"], 1)
        self.assertEqual(result["experiments"][0]["swap_dimension"], "principle")

    def test_crisis_relevance_no_feeds_is_inactive(self) -> None:
        with patch.dict(os.environ, {"CRISIS_FEED_URLS": ""}, clear=False):
            result = crisis_relevance.run(self._tmp)
        self.assertFalse(result["active"])
        self.assertEqual(result["events_found"], 0)

    def test_cross_post_recycler_requires_engagement_and_cooldown(self) -> None:
        _make_history(
            self._tmp,
            [
                {
                    "post_id": "old_high",
                    "published_at": "2026-06-01T00:00:00+00:00",
                    "logical_emotional_strategy": {"archetype_key": "preparedness_buyer"},
                    "engagement_metrics": {
                        "facebook": {"total_interactions": 25},
                        "instagram": {"total_interactions": 25},
                    },
                    "product_id": "prod_1",
                    "topic": "outage prep",
                },
                {
                    "post_id": "yesterday",
                    "published_at": "2026-08-09T00:00:00+00:00",
                    "logical_emotional_strategy": {"archetype_key": "preparedness_buyer"},
                    "engagement_metrics": {"facebook": {"total_interactions": 50}},
                },
            ],
        )
        result = cross_post_recycler.run(self._tmp)
        picks = result["picks"]
        self.assertTrue(all(p["source_post_id"] != "yesterday" for p in picks))

    def test_retention_dry_run_reports_but_deletes_nothing(self) -> None:
        os.makedirs(os.path.join(self._tmp, "marketing"), exist_ok=True)
        for name in ("brand_profile_20260101T000000Z.json", "brand_profile_20260101T010000Z.json", "brand_profile_20260101T020000Z.json"):
            with open(os.path.join(self._tmp, "marketing", name), "w", encoding="utf-8") as f:
                f.write("{}")
        result = retention.run(self._tmp, dry_run=True)
        marketing_result = next(r for r in result["results"] if r["folder"].endswith("marketing"))
        self.assertTrue(marketing_result.get("dry_run"))
        for name in os.listdir(os.path.join(self._tmp, "marketing")):
            self.assertTrue(os.path.exists(os.path.join(self._tmp, "marketing", name)))


if __name__ == "__main__":
    unittest.main()
