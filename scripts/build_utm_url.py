from __future__ import annotations

from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse


def _validate_url(base_url: str) -> tuple[bool, str]:
    try:
        parsed = urlparse(base_url)
    except Exception:
        return False, "url_parse_error"

    if parsed.scheme not in ("http", "https"):
        return False, "url_scheme_not_supported"
    if not parsed.netloc:
        return False, "url_missing_host"
    return True, "ok"


def build_utm_url(
    base_url: str,
    *,
    source: str,
    campaign: str,
    content: str,
    term: str,
    medium: str = "organic_social",
) -> dict[str, Any]:
    """Build a UTM URL while preserving existing query parameters.

    Returns a dict containing both original and final URL and validation state.
    """

    base = (base_url or "").strip()
    ok, reason = _validate_url(base)
    if not ok:
        return {
            "ok": False,
            "reason": reason,
            "original_url": base,
            "utm_url": base,
        }

    parsed = urlparse(base)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.update(
        {
            "utm_source": (source or "").strip(),
            "utm_medium": (medium or "organic_social").strip() or "organic_social",
            "utm_campaign": (campaign or "").strip(),
            "utm_content": (content or "").strip(),
            "utm_term": (term or "").strip(),
        }
    )

    final_url = urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            urlencode(query),
            parsed.fragment,
        )
    )

    ok2, reason2 = _validate_url(final_url)
    return {
        "ok": ok2,
        "reason": reason2,
        "original_url": base,
        "utm_url": final_url,
    }
