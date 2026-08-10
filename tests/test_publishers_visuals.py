from __future__ import annotations

import os
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = os.path.dirname(os.path.dirname(__file__))
SCRIPTS = os.path.join(ROOT, "scripts")
sys.path.insert(0, ROOT)
sys.path.insert(0, SCRIPTS)

import publish_facebook  # noqa: E402
import publish_instagram  # noqa: E402
import publish_linkedin  # noqa: E402
from generate_posts import (  # noqa: E402
    _build_fallback_content,
    _enforce_conversion_caption,
    _enforce_product_led_copy,
    _enforce_product_sales_platform_copy,
    _model_caption_overrides,
)
from run_engine import _live_visual_gate_errors  # noqa: E402
from social_visuals import (  # noqa: E402
    _build_gemini_image_prompt,
    _gemini_plate_quality,
    _normalize_reference_image,
    generate_visuals,
    normalize_brand_text,
)


class PublisherVisualTests(unittest.TestCase):
    def test_normalize_brand_text(self) -> None:
        text = "INF Energy Power helps INF Energy customers. #InfEnergyPower"
        normalized = normalize_brand_text(text)
        self.assertNotIn("INF Energy", normalized)
        self.assertIn("Infenergy Power", normalized)
        self.assertIn("#InfenergyPower", normalized)

    def test_gemini_prompt_is_a_textless_platform_scene_contract(self) -> None:
        prompt = _build_gemini_image_prompt(
            {
                "funnel_stage": "TRUST",
                "product_name": "PowerFlex 2000",
                "product_metrics": ["2000 Wh"],
                "selected_hook": "Keep essentials running",
            },
            "instagram",
            {"gemini_image_prompt": "Add badges, labels, and a fake product render."},
        )
        self.assertIn("left 42% and bottom 16%", prompt)
        self.assertIn("ABSOLUTE EXCLUSIONS", prompt)
        self.assertIn("no text, letters, numerals", prompt)
        self.assertIn("subordinate to every rule", prompt)

    def test_gemini_plate_quality_rejects_wrong_ratio_and_busy_copy_zone(self) -> None:
        from PIL import Image

        wrong_ratio = Image.new("RGB", (1200, 400), "#202830")
        accepted, reasons = _gemini_plate_quality(wrong_ratio, "instagram")
        self.assertFalse(accepted)
        self.assertIn("aspect_ratio", reasons)

        busy = Image.new("RGB", (1200, 1200), "black")
        for x in range(0, 528, 8):
            for y in range(0, 1200, 8):
                if (x // 8 + y // 8) % 2:
                    busy.paste("white", (x, y, x + 8, y + 8))
        accepted, reasons = _gemini_plate_quality(busy, "instagram")
        self.assertFalse(accepted)
        self.assertIn("busy_copy_zone", reasons)

    def test_style_reference_must_decode_as_an_image(self) -> None:
        from PIL import Image
        from io import BytesIO

        self.assertEqual(_normalize_reference_image(b"<html>not an image</html>"), (b"", ""))
        source = BytesIO()
        Image.new("RGB", (80, 60), "#223344").save(source, format="PNG")
        normalized, mime_type = _normalize_reference_image(source.getvalue())
        self.assertGreater(len(normalized), 0)
        self.assertEqual(mime_type, "image/jpeg")

    def test_linkedin_prefers_explicit_organization_urn(self) -> None:
        with patch.dict(os.environ, {"LINKEDIN_ORGANIZATION_URN": "urn:li:organization:12345"}, clear=False):
            author = publish_linkedin._resolve_author_urn()
        self.assertEqual(author, "urn:li:organization:12345")

    def test_facebook_uses_photo_endpoint_when_visual_exists(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp.write(b"fakepng")
            image_path = tmp.name
        try:
            response = Mock()
            response.ok = True
            response.json.return_value = {"id": "photo_123"}
            response.raise_for_status.return_value = None

            with patch.dict(
                os.environ,
                {
                    "META_PAGE_ID": "page123",
                    "META_PAGE_ACCESS_TOKEN": "token123",
                },
                clear=False,
            ), patch.object(publish_facebook, "_resolve_page_access_token", return_value="page_token"), patch.object(
                publish_facebook.requests,
                "post",
                return_value=response,
            ) as mock_post:
                result = publish_facebook.publish(
                    {
                        "fb_caption": "Caption text",
                        "generated_visuals": {"facebook": image_path},
                    },
                    "https://example.com",
                    dry_run=False,
                )

            self.assertEqual(result["id"], "photo_123")
            self.assertIn("/photos", mock_post.call_args.args[0])
        finally:
            try:
                os.remove(image_path)
            except OSError:
                pass

    def test_facebook_uses_photo_endpoint_with_product_image_url(self) -> None:
        response = Mock()
        response.ok = True
        response.json.return_value = {"id": "photo_url_123"}
        response.raise_for_status.return_value = None

        with patch.dict(
            os.environ,
            {
                "META_PAGE_ID": "page123",
                "META_PAGE_ACCESS_TOKEN": "token123",
                "FB_REQUIRE_IMAGE": "true",
            },
            clear=False,
        ), patch.object(publish_facebook, "_resolve_page_access_token", return_value="page_token"), patch.object(
            publish_facebook.requests,
            "post",
            return_value=response,
        ) as mock_post:
            result = publish_facebook.publish(
                {
                    "fb_caption": "Caption text",
                    "product_image_url": "https://example.com/product.png",
                },
                "https://example.com",
                dry_run=False,
            )

        self.assertEqual(result["id"], "photo_url_123")
        self.assertIn("/photos", mock_post.call_args.args[0])

    def test_facebook_raises_when_image_required_but_missing(self) -> None:
        with patch.dict(
            os.environ,
            {
                "META_PAGE_ID": "page123",
                "META_PAGE_ACCESS_TOKEN": "token123",
                "FB_REQUIRE_IMAGE": "true",
            },
            clear=False,
        ), patch.object(publish_facebook, "_resolve_page_access_token", return_value="page_token"):
            with self.assertRaises(RuntimeError):
                publish_facebook.publish(
                    {
                        "fb_caption": "Caption text",
                        "product_image_url": "",
                        "generated_visuals": {},
                    },
                    "https://example.com",
                    dry_run=False,
                )

    def test_generate_visuals_emits_png_and_html_assets(self) -> None:
        visuals = generate_visuals(
            {
                "post_id": "unit_test_card",
                "funnel_stage": "TRUST",
                "selected_hook": "Why energy resilience needs a better design standard",
                "topic": "A stronger branded social card",
                "selected_cta": "Review the full system.",
                "product_name": "PowerFlex",
                "product_image_url": "",
            }
        )
        self.assertIn("facebook", visuals)
        self.assertIn("instagram", visuals)
        self.assertIn("linkedin", visuals)
        self.assertIn("facebook_html", visuals)
        self.assertTrue(os.path.exists(visuals["facebook"]))
        self.assertTrue(os.path.exists(visuals["facebook_html"]))

    def test_live_visual_gate_rejects_local_render_and_missing_product(self) -> None:
        content = {
            "generated_visuals": {
                "facebook": "card.png",
                "render_engines": {"facebook": "local_render"},
                "product_overlay_applied": {"facebook": False},
                "product_specific_source_present": "false",
            }
        }
        errors = _live_visual_gate_errors(content, {"facebook": True}, dry_run=False)
        self.assertIn("product_specific_image_source_missing", errors)
        self.assertIn("facebook_visual_not_gemini", errors)
        self.assertIn("facebook_product_overlay_missing", errors)

    def test_live_visual_gate_accepts_gemini_product_composite(self) -> None:
        content = {
            "generated_visuals": {
                "facebook": "card.png",
                "instagram": "card.png",
                "render_engines": {"facebook": "gemini", "instagram": "gemini"},
                "product_overlay_applied": {"facebook": True, "instagram": True},
                "product_specific_source_present": "true",
            }
        }
        errors = _live_visual_gate_errors(
            content,
            {"facebook": True, "instagram": True, "linkedin": False},
            dry_run=False,
        )
        self.assertEqual(errors, [])

    def test_model_platform_captions_are_preserved_for_packaging(self) -> None:
        overrides = _model_caption_overrides(
            {
                "fb_caption": "Facebook copy written for this product.",
                "ig_caption": "Instagram copy written for this product.",
                "li_text": "LinkedIn copy written for this product.",
                "selected_cta": "Compare the verified specifications.",
            }
        )
        self.assertEqual(overrides["facebook"]["caption"], "Facebook copy written for this product.")
        self.assertEqual(overrides["instagram"]["caption"], "Instagram copy written for this product.")
        self.assertEqual(overrides["linkedin"]["caption"], "LinkedIn copy written for this product.")

    def test_product_copy_guard_preserves_substantive_model_copy(self) -> None:
        product = {"name": "HoneyVolt Slim Power Bank", "metrics": ["10,000 mAh"]}
        original = {
            "fb_caption": "HoneyVolt Slim Power Bank keeps your phone available through a long travel day without turning preparedness into a lecture. Compare the published capacity before buying.",
            "ig_caption": "HoneyVolt Slim Power Bank belongs in the bag you already carry. Check the published capacity, charge before leaving, and keep your phone ready when outlets disappear.",
            "li_text": "HoneyVolt Slim Power Bank gives mobile teams a simple layer of charging continuity. Review its published capacity against the devices employees actually carry before standardizing a kit.",
        }
        content = dict(original)
        _enforce_product_sales_platform_copy(content, product, {})
        self.assertEqual(content, original)

    def test_conversion_guard_does_not_append_boilerplate_to_substantive_copy(self) -> None:
        caption = (
            "HoneyVolt Slim Power Bank belongs in the bag you already carry. "
            "Check its published capacity against your phone, charge it before leaving, "
            "and keep one dependable backup close when outlets disappear."
        )
        result = _enforce_conversion_caption(
            caption,
            {
                "pain_point": "Dead batteries expose weak preparation.",
                "proof_anchor": "Use published specifications to validate fit.",
                "first_step": "Comment with your top three devices.",
                "copy_generation_source": "gemini",
            },
            platform="facebook",
        )
        self.assertEqual(result, caption)

        fallback_result = _enforce_conversion_caption(
            caption,
            {
                "pain_point": "Dead batteries expose weak preparation.",
                "proof_anchor": "Use published specifications to validate fit.",
                "first_step": "Comment with your top three devices.",
                "copy_generation_source": "deterministic_fallback",
            },
            platform="facebook",
        )
        self.assertEqual(fallback_result, caption)

    def test_fallback_platform_copy_stays_concise_and_avoids_inventory_prefix(self) -> None:
        product = {
            "name": "SolarFlex Titan 20K",
            "sku": "SFT-20K",
            "sale_price": "69.99",
            "metrics": ["20,000mAh", "20W", "18W"],
            "categories": ["Emergency Power", "Outdoors & Camping"],
            "fact_snippet": "SolarFlex Titan 20K: Infinite Power, On The Go Harness the power of the sun.",
        }
        talking_point = {
            "pain_point": "A dead phone during an outage can cut off weather alerts and family check-ins.",
            "proof_anchor": "Compare capacity and charging output with the devices you rely on.",
            "first_step": "Review the product details and confirm it fits your emergency kit.",
        }
        content = _build_fallback_content("midday", "outage readiness", product, {}, talking_point)
        _enforce_product_led_copy(content, product)

        for key in ("fb_caption", "ig_caption", "li_text"):
            caption = content[key]
            self.assertIn(product["name"], caption)
            self.assertLessEqual(len(caption), 700)
            self.assertNotIn("Featured product:", caption)
            self.assertNotIn("Key specs:", caption)
            self.assertNotIn("to keeps", caption)

    def test_water_filter_fallback_copy_uses_water_domain_language(self) -> None:
        product = {
            "name": "Wosfer Micron Water Filter Straw",
            "sku": "WFS-001",
            "sale_price": "24.99",
            "metrics": ["28mm", "30mm"],
            "categories": ["Water Filtration"],
        }
        talking_point = {
            "pain_point": "Your backup power setup cannot run what matters most.",
            "proof_anchor": "Use 28mm and 30mm to validate fit before buying.",
            "first_step": "Comment with your top 3 must-run devices.",
        }
        content = _build_fallback_content("midday", "outage readiness", product, {}, talking_point)

        for key in ("fb_caption", "ig_caption", "li_text"):
            caption = content[key]
            self.assertIn("water", caption.lower())
            self.assertNotIn("must-run devices", caption)
            self.assertNotIn("backup power", caption.lower())
            self.assertNotIn("Use 28mm and 30mm", caption)
        self.assertIn("#WaterFiltration", content["fb_caption"])
        self.assertIn("#WaterFiltration", content["ig_caption"])

    def test_instagram_prefers_generated_visual_upload(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp.write(b"fakepng")
            image_path = tmp.name
        try:
            first = Mock()
            first.ok = True
            first.json.return_value = {"id": "creation_123"}
            first.raise_for_status.return_value = None
            second = Mock()
            second.ok = True
            second.json.return_value = {"id": "ig_123"}
            second.raise_for_status.return_value = None

            with patch.dict(
                os.environ,
                {
                    "META_IG_USER_ID": "ig_user_1",
                    "META_PAGE_ACCESS_TOKEN": "page_token_1",
                    "IG_VALIDATE_IMAGE_URLS": "false",
                },
                clear=False,
            ), patch.object(
                publish_instagram.publish_wordpress,
                "upload_media",
                return_value={"source_url": "https://example.com/generated.png"},
            ), patch.object(
                publish_instagram,
                "_post_with_retry",
                side_effect=[first, second],
            ) as mock_post, patch.object(
                publish_instagram,
                "_wait_for_media_container",
                return_value=(True, "finished"),
            ):
                result = publish_instagram.publish(
                    {
                        "ig_caption": "Caption text",
                        "generated_visuals": {"instagram": image_path},
                        "product_image_url": "https://example.com/fallback.png",
                    },
                    dry_run=False,
                )

            self.assertEqual(result["id"], "ig_123")
            self.assertEqual(mock_post.call_args_list[0].args[1]["image_url"], "https://example.com/generated.png")
        finally:
            try:
                os.remove(image_path)
            except OSError:
                pass


if __name__ == "__main__":
    unittest.main()
