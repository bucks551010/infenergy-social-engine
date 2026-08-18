"""Visual provider interface + template fallback (Master Build §92).

The abstract ``VisualProvider`` decouples the pipeline from any specific
image-generation SDK.  ``GeminiVisualProvider`` is the real provider
(delegates pixel generation to the already-proven ``social_visuals``
Gemini image pipeline, per §34 — don't reinvent what existing code does
well). ``TemplateRenderProvider`` returns a deterministic "recipe" object
used as an automatic fallback when Gemini is unavailable or fails.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Protocol


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
    reference images, plate + semantic quality QA, retries). Falls back to
    ``TemplateRenderProvider`` output whenever Gemini is unavailable or the
    call fails, so the orchestrator never breaks without network access.
    """

    name = "gemini"

    def __init__(self) -> None:
        self._fallback = TemplateRenderProvider()

    def generate(
        self,
        *,
        art_direction: dict[str, Any],
        positive_prompt: str,
        negative_prompt: str,
        platform: str,
    ) -> VisualResult:
        if not os.environ.get("GEMINI_API_KEY", "").strip():
            return self._fallback.generate(
                art_direction=art_direction,
                positive_prompt=positive_prompt,
                negative_prompt=negative_prompt,
                platform=platform,
            )
        try:
            try:
                import social_visuals  # type: ignore
            except ImportError:
                from scripts import social_visuals  # type: ignore
        except Exception as exc:
            fb = self._fallback.generate(
                art_direction=art_direction,
                positive_prompt=positive_prompt,
                negative_prompt=negative_prompt,
                platform=platform,
            )
            fb.provider_meta["gemini_import_error"] = str(exc)
            return fb

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
            fb = self._fallback.generate(
                art_direction=art_direction,
                positive_prompt=positive_prompt,
                negative_prompt=negative_prompt,
                platform=platform,
            )
            fb.provider_meta["fallback_ladder"] = fallback_attempts
            return fb

        return VisualResult(
            provider=self.name,
            kind="generated_image",
            prompt=positive_prompt,
            negative_prompt=negative_prompt,
            asset_path=asset_path,
            provider_meta={"platform": platform, "fallback_ladder": fallback_attempts, **{k: v for k, v in result.items() if k != plat_key}},
        )


def default_provider() -> "VisualProvider":
    """Auto-select the real Gemini provider when a key is configured."""
    if os.environ.get("GEMINI_API_KEY", "").strip():
        return GeminiVisualProvider()
    return TemplateRenderProvider()
