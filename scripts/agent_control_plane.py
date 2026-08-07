from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any


SCHEMAS_VERSION = "phase2.v1"


AGENT_IO_SCHEMAS: dict[str, dict[str, Any]] = {
    "visual_director": {
        "required": {
            "style_intent": "str",
            "mood": "str",
            "image_strategy": {"enum": ["gemini_generated", "product_photo_featured", "hybrid"]},
            "composition": "str",
            "use_product_photo": "bool",
            "text_on_image": {"enum": ["none", "minimal"]},
            "gemini_image_prompt": "str",
            "platform_overrides": {
                "required": {
                    "facebook": {
                        "required": {
                            "composition": "str",
                            "visual_direction": "str",
                        }
                    },
                    "instagram": {
                        "required": {
                            "composition": "str",
                            "visual_direction": "str",
                        }
                    },
                    "linkedin": {
                        "required": {
                            "composition": "str",
                            "visual_direction": "str",
                        }
                    },
                }
            },
        }
    },
    "pre_generation_conference": {
        "required": {
            "recommended_hook": "str",
            "recommended_cta": "str",
            "primary_angle": "str",
            "visual_focus": "str",
            "platform_notes": {
                "required": {
                    "facebook": "str",
                    "instagram": "str",
                    "linkedin": "str",
                }
            },
            "collective_actions": {"list_of": "str"},
            "risk_checks": {"list_of": "str"},
        }
    },
    "agent_conference": {
        "required": {
            "copywriter_feedback": {"list_of": "str"},
            "visual_director_feedback": {"list_of": "str"},
            "product_truth_feedback": {"list_of": "str"},
            "platform_editor_feedback": {"list_of": "str"},
            "collective_actions": {"list_of": "str"},
            "refined": {
                "required": {
                    "hook": "str",
                    "cta": "str",
                    "gemini_image_prompt": "str",
                    "image_strategy": {"enum": ["", "gemini_generated", "product_photo_featured", "hybrid"]},
                    "fb_caption": "str",
                    "ig_caption": "str",
                    "li_text": "str",
                }
            },
        }
    },
    "ideation_divergence": {
        "required": {
            "concepts": {
                "list_of": {
                    "required": {
                        "angle": "str",
                        "hook_candidate": "str",
                        "narrative_focus": "str",
                        "risk_note": "str",
                    }
                }
            },
            "winner_angle": "str",
            "winner_hook": "str",
            "novelty_rationale": "str",
        }
    },
    "audience_psychographics": {
        "required": {
            "primary_segment": "str",
            "emotional_driver": "str",
            "core_objection": "str",
            "trust_trigger": "str",
            "cta_framing": "str",
        }
    },
    "narrative_architect": {
        "required": {
            "narrative_sequence": {"list_of": "str"},
            "must_include": {"list_of": "str"},
            "proof_style": "str",
            "close_style": "str",
        }
    },
    "platform_voice_calibrator": {
        "required": {
            "facebook": "str",
            "instagram": "str",
            "linkedin": "str",
        }
    },
    "hook_stress_test": {
        "required": {
            "candidate_hooks": {"list_of": "str"},
            "recommended_hook": "str",
            "reason": "str",
        }
    },
    "precision_claims_verifier": {
        "required": {
            "passed": "bool",
            "issues": {"list_of": "str"},
            "required_fixes": {"list_of": "str"},
        }
    },
    "compliance_policy_sentinel": {
        "required": {
            "risk_level": {"enum": ["low", "medium", "high"]},
            "blocked_terms": {"list_of": "str"},
            "required_actions": {"list_of": "str"},
        }
    },
    "semantic_novelty": {
        "required": {
            "novelty_score": "number",
            "signal": "str",
            "rewrite_guidance": {"list_of": "str"},
        }
    },
    "visual_strategy": {
        "required": {
            "visual_objective": "str",
            "composition_adjustments": {"list_of": "str"},
            "platform_focus": {
                "required": {
                    "facebook": "str",
                    "instagram": "str",
                    "linkedin": "str",
                }
            },
        }
    },
    "cta_optimization": {
        "required": {
            "recommended_cta": "str",
            "alternates": {"list_of": "str"},
            "friction_note": "str",
        }
    },
    "phase7_conference_packets": {
        "required": {
            "pre_generation_packet": "dict",
            "pre_publish_packet": "dict",
            "post_run_packet": "dict",
        }
    },
}


