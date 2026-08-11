"""StrategicBrief — the single source of truth for copy AND design (spec Section 19 + 44).

Every generated post is anchored to one StrategicBrief. All downstream phases
(Phase 2 creative stack, Phase 4 optimization, Phase 5-6 caption generation,
Phase 7 conference, visual generation) MUST derive their choices from this
object. That is the "copy and design share the same strategic brief" guarantee.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class PersuasionBlock:
    """Spec Section 9 A-K: who / when / problem / desire / product / mechanism /
    benefit / emotion / proof / objection / CTA intent."""
    who: str = ""
    when_context: str = ""
    problem: str = ""
    desire: str = ""
    product: str = ""
    feature: str = ""
    mechanism: str = ""
    benefit: str = ""
    outcome: str = ""
    proof: str = ""
    objection: str = ""
    transformation_from: str = ""
    transformation_to: str = ""


@dataclass
class CopyBlock:
    hook: str = ""
    headline: str = ""
    supporting_text: str = ""
    caption: str = ""
    cta: str = ""
    hashtags: list[str] = field(default_factory=list)


@dataclass
class DesignBlock:
    visual_hook: str = ""
    hero_element: str = ""
    layout: str = ""
    text_overlay: list[str] = field(default_factory=list)
    visual_direction: str = ""
    template: str = ""
    image_prompt: str = ""


@dataclass
class QualityBlock:
    conversion_quality_score: float = 0.0
    claim_integrity: str = ""
    brand_score: float = 0.0
    repetition_score: float = 0.0
    component_scores: dict[str, float] = field(default_factory=dict)


@dataclass
class ExperimentBlock:
    variant_id: str = ""
    variables: dict[str, Any] = field(default_factory=dict)


@dataclass
class StrategicBrief:
    """Spec Section 44 shape. Immutable within one generation cycle."""

    # Strategy layer
    product_id: str = ""
    product_name: str = ""
    campaign_goal: str = ""
    audience_id: str = ""
    audience_name: str = ""
    awareness_stage: str = ""
    funnel_stage: str = ""
    logic_principle: str = ""
    emotional_driver_primary: str = ""
    emotional_driver_secondary: str = ""
    copy_framework: str = ""
    creative_type: str = ""
    platform_priority: list[str] = field(default_factory=list)

    persuasion: PersuasionBlock = field(default_factory=PersuasionBlock)
    copy: CopyBlock = field(default_factory=CopyBlock)
    design: DesignBlock = field(default_factory=DesignBlock)
    quality: QualityBlock = field(default_factory=QualityBlock)
    experiment: ExperimentBlock = field(default_factory=ExperimentBlock)

    # Provenance
    brief_id: str = ""
    schema_version: str = "conversion.v1"
    generated_at: str = ""
    source: str = "conversion_strategist"
    rationale: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def summary(self) -> str:
        """Compact human-readable summary for logging."""
        return (
            f"[{self.brief_id or 'brief'}] "
            f"aud={self.audience_id} aware={self.awareness_stage} "
            f"law={self.logic_principle} emo={self.emotional_driver_primary} "
            f"struct={self.copy_framework} product={self.product_id or '-'}"
        )
