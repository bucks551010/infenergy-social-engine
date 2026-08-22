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
    _product_copy_profile,
)
from run_engine import _live_visual_gate_errors  # noqa: E402
from social_visuals import (  # noqa: E402
    _build_gemini_image_prompt,
    _gemini_plate_quality,
    _has_scanline_corruption,
    _normalize_reference_image,
    generate_visuals,
    normalize_brand_text,
    review_rendered_visual,
)


class PublisherVisualTests(unittest.TestCase):
    def test_normalize_brand_text(self) -> None:
        text = "INF Energy Power helps INF Energy customers. #InfEnergyPower"
        normalized = normalize_brand_text(text)
        self.assertNotIn("INF Energy", normalized)
        self.assertIn("Infenergy Power", normalized)
        self.assertIn("#InfenergyPower", normalized)

    def test_gemini_prompt_includes_verbatim_ad_copy(self) -> None:
        prompt = _build_gemini_image_prompt(
            {
                "funnel_stage": "TRUST",
                "product_name": "PowerFlex 2000",
                "product_metrics": ["2000 Wh"],
                "selected_hook": "Keep essentials running",
                "selected_cta": "Compare the verified specs.",
            },
            "instagram",
            {"gemini_image_prompt": "Add badges, labels, and a fake product render."},
        )
        self.assertIn("left 42% and bottom 16%", prompt)
        self.assertIn("Render exactly this on-image copy", prompt)
        self.assertIn("Compare the verified specs.", prompt)
        self.assertIn("2000 Wh", prompt)
        self.assertIn("do not invent a different or generic device", prompt)
        self.assertNotIn("ABSOLUTE EXCLUSIONS", prompt)
        self.assertIn("subordinate to every rule", prompt)

    def test_gemini_plate_quality_rejects_wrong_aspect_ratio(self) -> None:
        from PIL import Image

        wrong_ratio = Image.new("RGB", (1200, 400), "#202830")
        accepted, reasons = _gemini_plate_quality(wrong_ratio, "instagram")
        self.assertFalse(accepted)
        self.assertIn("aspect_ratio", reasons)

        correct_ratio = Image.new("RGB", (1200, 1200), "#334455")
        accepted, reasons = _gemini_plate_quality(correct_ratio, "instagram")
        self.assertNotIn("aspect_ratio", reasons)

    def test_corrupted_scanlines_are_rejected_at_generation_and_artifact_qa(self) -> None:
        from PIL import Image, ImageDraw

        image = Image.new("RGB", (1200, 1200), "#263746")
        draw = ImageDraw.Draw(image)
        for y, color in ((200, "#ff0000"), (400, "#00ff00"), (600, "#0000ff")):
            draw.rectangle((700, y, 1199, y + 12), fill=color)
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as image_file:
            image_path = image_file.name
        try:
            image.save(image_path, format="PNG")
            accepted, reasons = _gemini_plate_quality(image, "instagram")
            review = review_rendered_visual(image_path, "instagram")
        finally:
            os.unlink(image_path)

        self.assertTrue(_has_scanline_corruption(image))
        self.assertFalse(accepted)
        self.assertIn("scanline_corruption", reasons)
        self.assertEqual(review["verdict"], "REGENERATE_VISUAL")
        self.assertIn("rendered_scanline_corruption", review["issues"])

    def test_instagram_strict_gemini_mode_never_uses_catalog_fallback(self) -> None:
        with patch.dict(
            os.environ,
            {
                "LIVE_REQUIRE_GEMINI_VISUAL": "true",
                "IG_VALIDATE_IMAGE_URLS": "false",
            },
            clear=False,
        ):
            result = publish_instagram.publish(
                {
                    "ig_caption": "Caption",
                    "generated_visuals": {},
                    "product_image_url": "https://example.com/catalog.png",
                }
            )

        self.assertEqual(result["id"], "skipped")
        self.assertEqual(result["reason"], "required_gemini_visual_unavailable")

    def test_instagram_strict_package_rejects_untracked_hosted_image(self) -> None:
        with patch.dict(os.environ, {"IG_VALIDATE_IMAGE_URLS": "false"}, clear=False):
            result = publish_instagram.publish(
                {
                    "ig_caption": "Caption",
                    "gemini_generation": {"strict_provider": True, "assets": []},
                    "primary_publish_image_url": "https://example.com/untracked.png",
                }
            )

        self.assertEqual(result["id"], "skipped")
        self.assertEqual(result["reason"], "required_gemini_visual_unavailable")

    def test_instagram_strict_package_fails_closed_on_public_url_preflight(self) -> None:
        public_url = "https://example.com/media/reviewed.png"
        with patch.dict(os.environ, {"IG_VALIDATE_IMAGE_URLS": "true"}, clear=False), patch.object(
            publish_instagram, "_is_reachable_image_url", return_value=False
        ):
            result = publish_instagram.publish(
                {
                    "ig_caption": "Caption",
                    "gemini_generation": {
                        "strict_provider": True,
                        "assets": [{"render_engine": "gemini", "public_url": public_url}],
                    },
                    "primary_publish_image_url": public_url,
                }
            )

        self.assertEqual(result["id"], "skipped")
        self.assertEqual(result["reason"], "strict_gemini_public_url_preflight_failed")

    def test_facebook_strict_package_rejects_corrupted_local_artifact(self) -> None:
        with patch.object(
            publish_facebook,
            "review_rendered_visual",
            return_value={"verdict": "REGENERATE_VISUAL", "issues": ["rendered_scanline_corruption"]},
        ):
            with self.assertRaisesRegex(RuntimeError, "facebook_strict_gemini_artifact_invalid"):
                publish_facebook.publish(
                    {
                        "fb_caption": "Caption",
                        "gemini_generation": {"strict_provider": True},
                        "generated_visuals": {"facebook": "missing.png"},
                    },
                    "https://example.com",
                )

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

    def test_facebook_attaches_generated_photo_to_feed_post(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
            tmp.write(b"fakepng")
            image_path = tmp.name
        try:
            upload_response = Mock(ok=True)
            upload_response.json.return_value = {"id": "photo_123"}
            feed_response = Mock(ok=True)
            feed_response.json.return_value = {"id": "page123_feed_456"}

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
                side_effect=[upload_response, feed_response],
            ) as mock_post:
                result = publish_facebook.publish(
                    {
                        "fb_caption": "Caption text",
                        "generated_visuals": {"facebook": image_path},
                    },
                    "https://example.com",
                    dry_run=False,
                )

            self.assertEqual(result["id"], "page123_feed_456")
            self.assertEqual(mock_post.call_count, 2)
            self.assertIn("/photos", mock_post.call_args_list[0].args[0])
            self.assertEqual(mock_post.call_args_list[0].kwargs["data"]["published"], "false")
            self.assertIn("/feed", mock_post.call_args_list[1].args[0])
            self.assertIn('"media_fbid": "photo_123"', mock_post.call_args_list[1].kwargs["data"]["attached_media"])
        finally:
            try:
                os.remove(image_path)
            except OSError:
                pass

    def test_facebook_attaches_hosted_photo_to_feed_post(self) -> None:
        upload_response = Mock(ok=True)
        upload_response.json.return_value = {"id": "photo_url_123"}
        feed_response = Mock(ok=True)
        feed_response.json.return_value = {"id": "page123_feed_789"}

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
            side_effect=[upload_response, feed_response],
        ) as mock_post:
            result = publish_facebook.publish(
                {
                    "fb_caption": "Caption text",
                    "product_image_url": "https://example.com/product.png",
                },
                "https://example.com",
                dry_run=False,
            )

        self.assertEqual(result["id"], "page123_feed_789")
        self.assertEqual(mock_post.call_count, 2)
        self.assertIn("/photos", mock_post.call_args_list[0].args[0])
        self.assertEqual(mock_post.call_args_list[0].kwargs["data"]["published"], "false")
        self.assertEqual(mock_post.call_args_list[0].kwargs["data"]["url"], "https://example.com/product.png")
        self.assertIn("/feed", mock_post.call_args_list[1].args[0])
        self.assertIn('"media_fbid": "photo_url_123"', mock_post.call_args_list[1].kwargs["data"]["attached_media"])

    def test_facebook_attaches_all_carousel_slides(self) -> None:
        paths = []
        try:
            for _ in range(4):
                tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
                tmp.write(b"fakepng")
                tmp.close()
                paths.append(tmp.name)
            uploads = []
            for index in range(4):
                response = Mock(ok=True)
                response.json.return_value = {"id": f"photo_{index}"}
                uploads.append(response)
            feed = Mock(ok=True)
            feed.json.return_value = {"id": "carousel_post"}
            with patch.dict(os.environ, {"META_PAGE_ID": "page123", "META_PAGE_ACCESS_TOKEN": "token123"}, clear=False), patch.object(
                publish_facebook, "_resolve_page_access_token", return_value="page_token"
            ), patch.object(publish_facebook.requests, "post", side_effect=[*uploads, feed]) as mock_post:
                result = publish_facebook.publish(
                    {
                        "fb_caption": "Carousel caption",
                        "carousel_assets": [{"local_path": path} for path in paths],
                        "generated_visuals": {"facebook": paths[0]},
                    },
                    "",
                )
            attached = mock_post.call_args_list[-1].kwargs["data"]["attached_media"]
            self.assertEqual(result["id"], "carousel_post")
            self.assertEqual(mock_post.call_count, 5)
            self.assertEqual(attached.count("media_fbid"), 4)
        finally:
            for path in paths:
                try:
                    os.remove(path)
                except OSError:
                    pass

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

    def test_instagram_bounds_caption_before_creating_media(self) -> None:
        create_response = Mock(ok=True)
        create_response.json.return_value = {"id": "container_123"}
        publish_response = Mock(ok=True)
        publish_response.json.return_value = {"id": "instagram_456"}
        long_caption = "Useful preparation advice " * 150

        with patch.dict(
            os.environ,
            {
                "META_IG_USER_ID": "ig123",
                "META_PAGE_ACCESS_TOKEN": "token123",
                "IG_VALIDATE_IMAGE_URLS": "false",
            },
            clear=False,
        ), patch.object(publish_instagram, "_wait_for_media_container", return_value=(True, "finished")), patch.object(
            publish_instagram,
            "_post_with_retry",
            side_effect=[create_response, publish_response],
        ) as mock_post:
            result = publish_instagram.publish(
                {
                    "ig_caption": long_caption,
                    "product_image_url": "https://example.com/product.png",
                }
            )

        self.assertEqual(result["id"], "instagram_456")
        caption = mock_post.call_args_list[0].args[1]["caption"]
        self.assertLessEqual(len(caption), publish_instagram.INSTAGRAM_CAPTION_MAX_LENGTH)
        self.assertTrue(caption.endswith("..."))

    def test_instagram_creates_native_carousel(self) -> None:
        responses = []
        for index in range(4):
            child = Mock(ok=True)
            child.json.return_value = {"id": f"child_{index}"}
            responses.append(child)
        parent = Mock(ok=True)
        parent.json.return_value = {"id": "parent_1"}
        published = Mock(ok=True)
        published.json.return_value = {"id": "instagram_carousel_1"}
        with patch.dict(
            os.environ,
            {"META_IG_USER_ID": "ig123", "META_PAGE_ACCESS_TOKEN": "token123", "IG_VALIDATE_IMAGE_URLS": "false"},
            clear=False,
        ), patch.object(publish_instagram, "_wait_for_media_container", return_value=(True, "finished")), patch.object(
            publish_instagram, "_post_with_retry", side_effect=[*responses, parent, published]
        ) as mock_post:
            result = publish_instagram.publish(
                {
                    "ig_caption": "Carousel caption",
                    "primary_publish_image_url": "https://example.com/slide-1.png",
                    "carousel_assets": [
                        {"public_url": f"https://example.com/slide-{index}.png"} for index in range(1, 5)
                    ],
                }
            )
        parent_data = mock_post.call_args_list[4].args[1]
        self.assertEqual(result["id"], "instagram_carousel_1")
        self.assertEqual(parent_data["media_type"], "CAROUSEL")
        self.assertEqual(parent_data["children"], "child_0,child_1,child_2,child_3")

    def test_generate_visuals_has_no_fallback_when_gemini_unavailable(self) -> None:
        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}, clear=False):
            visuals = generate_visuals(
                {
                    "post_id": "unit_test_card_no_fallback",
                    "funnel_stage": "TRUST",
                    "selected_hook": "Why energy resilience needs a better design standard",
                    "topic": "A stronger branded social card",
                    "selected_cta": "Review the full system.",
                    "product_name": "PowerFlex",
                    "product_image_url": "",
                }
            )
        self.assertNotIn("facebook", visuals)
        self.assertNotIn("instagram", visuals)
        self.assertNotIn("linkedin", visuals)
        self.assertNotIn("facebook_html", visuals)
        self.assertEqual(visuals["render_engines"]["facebook"], "failed")
        self.assertEqual(visuals["gemini_available"], "false")
        render = visuals["visual_generation"]["facebook"]
        self.assertTrue(render["visual_generation_attempted"])
        self.assertEqual(render["generation_status"], "failed")
        self.assertEqual(render["provider_error_class"], "AUTH_ERROR")
        self.assertEqual(render["artifact_path"], "")
        self.assertFalse(render["artifact_exists"])

    def test_generate_visuals_uses_approved_product_photo_when_gemini_fails(self) -> None:
        from PIL import Image

        with tempfile.TemporaryDirectory() as temp_dir:
            source_path = os.path.join(temp_dir, "product.png")
            Image.new("RGB", (800, 600), "#223344").save(source_path, format="PNG")
            with patch.dict(os.environ, {"GEMINI_API_KEY": ""}, clear=False), patch("social_visuals.VISUAL_DIR", temp_dir):
                visuals = generate_visuals(
                    {
                        "post_id": "unit_test_product_photo_fallback",
                        "product_image_url": source_path,
                    }
                )

            self.assertEqual(visuals["render_engines"]["instagram"], "approved_product_photo")
            self.assertIn("instagram", visuals)
            self.assertEqual(
                visuals["visual_generation"]["instagram"].get("fallback_source"),
                "approved_product_photo",
            )
            self.assertEqual(visuals["artifact_reviews"]["instagram"]["verdict"], "PASS")

    def test_live_visual_gate_rejects_missing_product_source_and_overlay(self) -> None:
        content = {
            "product_id": "SFT-20K",
            "generated_visuals": {
                "facebook": "card.png",
                "render_engines": {"facebook": "local_render"},
                "product_overlay_applied": {"facebook": False},
                "product_specific_source_present": "false",
            }
        }
        errors = _live_visual_gate_errors(content, {"facebook": True}, dry_run=False)
        self.assertIn("product_specific_image_source_missing", errors)
        self.assertIn("facebook_product_overlay_missing", errors)

    def test_live_visual_gate_accepts_approved_product_photo_fallback(self) -> None:
        content = {
            "product_id": "SFT-20K",
            "generated_visuals": {
                "facebook": "product-photo.png",
                "render_engines": {"facebook": "approved_product_photo"},
                "product_overlay_applied": {"facebook": True},
                "product_specific_source_present": "true",
            },
        }

        assert _live_visual_gate_errors(content, {"facebook": True}, dry_run=False) == []

    def test_live_visual_gate_skips_product_checks_when_no_product_anchored(self) -> None:
        # Educational/pillar content with no product_id must not be blocked by
        # product-specific image requirements — those only apply when a product
        # is actually anchored to the post.
        content = {
            "generated_visuals": {
                "facebook": "card.png",
                "render_engines": {"facebook": "local_render"},
                "product_overlay_applied": {"facebook": False},
                "product_specific_source_present": "false",
            }
        }
        errors = _live_visual_gate_errors(content, {"facebook": True}, dry_run=False)
        self.assertNotIn("product_specific_image_source_missing", errors)
        self.assertNotIn("facebook_product_overlay_missing", errors)
        self.assertEqual(errors, [])

    def test_generate_visuals_uses_approved_reference_for_non_product_fallback(self) -> None:
        from PIL import Image

        with tempfile.TemporaryDirectory() as temp_dir:
            source_path = os.path.join(temp_dir, "editorial.png")
            Image.new("RGB", (1200, 1200), "#36505f").save(source_path, format="PNG")
            context = {"references": [{"reference_url": source_path}], "settings": {}}
            with patch.dict(os.environ, {"GEMINI_API_KEY": ""}, clear=False), \
                    patch("social_visuals.VISUAL_DIR", temp_dir), \
                    patch("social_visuals._load_visual_repo_context", return_value=context):
                visuals = generate_visuals({"post_id": "organic-reference", "product_id": None})

            self.assertEqual(visuals["render_engines"]["facebook"], "approved_reference_image")
            self.assertEqual(visuals["visual_generation"]["facebook"]["fallback_source"], "approved_reference_image")
            self.assertEqual(visuals["artifact_reviews"]["facebook"]["verdict"], "PASS")

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
            self.assertNotIn("Use only published", caption)

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

    def test_multifunction_fan_is_not_classified_as_a_power_bank(self) -> None:
        product = {
            "name": "3-in-1 Portable Camping Fan with 12000mAh Battery, LED Light & Power Bank",
            "sku": "CAMP-FAN-12K",
            "sale_price": "39.99",
            "metrics": [],
            "categories": ["Camping Gear", "Portable Power"],
        }
        content = _build_fallback_content("midday", "outage readiness", product, {}, {})

        for key in ("fb_caption", "ig_caption", "li_text"):
            caption = content[key]
            self.assertIn("airflow", caption.lower())
            self.assertIn("runtime", caption.lower())
            self.assertNotIn("cheap power bank", caption.lower())
            self.assertNotIn("top 3 must-run devices", caption)
        self.assertIn("#PortableFan", content["fb_caption"])
        self.assertLessEqual(len(content["fb_caption"]), 700)

    def test_power_station_evidence_wins_over_solar_panel_category(self) -> None:
        profile = _product_copy_profile(
            {
                "name": "AFERIY AF-P210",
                "categories": ["Emergency Power", "Power Stations", "Solar Panels"],
                "metrics": ["1.5 hours", "120V", "100W"],
                "fact_snippet": "2400W home backup powerhouse with a 2048Wh battery and pure sine wave inverter.",
            }
        )

        self.assertEqual(profile["role"], "backup power station")
        self.assertIn("runtime", profile["proof_intro"])

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
