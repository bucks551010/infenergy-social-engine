"""Structured schemas for the Living Business Intelligence Foundation.

Everything is a plain dataclass so we avoid adding a runtime dependency
on pydantic. A light hand-rolled validator (``validate``) enforces
required-field / enum / confidence-range rules per §62.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

from .information_types import INFORMATION_TYPES


SCHEMA_VERSION = "bi.v1"


# --- Source registry (§4, §5) --------------------------------------------


@dataclass
class Source:
    source_id: str
    source_type: str  # csv_catalog | document | repository | structured_config | image_asset | performance | external_research | manifesto
    location: str
    display_name: str = ""
    format: str = ""
    discovered_at: str = ""
    last_read_at: str = ""
    checksum: str = ""
    size_bytes: int = 0
    row_count: int | None = None
    notes: str = ""


# --- Evidence (§7) --------------------------------------------------------


@dataclass
class EvidenceRecord:
    evidence_id: str
    subject: str
    field: str
    value: Any
    information_type: str  # one of INFORMATION_TYPES
    source_id: str
    source_location: str = ""
    source_authority: str = "low"
    confidence: float = 0.0
    verification_status: str = "unverified"  # unverified | verified | disputed | expired
    risk_level: str = "LOW"  # LOW | MEDIUM | HIGH
    freshness_required: bool = False
    observed_at: str = ""
    verified_at: str = ""
    expires_at: str | None = None
    notes: str = ""


@dataclass
class ConflictRecord:
    conflict_id: str
    subject: str
    field: str
    values: list[dict[str, Any]] = field(default_factory=list)
    status: str = "requires_verification"  # requires_verification | resolved | dismissed
    resolution: str = ""
    resolved_by: str = ""
    resolved_at: str = ""


# --- Offering (§15, §16) --------------------------------------------------


@dataclass
class Offering:
    offering_id: str
    offering_type: str  # PRODUCT|SERVICE|SUBSCRIPTION|...
    name: str
    parent_offering_id: str = ""
    sku: str = ""
    brand: str = ""
    category: str = ""
    subcategory: str = ""
    price: float | None = None
    sale_price: float | None = None
    stock_status: str = ""
    description_raw: str = ""
    description_clean: str = ""
    features: list[str] = field(default_factory=list)
    specifications: dict[str, Any] = field(default_factory=dict)
    dimensions: dict[str, Any] = field(default_factory=dict)
    weight: float | None = None
    images: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    use_cases: list[str] = field(default_factory=list)
    problems_addressed: list[str] = field(default_factory=list)
    mechanisms: list[str] = field(default_factory=list)
    functional_benefits: list[str] = field(default_factory=list)
    emotional_benefits: list[str] = field(default_factory=list)
    outcomes: list[str] = field(default_factory=list)
    transformations: list[str] = field(default_factory=list)
    differentiators: list[str] = field(default_factory=list)
    alternatives: list[str] = field(default_factory=list)
    compatibility: list[str] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    objections: list[str] = field(default_factory=list)
    proof: list[str] = field(default_factory=list)
    claim_constraints: list[str] = field(default_factory=list)
    customer_fit: list[str] = field(default_factory=list)
    consumer_profile: dict[str, Any] = field(default_factory=dict)
    purchase_context: list[str] = field(default_factory=list)
    content_opportunities: list[str] = field(default_factory=list)
    verified_facts: list[str] = field(default_factory=list)
    forbidden_claims: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)


@dataclass
class OfferingGraphEdge:
    source_id: str
    target_id: str
    relation: str  # HAS_FEATURE | ADDRESSES_PROBLEM | ENABLES_USE_CASE | SERVES_SEGMENT | ...
    strength: float = 0.5
    evidence_refs: list[str] = field(default_factory=list)


# --- Audience (§21-§24) ---------------------------------------------------


@dataclass
class AudienceSegment:
    segment_id: str
    name: str
    definition: str = ""
    experience_level: str = ""
    lifestyle_context: list[str] = field(default_factory=list)
    goals: list[str] = field(default_factory=list)
    problems: list[str] = field(default_factory=list)
    frustrations: list[str] = field(default_factory=list)
    fears: list[str] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
    curiosities: list[str] = field(default_factory=list)
    misconceptions: list[str] = field(default_factory=list)
    information_gaps: list[str] = field(default_factory=list)
    desired_outcomes: list[str] = field(default_factory=list)
    emotional_drivers: list[str] = field(default_factory=list)
    purchase_context: list[str] = field(default_factory=list)
    decision_criteria: list[str] = field(default_factory=list)
    objections: list[str] = field(default_factory=list)
    alternatives: list[str] = field(default_factory=list)
    existing_tools: list[str] = field(default_factory=list)
    triggers: list[str] = field(default_factory=list)
    barriers: list[str] = field(default_factory=list)
    platform_behavior: list[str] = field(default_factory=list)
    preferred_language: list[str] = field(default_factory=list)
    content_preferences: list[str] = field(default_factory=list)
    trust_requirements: list[str] = field(default_factory=list)
    social_identity: str = ""
    evidence_refs: list[str] = field(default_factory=list)
    confidence: float = 0.5


@dataclass
class CustomerMoment:
    moment_id: str
    situation: str
    trigger: str = ""
    current_thought: str = ""
    current_emotion: str = ""
    friction: str = ""
    desired_change: str = ""
    likely_question: str = ""
    likely_objection: str = ""
    relevant_offering_ids: list[str] = field(default_factory=list)
    appropriate_content_job: str = ""


@dataclass
class Transformation:
    transformation_id: str
    current_state: str
    friction: str
    desired_state: str
    offering_capability: str
    mechanism: str
    benefit: str
    outcome: str
    emotional_meaning: str


# --- Positioning + Brand (§25-§30) ----------------------------------------


@dataclass
class Positioning:
    market_category: str = ""
    category_role: str = ""
    competitive_frame: str = ""
    direct_alternatives: list[str] = field(default_factory=list)
    indirect_alternatives: list[str] = field(default_factory=list)
    status_quo_alternative: str = ""
    primary_position: str = ""
    secondary_positions: list[str] = field(default_factory=list)
    differentiators: list[str] = field(default_factory=list)
    reasons_to_believe: list[str] = field(default_factory=list)
    positioning_strength: float = 0.5
    positioning_risks: list[str] = field(default_factory=list)
    positioning_whitespace: list[str] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)


@dataclass
class Reputation:
    desired_reputation: str = ""
    desired_associations: list[str] = field(default_factory=list)
    desired_emotions: list[str] = field(default_factory=list)
    desired_customer_language: list[str] = field(default_factory=list)
    trust_attributes: list[str] = field(default_factory=list)
    authority_attributes: list[str] = field(default_factory=list)
    community_attributes: list[str] = field(default_factory=list)
    undesired_associations: list[str] = field(default_factory=list)
    reputation_risks: list[str] = field(default_factory=list)


@dataclass
class BrandPromise:
    promise: str = ""
    business_capability: str = ""
    offering_capability: str = ""
    customer_outcome: str = ""
    evidence_refs: list[str] = field(default_factory=list)


@dataclass
class VoiceDNA:
    brand_personality: str = ""
    voice_principles: list[str] = field(default_factory=list)
    voice_traits: list[str] = field(default_factory=list)
    tone_range: list[str] = field(default_factory=list)
    sentence_style: str = ""
    rhythm: str = ""
    vocabulary_notes: str = ""
    technical_depth: str = ""
    humor_policy: str = ""
    confidence_level: str = ""
    warmth_level: str = ""
    authority_level: str = ""
    directness_level: str = ""
    emotional_range: list[str] = field(default_factory=list)
    preferred_phrases: list[str] = field(default_factory=list)
    prohibited_phrases: list[str] = field(default_factory=list)
    cliches_to_avoid: list[str] = field(default_factory=list)
    claims_language: str = ""
    cta_style: str = ""
    storytelling_style: str = ""
    educational_style: str = ""
    community_style: str = ""
    sales_style: str = ""
    platform_variations: dict[str, str] = field(default_factory=dict)


@dataclass
class VisualDNA:
    logo_assets: list[str] = field(default_factory=list)
    brand_colors: dict[str, str] = field(default_factory=dict)
    accent_palette: list[str] = field(default_factory=list)
    neutral_palette: list[str] = field(default_factory=list)
    heading_font: str = ""
    body_font: str = ""
    typography_behavior: str = ""
    spacing_system: str = ""
    border_radius: str = ""
    icon_style: str = ""
    photography_style: str = ""
    illustration_style: str = ""
    graphic_density: str = ""
    background_style: str = ""
    shadow_rules: str = ""
    texture_rules: str = ""
    image_tone: str = ""
    visual_energy: str = ""
    brand_mood: str = ""
    product_representation_rules: list[str] = field(default_factory=list)
    human_representation_rules: list[str] = field(default_factory=list)
    composition_preferences: list[str] = field(default_factory=list)
    visual_metaphor_policy: str = ""
    prohibited_visual_patterns: list[str] = field(default_factory=list)
    accessibility_requirements: list[str] = field(default_factory=list)


# --- Business identity + why + worldview + job (§11-§14) -----------------


@dataclass
class BusinessIdentity:
    business_name: str = ""
    business_description: str = ""
    business_type: str = ""
    industry: str = ""
    subindustries: list[str] = field(default_factory=list)
    business_model: str = ""
    commercial_model: str = ""
    geographic_relevance: str = ""
    stage: str = ""
    primary_category: str = ""
    secondary_categories: list[str] = field(default_factory=list)
    what_we_do: list[str] = field(default_factory=list)
    what_we_do_not_do: list[str] = field(default_factory=list)


@dataclass
class BusinessWhy:
    reason_for_existence: str = ""
    foundational_problem: str = ""
    mission: str = ""
    vision: str = ""
    purpose: str = ""
    beliefs: list[str] = field(default_factory=list)
    principles: list[str] = field(default_factory=list)
    worldview: str = ""
    desired_customer_impact: str = ""
    desired_social_impact: str = ""
    future_state_we_want_to_help_create: str = ""
    why_customers_should_matter_to_us: str = ""
    why_we_want_people_to_purchase: str = ""
    why_the_business_deserves_to_exist: str = ""


@dataclass
class Worldview:
    market_beliefs: list[str] = field(default_factory=list)
    customer_deserves: list[str] = field(default_factory=list)
    unnecessary_difficulties: list[str] = field(default_factory=list)
    conventional_agrees_with: list[str] = field(default_factory=list)
    conventional_challenges: list[str] = field(default_factory=list)
    enduring_principles: list[str] = field(default_factory=list)
    supported_progress: list[str] = field(default_factory=list)
    would_never_encourage: list[str] = field(default_factory=list)


@dataclass
class BusinessJob:
    functional_job: str = ""
    emotional_job: str = ""
    educational_job: str = ""
    decision_support_job: str = ""
    community_job: str = ""
    commercial_job: str = ""


# --- Social mandate + content territories + posture ---------------------


@dataclass
class SocialMandate:
    social_account_role: str = ""
    social_account_promise: str = ""
    audience_value_exchange: str = ""
    what_followers_should_gain: list[str] = field(default_factory=list)
    what_the_account_should_be_known_for: list[str] = field(default_factory=list)
    what_the_account_should_never_become: list[str] = field(default_factory=list)
    commercial_role: str = ""
    educational_role: str = ""
    community_role: str = ""
    authority_role: str = ""
    entertainment_role: str = ""
    conversation_role: str = ""


@dataclass
class ContentTerritory:
    territory_id: str
    name: str
    description: str = ""
    brand_relevance: float = 0.5
    audience_relevance: float = 0.5
    offering_connection: list[str] = field(default_factory=list)
    authority_basis: str = ""
    evidence_refs: list[str] = field(default_factory=list)
    recommended_depth: str = ""


@dataclass
class BrandPosture:
    how_the_brand_speaks: str = ""
    how_the_brand_teaches: str = ""
    how_the_brand_sells: str = ""
    how_the_brand_disagrees: str = ""
    how_the_brand_handles_uncertainty: str = ""
    how_the_brand_handles_risk: str = ""
    how_the_brand_handles_customer_questions: str = ""
    how_the_brand_handles_mistakes: str = ""
    how_the_brand_handles_comparison: str = ""
    how_the_brand_handles_urgency: str = ""


# --- Research + knowledge gaps + hypothesis + claim (§35-§38, §51) ------


@dataclass
class ResearchPolicy:
    research_enabled: bool = False
    allowed_source_types: list[str] = field(default_factory=list)
    preferred_sources: list[str] = field(default_factory=list)
    blocked_sources: list[str] = field(default_factory=list)
    freshness_requirements: dict[str, int] = field(default_factory=dict)
    max_research_depth: int = 1
    high_risk_verification_required: bool = True
    competitor_research_enabled: bool = False
    current_event_research_enabled: bool = False
    technical_research_enabled: bool = True
    research_cache_ttl_days: int = 14


@dataclass
class KnowledgeGap:
    gap_id: str
    domain: str
    question: str
    importance: str = "medium"  # low | medium | high
    reason_needed: str = ""
    downstream_impact: str = ""
    researchable: bool = False
    owner_input_required: bool = False
    priority: int = 5
    status: str = "OPEN"  # OPEN | IN_PROGRESS | RESOLVED | DEFERRED
    notes: str = ""


@dataclass
class Hypothesis:
    hypothesis_id: str
    statement: str
    domain: str
    confidence: float = 0.3
    supporting_evidence: list[str] = field(default_factory=list)
    contradicting_evidence: list[str] = field(default_factory=list)
    validation_method: str = ""
    status: str = "UNTESTED"  # UNTESTED | WEAK_SIGNAL | SUPPORTED | STRONGLY_SUPPORTED | DISPROVEN | RETIRED


@dataclass
class Claim:
    claim_id: str
    subject: str
    claim: str
    claim_type: str
    supporting_evidence: list[str] = field(default_factory=list)
    confidence: float = 0.5
    verification_status: str = "unverified"
    risk: str = "LOW"
    allowed_wording: list[str] = field(default_factory=list)
    prohibited_wording: list[str] = field(default_factory=list)
    freshness_required: bool = False
    last_verified: str = ""


# --- Learning + overrides + versioning (§39-§41, §66) -------------------


@dataclass
class OwnerOverride:
    override_id: str
    subject: str  # e.g. "voice.tone_range", "audience_universe.segments.preparedness_focused_household.name"
    field_path: str
    value: Any
    reason: str = ""
    applied_at: str = ""
    persistent: bool = True


@dataclass
class ProfileVersion:
    profile_version: str
    created_at: str
    updated_at: str
    changed_fields: list[str] = field(default_factory=list)
    change_reason: str = ""
    source_event: str = ""
    previous_version: str = ""
    confidence_change: float = 0.0
    approved_by: str = ""


@dataclass
class LearningRecord:
    record_id: str
    scope: str  # audience | topic | angle | benefit | problem | emotion | CTA | platform | comment_theme
    subject: str
    signal: str  # positive | negative | neutral
    weight: float = 1.0
    sample_size: int = 1
    observed_at: str = ""
    source_post_id: str = ""


# --- The living BusinessProfile (§10) ----------------------------------


@dataclass
class BusinessProfile:
    profile_id: str
    profile_version: str
    schema_version: str = SCHEMA_VERSION
    identity: BusinessIdentity = field(default_factory=BusinessIdentity)
    why: BusinessWhy = field(default_factory=BusinessWhy)
    worldview: Worldview = field(default_factory=Worldview)
    job: BusinessJob = field(default_factory=BusinessJob)
    positioning: Positioning = field(default_factory=Positioning)
    promise: BrandPromise = field(default_factory=BrandPromise)
    reputation: Reputation = field(default_factory=Reputation)
    voice: VoiceDNA = field(default_factory=VoiceDNA)
    visual: VisualDNA = field(default_factory=VisualDNA)
    posture: BrandPosture = field(default_factory=BrandPosture)
    social_mandate: SocialMandate = field(default_factory=SocialMandate)
    content_territories: list[ContentTerritory] = field(default_factory=list)
    audience_segments: list[AudienceSegment] = field(default_factory=list)
    customer_moments: list[CustomerMoment] = field(default_factory=list)
    transformations: list[Transformation] = field(default_factory=list)
    offerings: list[Offering] = field(default_factory=list)
    offering_graph: list[OfferingGraphEdge] = field(default_factory=list)
    research_policy: ResearchPolicy = field(default_factory=ResearchPolicy)
    knowledge_gaps: list[KnowledgeGap] = field(default_factory=list)
    hypotheses: list[Hypothesis] = field(default_factory=list)
    claims: list[Claim] = field(default_factory=list)
    current_priorities: dict[str, Any] = field(default_factory=dict)
    learning_state: dict[str, Any] = field(default_factory=dict)
    source_refs: list[str] = field(default_factory=list)
    field_confidences: dict[str, float] = field(default_factory=dict)
    field_info_types: dict[str, str] = field(default_factory=dict)
    generated_at: str = ""


# --- Light validator (§62) ----------------------------------------------


class ValidationError(Exception):
    pass


def validate_evidence(rec: EvidenceRecord) -> None:
    if rec.information_type not in INFORMATION_TYPES:
        raise ValidationError(f"unknown information_type {rec.information_type!r}")
    if not (0.0 <= float(rec.confidence) <= 1.0):
        raise ValidationError(f"confidence out of range: {rec.confidence}")
    if rec.risk_level not in {"LOW", "MEDIUM", "HIGH"}:
        raise ValidationError(f"risk_level invalid: {rec.risk_level}")


def validate_profile(p: BusinessProfile) -> list[str]:
    """Return a list of soft-warning strings — do not raise."""
    warn: list[str] = []
    if not p.identity.business_name:
        warn.append("identity.business_name is empty")
    if not p.why.mission:
        warn.append("why.mission is empty")
    if not p.audience_segments:
        warn.append("no audience segments")
    if not p.offerings:
        warn.append("no offerings")
    if not p.social_mandate.social_account_role:
        warn.append("social_mandate.social_account_role is empty")
    return warn


def to_dict(obj: Any) -> Any:
    """dataclasses.asdict wrapper that leaves plain values alone."""
    try:
        return asdict(obj)
    except TypeError:
        return obj
