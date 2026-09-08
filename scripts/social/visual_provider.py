"""Visual provider interface for preview recipes and live Gemini images.

The abstract ``VisualProvider`` decouples the pipeline from any specific
image-generation SDK.  ``GeminiVisualProvider`` is the real provider
(delegates pixel generation to the already-proven ``social_visuals``
Gemini image pipeline, per §34 — don't reinvent what existing code does
well). ``TemplateRenderProvider`` is available for explicit preview tooling,
but live Gemini requests fail closed instead of substituting generic creative.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Protocol

import requests

from .creative_contracts import CANONICAL_ROUTES


@dataclass
class VisualResult:
    provider: str
    kind: str  # "generated_image" | "template_recipe" | "product_asset" | "none"
    prompt: str = ""
    negative_prompt: str = ""
    asset_path: str | None = None
    recipe: dict[str, Any] = field(default_factory=dict)
    provider_meta: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "provider": self.provider,
            "kind": self.kind,
            "prompt": self.prompt,
            "negative_prompt": self.negative_prompt,
            "asset_path": self.asset_path,
            "recipe": self.recipe,
            "provider_meta": self.provider_meta,
        }


class VisualProvider(Protocol):
    def generate(self, *, art_direction: dict[str, Any], positive_prompt: str, negative_prompt: str, platform: str) -> VisualResult:
        ...


# --- Template fallback provider --------------------------------------------


class TemplateRenderProvider:
    """Deterministic provider that returns a rendering recipe, not an image.

    Downstream code (e.g. an existing Pillow renderer) can execute the
    recipe.  This lets the pipeline run end-to-end without a network.
    """

    name = "template_render"

    def generate(
        self,
        *,
        art_direction: dict[str, Any],
        positive_prompt: str,
        negative_prompt: str,
        platform: str,
    ) -> VisualResult:
        recipe = {
            "template": art_direction.get("visual_format", "fact_card"),
            "primary_text": art_direction.get("visual_message", ""),
            "focal_point": art_direction.get("focal_point", ""),
            "layout_grammar": art_direction.get("layout_grammar", {}),
            "platform_interpretation": (art_direction.get("platform_interpretations", {}) or {}).get(platform.split("_", 1)[0], {}),
            "information_priority": art_direction.get("information_priority", {}),
            "benefit_translation": art_direction.get("benefit_translation", {}),
            "color_direction": art_direction.get("color_direction", ""),
            "safe_area": art_direction.get("text_safe_area", ""),
            "must_include": art_direction.get("must_include", []),
            "must_avoid": art_direction.get("must_avoid", []),
        }
        return VisualResult(
            provider=self.name,
            kind="template_recipe",
            prompt=positive_prompt,
            negative_prompt=negative_prompt,
            recipe=recipe,
            provider_meta={"platform": platform},
        )


# --- Real Gemini provider ----------------------------------------------------


class GeminiVisualProvider:
    """Generates the actual finished creative via Gemini.

    Delegates to ``social_visuals.generate_visuals`` (the same pipeline the
    legacy generator uses in production: prompt compilation, brand/product
    reference images, plate + semantic quality QA, retries). Provider failures
    are publication blockers because a template recipe is not a finished image.
    """

    name = "gemini"

    def generate(
        self,
        *,
        art_direction: dict[str, Any],
        positive_prompt: str,
        negative_prompt: str,
        platform: str,
    ) -> VisualResult:
        if not os.environ.get("GEMINI_API_KEY", "").strip():
            raise RuntimeError("gemini_visual_provider_unavailable:api_key_missing")
        try:
            try:
                import social_visuals  # type: ignore
            except ImportError:
                from scripts import social_visuals  # type: ignore
        except Exception as exc:
            raise RuntimeError(f"gemini_visual_provider_unavailable:{type(exc).__name__}") from exc

        layout = art_direction.get("layout_grammar", {}) or {}
        v5_direction = art_direction.get("v5_direction", {}) if isinstance(art_direction.get("v5_direction"), dict) else {}
        content = {
            "post_id": art_direction.get("post_id") or "preview",
            "topic": art_direction.get("primary_subject", ""),
            "selected_hook": art_direction.get("visual_message", ""),
            "selected_cta": art_direction.get("cta", ""),
            "product_name": art_direction.get("product_name", ""),
            "product_image_url": art_direction.get("product_image_url", ""),
            "on_image_headline": (v5_direction.get("text_overlay", {}) or {}).get("text", "") or art_direction.get("visual_message", ""),
            "layout_grammar": layout,
            "platform_interpretations": art_direction.get("platform_interpretations", {}),
            "information_priority": art_direction.get("information_priority", {}),
            "benefit_translation": art_direction.get("benefit_translation", {}),
            "art_direction": art_direction,
        }
        visual_plan = {
            "image_strategy": "gemini_generated",
            "v5_direction": v5_direction,
            "gemini_image_prompt": art_direction.get("v5_scene_prompt", positive_prompt),
            "layout_grammar": layout,
            "platform_interpretations": art_direction.get("platform_interpretations", {}),
            "information_priority": art_direction.get("information_priority", {}),
            "benefit_translation": art_direction.get("benefit_translation", {}),
            "composition": art_direction.get("composition", ""),
            "mood": art_direction.get("mood", ""),
        }
        plat_key = platform.split("_", 1)[0]
        attempts = [{"direction": v5_direction, "prompt": visual_plan["gemini_image_prompt"], "kind": "primary"}]
        attempts.extend(
            {"direction": item.get("direction", {}), "prompt": item.get("prompt", ""), "kind": "next_direction"}
            for item in art_direction.get("v5_fallback_candidates", [])
            if isinstance(item, dict) and isinstance(item.get("direction"), dict) and str(item.get("prompt", "")).strip()
        )
        fallback_attempts: list[dict[str, str]] = []
        result: dict[str, Any] = {}
        asset_path: str | None = None
        for attempt in attempts:
            attempt_plan = dict(visual_plan)
            attempt_plan["v5_direction"] = attempt["direction"]
            attempt_plan["gemini_image_prompt"] = attempt["prompt"]
            try:
                result = social_visuals.generate_visuals(content, attempt_plan)
            except Exception as exc:
                fallback_attempts.append({"kind": attempt["kind"], "reason": str(exc)[:240]})
                continue
            asset_path = result.get(plat_key) if isinstance(result, dict) else None
            if asset_path:
                break
            fallback_attempts.append({
                "kind": attempt["kind"],
                "reason": str((result.get("fallback_reasons", {}) or {}).get(plat_key, "no_asset"))[:240] if isinstance(result, dict) else "invalid_result",
            })
        if not asset_path and fallback_attempts:
            reasons = ";".join(f"{item['kind']}={item['reason']}" for item in fallback_attempts)
            raise RuntimeError(f"gemini_visual_generation_failed:{reasons}")

        return VisualResult(
            provider=self.name,
            kind="generated_image",
            prompt=positive_prompt,
            negative_prompt=negative_prompt,
            asset_path=asset_path,
            provider_meta={"platform": platform, "fallback_ladder": fallback_attempts, **{k: v for k, v in result.items() if k != plat_key}},
        )


class EntertainmentStudioVisualProvider:
    """Routes complete structured visual work to Studio and fails closed."""

    name = "entertainment_studio"

    def __init__(self, base_url: str, token: str, *, fallback: VisualProvider | None = None, timeout: float = 180.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    def generate(self, *, art_direction: dict[str, Any], positive_prompt: str, negative_prompt: str, platform: str) -> VisualResult:
        creative_request = art_direction.get("creative_request")
        route = str((creative_request or {}).get("requestedRoute") or "")
        if not isinstance(creative_request, dict) or not route:
            raise RuntimeError("entertainment_studio_request_invalid:creative_request_and_route_required")
        headline = str(art_direction.get("visual_message") or "").strip()
        if not headline:
            raise RuntimeError("entertainment_studio_request_invalid:concrete_headline_required")
        production = {
            "headline": headline[:300],
            "kind": str(art_direction.get("visual_format") or "cinematic").lower() if str(art_direction.get("visual_format") or "").lower() in {"cinematic", "product", "typography", "comic", "carousel", "storypage"} else "cinematic",
            "aspectRatio": str(((creative_request.get("composition") or {}).get("aspectRatio") or "4:5")) if str(((creative_request.get("composition") or {}).get("aspectRatio") or "4:5")) in {"1:1", "4:5", "9:16", "16:9"} else "4:5",
            "provider": "gemini",
            "promptPrefix": positive_prompt[:2000],
        }
        sequence_briefs = art_direction.get("sequence_briefs")
        if isinstance(sequence_briefs, list) and len(sequence_briefs) >= 2:
            incomplete = [index + 1 for index, item in enumerate(sequence_briefs) if not isinstance(item, dict) or not str(item.get("title") or "").strip() or not str(item.get("prompt") or "").strip()]
            if incomplete:
                raise RuntimeError(f"entertainment_studio_request_invalid:incomplete_sequence_briefs={incomplete}")
            production["sequenceBriefs"] = [
                {
                    "title": str(item["title"]).strip()[:180],
                    "prompt": str(item["prompt"]).strip()[:3000],
                    "useCanon": bool(item.get("useCanon", True)),
                    **({"role": str(item["role"])} if item.get("role") in {"COVER", "STORY", "FINALE", "PANEL"} else {}),
                    **({"speaker": str(item["speaker"])[:100]} if item.get("speaker") else {}),
                    **({"dialogue": str(item["dialogue"])[:500]} if item.get("dialogue") else {}),
                    **({"caption": str(item["caption"])[:500]} if item.get("caption") else {}),
                    **({"heroPanel": bool(item["heroPanel"])} if "heroPanel" in item else {}),
                }
                for item in sequence_briefs[:10]
            ]
        try:
            response = requests.post(
                f"{self.base_url}/api/creative-requests",
                json={"request": creative_request, "production": production},
                headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
                timeout=self.timeout,
            )
            response.raise_for_status()
            payload = response.json()
            result = payload.get("result") or {}
            assets = result.get("assets") or []
            if not assets:
                raise ValueError("Entertainment Studio returned no assets")
            return VisualResult(
                provider=self.name,
                kind="generated_image",
                prompt=positive_prompt,
                negative_prompt=negative_prompt,
                asset_path=f"{self.base_url}/api/assets/{assets[0]}",
                provider_meta={"platform": platform, "creative_request": creative_request, "creative_result": result, "replayed": bool(payload.get("replayed"))},
            )
        except Exception as exc:
            raise RuntimeError(f"entertainment_studio_generation_failed:route={route}:{type(exc).__name__}:{str(exc)[:500]}") from exc


def default_provider() -> "VisualProvider":
    """Select live generation when configured; otherwise return a preview-only recipe."""
    studio_url = os.environ.get("ENTERTAINMENT_STUDIO_URL", "").strip()
    studio_token = (
        os.environ.get("ENTERTAINMENT_STUDIO_TOKEN", "").strip()
        or os.environ.get("SOCIAL_ENGINE_TOKEN", "").strip()
    )
    if studio_url and studio_token:
        return EntertainmentStudioVisualProvider(studio_url, studio_token)
    if os.environ.get("GEMINI_API_KEY", "").strip():
        return GeminiVisualProvider()
    return TemplateRenderProvider()
