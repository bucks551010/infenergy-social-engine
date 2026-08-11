"""Visual provider interface + template fallback (Master Build §92).

The abstract ``VisualProvider`` decouples the pipeline from any specific
image-generation SDK.  A real Gemini/Imagen provider can subclass it;
``TemplateRenderProvider`` returns a deterministic "recipe" object that
can be handed to a downstream graphic renderer (Pillow/HTML template).
"""

from __future__ import annotations

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
