from __future__ import annotations

import io
import json
import os
import sys
from unittest.mock import patch


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "scripts"))

from verify_deployment import verify  # noqa: E402


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.close()


def test_verify_deployment_requires_exact_sha_and_no_blockers():
    payload = {"status": "ok", "deployment": {"build_sha": "abc123"}, "startup_validation": {"blockers": []}}
    encoded = json.dumps(payload).encode("utf-8")
    with patch("urllib.request.urlopen", side_effect=[_Response(encoded), _Response(encoded)]):
        assert verify("https://service.test", "abc123")["verified"] is True
        mismatch = verify("https://service.test", "other")
    assert mismatch["verified"] is False
    assert mismatch["errors"] == ["DEPLOYMENT_REVISION_MISMATCH"]


def test_verify_deployment_rejects_degraded_or_blocked_runtime():
    payload = {"status": "degraded", "deployment": {"build_sha": "abc123"}, "startup_validation": {"blockers": ["PLATFORM_CREDENTIALS_MISSING"]}}
    with patch("urllib.request.urlopen", return_value=_Response(json.dumps(payload).encode("utf-8"))):
        result = verify("https://service.test", "abc123")
    assert result["verified"] is False
    assert result["errors"] == ["HEALTH_NOT_READY", "PLATFORM_CREDENTIALS_MISSING"]