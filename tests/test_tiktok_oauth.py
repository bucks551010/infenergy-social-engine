from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlparse

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import tiktok_oauth


@pytest.fixture
def oauth_env(tmp_path):
    values = {
        "DATA_DIR": str(tmp_path),
        "TIKTOK_CLIENT_KEY": "client-key",
        "TIKTOK_CLIENT_SECRET": "client-secret",
        "TIKTOK_REDIRECT_URI": "https://jubilant-harmony-production-5bd1.up.railway.app/api/auth/tiktok/callback",
        "TIKTOK_TOKEN_ENCRYPTION_KEY": "stable-test-encryption-key",
        "TIKTOK_ACCESS_TOKEN": "",
        "TIKTOK_REFRESH_TOKEN": "",
    }
    with patch.dict(os.environ, values, clear=False):
        yield tmp_path


def _token_payload(access="access-one", refresh="refresh-one", expires_in=86400):
    return {
        "access_token": access,
        "refresh_token": refresh,
        "expires_in": expires_in,
        "refresh_expires_in": 30 * 86400,
        "open_id": "creator-123",
        "scope": ",".join(tiktok_oauth.SCOPES),
    }


def test_connect_url_uses_exact_redirect_scopes_and_one_time_state(oauth_env):
    authorization = tiktok_oauth.create_authorization()
    parsed = urlparse(authorization["authorization_url"])
    query = parse_qs(parsed.query)

    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == tiktok_oauth.AUTHORIZE_URL
    assert query["redirect_uri"] == [os.environ["TIKTOK_REDIRECT_URI"]]
    assert query["scope"] == [",".join(tiktok_oauth.SCOPES)]
    assert query["response_type"] == ["code"]
    assert query["state"][0] not in (oauth_env / "marketing" / "tiktok_oauth_states.json").read_text(encoding="utf-8")

    tiktok_oauth.consume_state(query["state"][0])
    with pytest.raises(tiktok_oauth.TikTokOAuthError, match="already used"):
        tiktok_oauth.consume_state(query["state"][0])


def test_complete_authorization_persists_encrypted_tokens_and_safe_profile(oauth_env):
    token_response = Mock()
    token_response.raise_for_status.return_value = None
    token_response.json.return_value = _token_payload()
    user_response = Mock()
    user_response.raise_for_status.return_value = None
    user_response.json.return_value = {"data": {"user": {"open_id": "creator-123", "display_name": "Infenergy", "avatar_url": "https://example/avatar.jpg"}}}

    with patch.object(tiktok_oauth.requests, "post", return_value=token_response), patch.object(tiktok_oauth.requests, "get", return_value=user_response):
        status = tiktok_oauth.complete_authorization("single-use-code")

    stored_text = (oauth_env / "marketing" / "tiktok_account.json").read_text(encoding="utf-8")
    assert "access-one" not in stored_text
    assert "refresh-one" not in stored_text
    assert status["connected"] is True
    assert status["display_name"] == "Infenergy"
    serialized_status = json.dumps(status)
    assert "access-one" not in serialized_status
    assert "refresh-one" not in serialized_status
    assert "access_token_encrypted" not in status
    assert "refresh_token_encrypted" not in status
    account = tiktok_oauth.load_account(include_tokens=True)
    assert account["access_token"] == "access-one"
    assert account["refresh_token"] == "refresh-one"


def test_expiring_access_token_refreshes_and_persists_rotated_refresh_token(oauth_env):
    tiktok_oauth.persist_tokens(_token_payload(expires_in=1), {"display_name": "Infenergy"})
    refresh_response = Mock()
    refresh_response.raise_for_status.return_value = None
    refresh_response.json.return_value = _token_payload("access-two", "refresh-two")

    with patch.object(tiktok_oauth.requests, "post", return_value=refresh_response) as post:
        assert tiktok_oauth.access_token() == "access-two"

    assert post.call_args.args[0] == tiktok_oauth.TOKEN_URL
    assert post.call_args.kwargs["data"]["refresh_token"] == "refresh-one"
    account = tiktok_oauth.load_account(include_tokens=True)
    assert account["access_token"] == "access-two"
    assert account["refresh_token"] == "refresh-two"


def test_expired_state_is_rejected(oauth_env):
    raw_state = "expired-state"
    digest = __import__("hashlib").sha256(raw_state.encode("utf-8")).hexdigest()
    path = oauth_env / "marketing" / "tiktok_oauth_states.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({digest: {"expires_at": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()}}), encoding="utf-8")

    with pytest.raises(tiktok_oauth.TikTokOAuthError, match="Expired"):
        tiktok_oauth.consume_state(raw_state)


def test_disconnect_revokes_then_removes_local_credentials(oauth_env):
    tiktok_oauth.persist_tokens(_token_payload(), {"display_name": "Infenergy"})
    response = Mock()
    response.raise_for_status.return_value = None

    with patch.object(tiktok_oauth.requests, "post", return_value=response) as post:
        status = tiktok_oauth.disconnect()

    assert post.call_args.args[0] == tiktok_oauth.REVOKE_URL
    assert status["status"] == "NOT_CONNECTED"
    assert status["connected"] is False
    assert tiktok_oauth.load_account() is None