@dataclass
class GateRecord:
    gate_id: str
    passed: bool
    severity: str
    reasons: list[str]
    details: dict[str, Any]

    def as_dict(self) -> dict[str, Any]:
        return {
            "gate_id": self.gate_id,
            "passed": self.passed,
            "severity": self.severity,
            "reasons": self.reasons,
            "details": self.details,
        }


def build_run_context(
    *,
    slot: str,
    topic: str,
    funnel_stage: str,
    stage_objective: str,
    audience_segment: str,
    campaign_id: str,
    destination_url: str,
    product_id: str,
    product_name: str,
    selected_hook: str,
    selected_cta: str,
    recent_hooks: list[str],
    recent_topics: list[str],
    recent_ctas: list[str],
) -> dict[str, Any]:
    return {
        "slot": str(slot or ""),
        "topic": str(topic or ""),
        "funnel_stage": str(funnel_stage or ""),
        "stage_objective": str(stage_objective or ""),
        "audience_segment": str(audience_segment or ""),
        "campaign_id": str(campaign_id or ""),
        "destination_url": str(destination_url or ""),
        "product": {
            "id": str(product_id or ""),
            "name": str(product_name or ""),
        },
        "draft_direction": {
            "selected_hook": str(selected_hook or ""),
            "selected_cta": str(selected_cta or ""),
        },
        "recency_windows": {
            "recent_hooks": [str(v) for v in recent_hooks if str(v).strip()],
            "recent_topics": [str(v) for v in recent_topics if str(v).strip()],
            "recent_ctas": [str(v) for v in recent_ctas if str(v).strip()],
        },
    }


def _type_ok(value: Any, expected: str) -> bool:
    if expected == "str":
        return isinstance(value, str)
    if expected == "bool":
        return isinstance(value, bool)
    if expected == "dict":
        return isinstance(value, dict)
    if expected == "list":
        return isinstance(value, list)
    if expected == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return False


def _validate(value: Any, spec: Any, path: str, errors: list[str]) -> None:
    if isinstance(spec, str):
        if not _type_ok(value, spec):
            errors.append(f"{path}: expected {spec}")
        return

    if isinstance(spec, dict):
        if "enum" in spec:
            choices = spec.get("enum", [])
            if value not in choices:
                errors.append(f"{path}: expected one of {choices}")
            return

        if "list_of" in spec:
            if not isinstance(value, list):
                errors.append(f"{path}: expected list")
                return
            child = spec.get("list_of")
            for idx, row in enumerate(value):
                _validate(row, child, f"{path}[{idx}]", errors)
            return

        required = spec.get("required")
        if required is not None:
            if not isinstance(value, dict):
                errors.append(f"{path}: expected dict")
                return
            for key, child_spec in required.items():
                if key not in value:
                    errors.append(f"{path}.{key}: missing")
                    continue
                _validate(value.get(key), child_spec, f"{path}.{key}", errors)
            return

    errors.append(f"{path}: invalid schema spec")


def validate_agent_output(agent_name: str, payload: Any) -> tuple[dict[str, Any], list[str]]:
    schema = AGENT_IO_SCHEMAS.get(agent_name)
    if not schema:
        return {}, [f"unknown_agent:{agent_name}"]
    if not isinstance(payload, dict):
        return {}, [f"agent_output:{agent_name}:expected dict"]

    normalized = deepcopy(payload)
    errors: list[str] = []
    _validate(normalized, schema, agent_name, errors)
    return normalized, errors


def build_gate_record(
    *,
    gate_id: str,
    passed: bool,
    severity: str,
    reasons: list[str],
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    record = GateRecord(
        gate_id=gate_id,
        passed=bool(passed),
        severity=str(severity or "error"),
        reasons=[str(r) for r in reasons if str(r).strip()],
        details=details or {},
    )
    return record.as_dict()


def evaluate_global_gates(gates: list[dict[str, Any]]) -> dict[str, Any]:
    blocking_failures = []
    for gate in gates:
        if not isinstance(gate, dict):
            continue
        if bool(gate.get("passed", False)):
            continue
        if str(gate.get("severity", "error")).lower() == "warning":
            continue
        blocking_failures.append(gate)

    return {
        "status": "pass" if not blocking_failures else "fail",
        "passed": len(blocking_failures) == 0,
        "blocking_failures": blocking_failures,
    }
