"""Shared SSRF-guard helper for code paths that fetch attacker/DB-influenced URLs.

Used by social_visuals.py, publish_instagram.py, and publish_linkedin.py before
issuing an outbound `requests.get`/`requests.head` for a product/candidate image
URL, to avoid fetching internal/private network targets (e.g. cloud metadata
endpoints, localhost, RFC1918 ranges).
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlparse


def is_safe_http_url(url: str) -> bool:
    """Return True if `url` is an http(s) URL whose host does not resolve to a
    private/loopback/link-local/reserved address.

    Fails open (returns True) if the host cannot be resolved at all, so that
    transient DNS issues do not silently break legitimate fetches; the
    subsequent `requests.get` call will fail naturally in that case.
    """
    try:
        parsed = urlparse(str(url or "").strip())
    except Exception:
        return False

    if parsed.scheme not in ("http", "https"):
        return False

    hostname = parsed.hostname
    if not hostname:
        return False

    try:
        infos = socket.getaddrinfo(hostname, None)
    except Exception:
        return True

    for info in infos:
        ip_str = info[4][0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if (
            ip.is_private
            or ip.is_loopback
            or ip.is_link_local
            or ip.is_reserved
            or ip.is_multicast
            or ip.is_unspecified
        ):
            return False

    return True
