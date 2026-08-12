"""Market conversation, whitespace, positioning, edge, and angle decisions."""
from __future__ import annotations

from collections import Counter
from typing import Any


def conversation(competitors: dict[str, Any], consumers: list[dict[str, Any]]) -> dict[str, list[str]]:
    values = list(competitors.values())
    messages = Counter(item for row in values for item in row.get("messages", []))
    benefits = Counter(item for row in values for item in row.get("benefits", []))
    questions = Counter(item for row in values for item in row.get("questions", []))
    consumer_questions = {str(row.get("question", "")) for row in consumers if row.get("question")}
    return {
        "dominant_messages": list(messages), "saturated_benefits": [key for key, count in benefits.items() if count > 1],
        "common_questions": list(questions), "unresolved_questions": sorted(consumer_questions - set(questions)),
        "underrepresented_customer_moments": sorted({str(row.get("customer_moment")) for row in consumers} - {item for row in values for item in row.get("customer_moments", [])}),
        "visual_saturation": list({item for row in values for item in row.get("visual_patterns", [])}),
    }


def whitespace(*, conversation_map: dict[str, list[str]], business_personality: str, capability: str) -> dict[str, str]:
    question = next(iter(conversation_map.get("unresolved_questions", [])), "")
    moment = next(iter(conversation_map.get("underrepresented_customer_moments", [])), "")
    return {"content_whitespace": question, "customer_moment_whitespace": moment,
            "positioning_whitespace": f"{business_personality}: {capability}" if (question or moment) and capability else ""}


def positioning(*, whitespace_result: dict[str, str], business_personality: str, offering_truth: list[str], audience_importance: float) -> dict[str, Any]:
    territory = whitespace_result.get("positioning_whitespace", "")
    score = round((0.3 if territory else 0) + (0.3 if offering_truth else 0) + (0.4 * audience_importance), 2)
    return {"territory": territory, "score": score, "credible": bool(territory and offering_truth),
            "rationale": "matches business personality, a customer gap, and supported offering truth" if territory and offering_truth else "insufficient support"}


def non_price_edge(*, customer: dict[str, Any], capability: str, benefit: str, evidence: list[dict[str, Any]], competitor_context: str = "") -> dict[str, Any]:
    support = [item for item in evidence if item.get("confidence", 0) >= 0.6]
    if capability and benefit and support:
        return {"edge_type": "PRODUCT_EDGE", "edge": f"{capability} supports {benefit}", "customer": customer.get("audience", ""), "customer_moment": customer.get("customer_moment", ""), "competitor_context": competitor_context, "support": support, "confidence": min(item["confidence"] for item in support), "claim_limit": "Use only supported capability language", "how_to_use_in_content": "Connect the supported capability to the customer's active moment."}
    return {"edge_type": "NO_DEFENSIBLE_EDGE", "edge": "", "customer": customer.get("audience", ""), "customer_moment": customer.get("customer_moment", ""), "competitor_context": competitor_context, "support": [], "confidence": 0.0, "claim_limit": "Do not imply superiority", "how_to_use_in_content": "Choose education or do not generate."}


def angles(*, customer: dict[str, Any], positioning_result: dict[str, Any], edge: dict[str, Any], why_now: str, limit: int = 3) -> list[dict[str, Any]]:
    if not positioning_result.get("credible"):
        return []
    base = {"audience": customer.get("audience", ""), "customer_moment": customer.get("customer_moment", ""), "human_need": customer.get("human_need", ""), "offering": customer.get("offering", ""), "positioning": positioning_result["territory"], "non_price_edge": edge, "why_now": why_now}
    topic = customer.get("question") or customer.get("topic") or customer.get("human_need")
    variants = [(f"Explain {topic}", f"Know what matters before choosing {customer.get('offering', 'a solution')}"), (f"Show the decision behind {topic}", "Make the next step clearer, not louder"), (f"Prepare for {customer.get('customer_moment', 'the moment')} before it happens", "Preparation begins with a clearer next step"), (f"Compare what matters for {topic}", "Use the right question before choosing")]
    return [base | {"angle": angle, "reader_memory": memory} for angle, memory in variants[:max(1, limit)]]