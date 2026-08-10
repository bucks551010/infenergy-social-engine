from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import patch


ROOT = os.path.dirname(os.path.dirname(__file__))
SCRIPTS = os.path.join(ROOT, "scripts")
sys.path.insert(0, ROOT)
sys.path.insert(0, SCRIPTS)

from generate_posts import (  # noqa: E402
    _apply_logical_visual_strategy,
    _build_ai_image_prompt_bank,
    _build_post_components,
    _build_social_media_assets,
    _select_logical_emotional_strategy,
)
from social_visuals import _build_gemini_image_prompt, _headline_lockup  # noqa: E402
from social_engine.marketing_team.agents import audience_agent, copy_agent, creative_agent  # noqa: E402


class LogicalEmotionalFrameworkTests(unittest.TestCase):
    def test_stage_selects_each_formal_logic_principle(self) -> None:
        expected = {
            "ATTENTION": "contrapositive",
            "EDUCATION": "disjunctive_syllogism",
            "DESIRE": "double_implication",
            "TRUST": "symmetrical_equivalence",
            "CONVERSION": "implication_of_result",
        }
        product = {"name": "PowerFlex", "metrics": ["512 Wh"], "categories": ["portable power"]}
        for stage, principle_key in expected.items():
            with self.subTest(stage=stage):
                strategy = _select_logical_emotional_strategy(product, "Prepared families", stage)
                self.assertEqual(strategy["principle_key"], principle_key)
                self.assertIn("512 Wh", strategy["logic_bridge"])

    def test_product_signals_select_audience_archetype(self) -> None:
        mobile = _select_logical_emotional_strategy(
            {"name": "Slim Power Bank", "categories": ["chargers"]}, "Commuters", "ATTENTION"
        )
        outdoor = _select_logical_emotional_strategy(
            {"name": "Camp Power Kit", "categories": ["outdoor", "RV"]}, "Travelers", "ATTENTION"
        )
        self.assertEqual(mobile["archetype_key"], "mobile_professional")
        self.assertEqual(outdoor["archetype_key"], "outdoor_adventurer")

    def test_prompt_bank_has_three_textless_product_free_variants(self) -> None:
        product = {"name": "PowerFlex", "metrics": ["512 Wh"], "categories": ["portable power"]}
        strategy = _select_logical_emotional_strategy(product, "Prepared families", "CONVERSION")
        bank = _build_ai_image_prompt_bank(strategy, product)
        self.assertEqual(
            set(bank),
            {"lifestyle_aesthetic", "crisis_preparedness", "professional_everyday_carry"},
        )
        for prompt in bank.values():
            self.assertIn("Do not render any product", prompt)
            self.assertIn("text, letters, numerals", prompt)

        plan = _apply_logical_visual_strategy({"platform_overrides": {}}, strategy, product)
        self.assertEqual(plan["platform_overrides"]["facebook"]["prompt_variant"], "crisis_preparedness")
        self.assertEqual(plan["platform_overrides"]["instagram"]["prompt_variant"], "lifestyle_aesthetic")
        self.assertEqual(plan["platform_overrides"]["linkedin"]["prompt_variant"], "professional_everyday_carry")
        instagram_prompt = _build_gemini_image_prompt(
            {"product_name": "PowerFlex", "funnel_stage": "CONVERSION"}, "instagram", plan
        )
        self.assertIn("Instagram/Pinterest direction", instagram_prompt)

    def test_assigned_overlay_copy_takes_priority(self) -> None:
        headline, subline = _headline_lockup(
            {
                "product_name": "PowerFlex",
                "on_image_headline": "Reactive or ready?",
                "on_image_subline": "PowerFlex | 512 Wh",
            }
        )
        self.assertEqual(headline, "REACTIVE OR READY?")
        self.assertEqual(subline, "PowerFlex | 512 Wh")

    def test_social_asset_package_contains_all_three_assets(self) -> None:
        product = {"name": "PowerFlex", "metrics": ["512 Wh", "600 W"], "categories": ["portable power"]}
        strategy = _select_logical_emotional_strategy(product, "Prepared families", "EDUCATION")
        components = _build_post_components(
            "Portable power fit",
            "Choose by the real job",
            "Review the product details.",
            product,
            "EDUCATION",
            logical_strategy=strategy,
        )
        plan = _apply_logical_visual_strategy({"platform_overrides": {}}, strategy, product)
        posts = {
            "facebook": {"caption": "Proof-backed choice. #PortablePower"},
            "instagram": {"caption": "Proof-backed choice. #PortablePower #Prepared"},
            "linkedin": {"caption": "Proof-backed choice. #BusinessContinuity"},
        }
        assets = _build_social_media_assets(components, posts, plan)
        self.assertEqual(
            set(assets),
            {
                "asset_1_single_image_social_ads",
                "asset_2_carousel_campaign",
                "asset_3_ai_image_prompt_bank",
            },
        )
        self.assertEqual(len(assets["asset_2_carousel_campaign"]["slides"]), 5)
        self.assertEqual(len(assets["asset_3_ai_image_prompt_bank"]), 3)
        self.assertEqual(
            assets["asset_1_single_image_social_ads"]["instagram"]["hashtags"],
            ["#PortablePower", "#Prepared"],
        )

    def test_weekly_agents_expose_archetypes_logic_and_prompt_bank(self) -> None:
        profile = {"psychographics": {"objections": []}, "visual_identity": {}}
        audience = audience_agent(profile, {})
        self.assertEqual(
            {segment["archetype_id"] for segment in audience["segments"]},
            {"preparedness_buyer", "mobile_professional", "outdoor_adventurer"},
        )
        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}, clear=False):
            copy = copy_agent(profile, audience, {}, {})
        self.assertEqual(len(copy["logical_frameworks"]), 5)
        creative = creative_agent(profile, {}, copy)
        self.assertEqual(len(creative["image_prompt_bank"]), 3)
        self.assertTrue(all("no product, text" in prompt for prompt in creative["image_prompts"]))


if __name__ == "__main__":
    unittest.main()
