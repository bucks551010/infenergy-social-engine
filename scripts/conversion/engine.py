"""ConversionLogicEngine — Spec Section 42.

The orchestrator. Given inputs about the run (audience hint, funnel stage,
product intel, history), it assembles a fully populated StrategicBrief that
downstream phases MUST respect.

This is the single strategic decision layer — it makes ALL the decisions
(who, what awareness stage, what law, what emotion, what structure, what
objection, what hook target, what CTA) BEFORE any copy is written.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timezone
from typing import Any

from . import awareness as awareness_mod
from . import claims as claims_mod
from . import copy_structures as copy_structures_mod
from . import ctas as ctas_mod
from . import emotions as emotions_mod
from . import hook_engine
from . import logic_laws as logic_laws_mod
from . import objections as objections_mod
from . import personas as personas_mod
from . import transformations as transformations_mod
from .briefs import (
    CopyBlock,
    DesignBlock,
    ExperimentBlock,
    PersuasionBlock,
    QualityBlock,
    StrategicBrief,
)


class ConversionLogicEngine:
    """Assembles a StrategicBrief from run inputs."""

    def __init__(self, config: dict[str, Any] | None = None) -> None:
        self.config = config or {}

    def build_brief(
        self,
        *,
        funnel_stage: str,
        product: dict[str, Any] | None = None,
        audience_hint: str | None = None,
        campaign_goal: str = "",
        platform_priority: list[str] | None = None,
        recent: dict[str, list[str]] | None = None,
        explicit: dict[str, str] | None = None,
        winning_hints: dict[str, list[str]] | None = None,
        losing_hints: dict[str, list[str]] | None = None,
    ) -> StrategicBrief:
        """Produce a fully populated StrategicBrief.

        Args:
            funnel_stage: existing funnel taxonomy (ATTENTION/EDUCATION/...).
            product: dict with keys product_id, product_name, product_type,
                     features[], mechanisms[], benefits[], verified_facts[],
                     top_objection (optional), landing_page_url.
            audience_hint: persona_id to force; else inferred from product.
            campaign_goal: awareness | consideration | purchase | promotion.
            platform_priority: list of platform names in publish priority.
            recent: dict with keys hooks, ctas, laws, structures, captions.
            explicit: dict with optional overrides for any strategy field.
            winning_hints: performance-memory feedback with keys
                logic_principle, copy_framework, emotional_driver_primary,
                audience_id, awareness_stage - each mapping to a list of
                proven-winner values. Used to bias selection while still
                respecting recency and eligibility.
            losing_hints: performance-memory feedback (same shape as
                winning_hints) listing proven-loser values. Merged into the
                recency-exclusion lists so known-bad combos are deprioritized
                the same way recently-used ones are, unless no alternative exists.
        """
        recent = recent or {}
        explicit = explicit or {}
        product = product or {}
        winning_hints = winning_hints or {}
        losing_hints = losing_hints or {}
        platform_priority = platform_priority or ["facebook", "instagram", "linkedin"]
        avoid_laws = list(dict.fromkeys(list(recent.get("laws") or []) + list(losing_hints.get("logic_principle") or [])))
        avoid_structures = list(dict.fromkeys(list(recent.get("structures") or []) + list(losing_hints.get("copy_framework") or [])))

        # 1. Persona
        persona_id = audience_hint or personas_mod.infer_from_product_and_stage(
            product.get("product_type"), funnel_stage
        )
        persona = personas_mod.get(persona_id)

        # 2. Awareness stage
        awareness_stage = awareness_mod.classify(
            funnel_stage=funnel_stage,
            audience_awareness_hint=explicit.get("awareness_stage"),
            persona_default=persona.get("awareness_stage"),
        )

        # 3. Logic law
        has_verified = bool(product.get("verified_facts"))
        law = logic_laws_mod.select(
            awareness_stage=awareness_stage,
            recent_law_ids=avoid_laws,
            explicit=explicit.get("logic_principle"),
            product_has_verified_specs=has_verified,
            preferred=winning_hints.get("logic_principle"),
        )

        # 4. Emotional drivers
        primary_emotion, secondary_emotion = emotions_mod.select(
            persona_id=persona_id,
            awareness_stage=awareness_stage,
            explicit_primary=explicit.get("emotional_driver_primary"),
            explicit_secondary=explicit.get("emotional_driver_secondary"),
            preferred=winning_hints.get("emotional_driver_primary"),
        )

        # 5. Copy structure
        structure = copy_structures_mod.select(
            awareness_stage=awareness_stage,
            law_name=law,
            recent_structures=avoid_structures,
            explicit=explicit.get("copy_framework"),
            preferred=winning_hints.get("copy_framework"),
        )

        # 6. Objection
        objection = objections_mod.select(
            awareness_stage=awareness_stage,
            persona_top_objection=persona.get("top_objection"),
            explicit=explicit.get("objection"),
        )

        # 7. Transformation
        t_from, t_to = transformations_mod.default_pair(persona_id)

        # 8. Persuasion block
        feature = _first(product.get("features"))
        mechanism = _first(product.get("mechanisms"))
        benefit = _first(product.get("benefits"))
        outcome = _first(product.get("outcomes")) or benefit
        proof = _first(product.get("verified_facts")) or (
            f"Verified {product.get('product_type', 'product')} specification"
            if product else ""
        )

        persuasion = PersuasionBlock(
            who=persona.get("audience_name", ""),
            when_context=persona.get("context", ""),
            problem=persona.get("primary_problem", ""),
            desire=persona.get("desired_outcome", ""),
            product=product.get("product_name", ""),
            feature=feature,
            mechanism=mechanism,
            benefit=benefit,
            outcome=outcome,
            proof=proof,
            objection=objections_mod.reframe_pattern(objection),
            transformation_from=t_from,
            transformation_to=t_to,
        )

        # 9. CTA
        cta_text = ctas_mod.choose(
            awareness_stage=awareness_stage,
            campaign_objective=campaign_goal,
            existing_cta=explicit.get("cta", ""),
            recent_ctas=recent.get("ctas"),
        )

        # 10. Design direction anchored to law
        design = DesignBlock(
            visual_direction=logic_laws_mod.visual_strategy(law),
            template=_visual_template_for(law, awareness_stage),
            image_prompt="",  # filled by downstream visual director using this direction
        )

        # 11. Copy block seeded with CTA only; hook/caption filled downstream
        copy = CopyBlock(cta=cta_text)

        # 12. Experiment variant id
        experiment = ExperimentBlock(
            variant_id=_variant_id(persona_id, awareness_stage, law, structure, primary_emotion),
            variables={
                "law": law,
                "structure": structure,
                "primary_emotion": primary_emotion,
                "hook_category_hint": _hook_category_hint(awareness_stage, law),
            },
        )

        # 13. Assemble
        brief = StrategicBrief(
            product_id=product.get("product_id", ""),
            product_name=product.get("product_name", ""),
            campaign_goal=campaign_goal or awareness_mod.preferred_cta_style(awareness_stage),
            audience_id=persona_id,
            audience_name=persona.get("audience_name", ""),
            awareness_stage=awareness_stage,
            funnel_stage=(funnel_stage or "").upper(),
            logic_principle=law,
            emotional_driver_primary=primary_emotion,
            emotional_driver_secondary=secondary_emotion,
            copy_framework=structure,
            creative_type=design.template,
            platform_priority=platform_priority,
            persuasion=persuasion,
            copy=copy,
            design=design,
            quality=QualityBlock(),
            experiment=experiment,
            brief_id=str(uuid.uuid4())[:8],
            generated_at=datetime.now(timezone.utc).isoformat(),
            rationale={
                "awareness_stage": f"funnel={funnel_stage} + persona={persona_id}",
                "logic_principle": f"eligible-for {awareness_stage}, avoids recent {recent.get('laws', [])[:3]}",
                "emotional_driver": f"persona-default for {persona_id} at {awareness_stage}",
                "copy_framework": f"best-fit for {law} + {awareness_stage}",
                "objection": f"persona.top_objection={persona.get('top_objection')} at {awareness_stage}",
            },
        )
        return brief

    def score_hook_candidates(
        self,
        brief: StrategicBrief,
        candidates: list[str],
        recent_hooks: list[str] | None = None,
        platform: str = "facebook",
    ) -> tuple[str, dict[str, float], list[dict[str, Any]]]:
        """Given a brief and hook candidates, return best hook + all scored."""
        return hook_engine.pick_best(
            candidates=candidates,
            audience_keywords=personas_mod.audience_keywords(brief.audience_id),
            product_name=brief.product_name or None,
            recent_hooks=recent_hooks,
            platform=platform,
        )

    def check_claims(
        self,
        text: str,
        verified_facts: list[str] | None = None,
        warranty_available: bool = False,
    ) -> tuple[bool, list[str], dict[str, list[str]]]:
        scan = claims_mod.classify_text(
            text, verified_facts=verified_facts, warranty_available=warranty_available
        )
        publishable, reasons = claims_mod.is_publishable(scan)
        return publishable, reasons, scan


def build_strategic_brief(**kwargs: Any) -> StrategicBrief:
    """Module-level convenience wrapper used by generate_posts.py Phase 0."""
    return ConversionLogicEngine().build_brief(**kwargs)


def _first(seq: Any) -> str:
    if not seq:
        return ""
    if isinstance(seq, str):
        return seq
    try:
        for item in seq:
            if isinstance(item, str) and item.strip():
                return item.strip()
            if isinstance(item, dict):
                for key in ("text", "value", "name", "label"):
                    if isinstance(item.get(key), str) and item[key].strip():
                        return item[key].strip()
    except TypeError:
        return ""
    return ""


def _visual_template_for(law: str, awareness_stage: str) -> str:
    """Pick a §18 creative template that matches the law's visual strategy."""
    mapping = {
        "contrapositive": "before_after",
        "disjunctive": "comparison",
        "double_implication": "feature_spotlight",
        "symmetrical_equivalence": "benefit_spotlight",
        "result_traceability": "product_demonstration",
    }
    base = mapping.get(law, "product_hero")
    if awareness_stage == "UNAWARE":
        return "lifestyle" if base in ("product_hero", "feature_spotlight") else base
    if awareness_stage == "MOST_AWARE":
        return "offer" if base == "product_hero" else base
    return base


def _hook_category_hint(awareness_stage: str, law: str) -> str:
    """Pick one hook category likely strongest for this brief."""
    hints = {
        ("UNAWARE", "contrapositive"): "scenario",
        ("UNAWARE", "symmetrical_equivalence"): "lifestyle",
        ("PROBLEM_AWARE", "contrapositive"): "problem_recognition",
        ("SOLUTION_AWARE", "disjunctive"): "comparison",
        ("SOLUTION_AWARE", "result_traceability"): "benefit",
        ("PRODUCT_AWARE", "double_implication"): "product_revelation",
        ("PRODUCT_AWARE", "result_traceability"): "outcome",
        ("MOST_AWARE", "double_implication"): "outcome",
    }
    return hints.get((awareness_stage, law), "curiosity")


def _variant_id(*parts: str) -> str:
    h = hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()
    return h[:10]
