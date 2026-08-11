"""Business Intelligence Foundation (Master Build).

Living, evolving business world model that sits underneath every social
system. Public entry points live in :mod:`business_intelligence.api`.

Enabled explicitly by setting ``ENABLE_BUSINESS_INTELLIGENCE=1``. Import
alone is safe; nothing runs until an API function is called.
"""

from __future__ import annotations

import os

__all__ = [
    "api",
    "bootstrap",
    "compilers",
    "conference",
    "evidence",
    "offerings",
    "audience",
    "brand",
    "social_mandate",
    "research",
    "learning",
    "profile",
    "critic",
    "schemas",
    "sources",
    "paths",
    "information_types",
    "is_enabled",
]


def is_enabled() -> bool:
    return os.environ.get("ENABLE_BUSINESS_INTELLIGENCE", "").lower() in {"1", "true", "yes", "on"}
