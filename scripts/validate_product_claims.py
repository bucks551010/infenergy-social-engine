from __future__ import annotations

import re
from typing import Any


_METRIC_PATTERN = re.compile(
    r"\b\d{1,3}(?:,\d{3})*(?:\.\d+)?\s?(?:Wh|mAh|W|kW|V|A|hours?|%)\b",
    flags=re.IGNORECASE,
)

_RUNTIME_PATTERN = re.compile(r"\b\d+(?:\.\d+)?\s?hours?\b", flags=re.IGNORECASE)
_PRICE_PATTERN = re.compile(r"\$\s?\d{1,4}(?:[\.,]\d{2})?", flags=re.IGNORECASE)


class ValidationResult(dict):
    @property
    def passed(self) -> bool:
        return bool(self.get("passed", False))


def _collect_text(content: dict[str, Any]) -> str:
    parts = [
        str(content.get("wp_content", "")),
        str(content.get("fb_caption", "")),
        str(content.get("ig_caption", "")),
        str(content.get("li_text", "")),
    ]
    return "\n".join(parts)


def _parse_numeric_tokens(text: str) -> set[str]:
    return {m.strip().lower() for m in _METRIC_PATTERN.findall(text or "")}


def _contains_testimonial_like_claim(text: str) -> bool:
    low = (text or "").lower()
    triggers = (
        "customer said",
        "customer review",
        "testimonial",
        "our client",
        "real customer story",
    )
    return any(t in low for t in triggers)


def validate_generated_content(content: dict[str, Any]) -> ValidationResult:
    """Validate product-bound claims before publishing.

    This is a conservative, rule-based validator intended to block risky
    content when product evidence is missing or mismatched.
    """

    errors: list[str] = []
    warnings: list[str] = []

    text = _collect_text(content)
    product_name = str(content.get("product_name", "")).strip()
    product_metrics = {str(x).strip().lower() for x in (content.get("product_metrics", []) or []) if str(x).strip()}
    product_facts = str(content.get("product_facts", "") or "")
    product_price = str(content.get("product_price", "") or "").strip()
    product_sale_price = str(content.get("product_sale_price", "") or "").strip()
    product_url = str(content.get("product_url", "") or content.get("destination_url", "")).strip()
    in_stock = str(content.get("product_in_stock", "") or "").strip().lower()

    if product_name:
        if not product_url:
            errors.append("product_url_missing")

        if in_stock in ("0", "false", "no", "outofstock", "out of stock"):
            errors.append("product_unavailable_or_out_of_stock")

        generated_metrics = _parse_numeric_tokens(text)
        for token in generated_metrics:
            if token not in product_metrics and token not in (product_facts or "").lower():
                if "wh" in token or "mah" in token:
                    errors.append(f"capacity_not_verified:{token}")
                elif "w" in token or "kw" in token:
                    errors.append(f"wattage_not_verified:{token}")
                elif "hour" in token:
                    errors.append(f"runtime_not_verified:{token}")
                else:
                    warnings.append(f"numeric_claim_not_verified:{token}")

        if _RUNTIME_PATTERN.search(text) and "hour" not in (product_facts or "").lower():
            errors.append("runtime_claim_not_supported")

        prices_mentioned = _PRICE_PATTERN.findall(text)
        valid_prices = set()
        if product_price:
            valid_prices.add(f"${product_price}")
        if product_sale_price:
            valid_prices.add(f"${product_sale_price}")
        if prices_mentioned and not valid_prices:
            errors.append("price_claim_without_product_price")
        if valid_prices:
            for p in prices_mentioned:
                norm = p.replace(" ", "")
                if norm not in {v.replace(' ', '') for v in valid_prices}:
                    errors.append(f"price_mismatch:{p}")

        low_text = text.lower()
        if "compatible with" in low_text and "compat" not in (product_facts or "").lower():
            errors.append("compatibility_not_verified")

        if _contains_testimonial_like_claim(text):
            errors.append("testimonial_or_customer_claim_unverified")

    passed = len(errors) == 0
    return ValidationResult(
        {
            "passed": passed,
            "errors": errors,
            "warnings": warnings,
            "hard_failure": not passed,
        }
    )
