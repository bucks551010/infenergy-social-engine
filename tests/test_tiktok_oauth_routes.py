from __future__ import annotations

import os
import sys
import threading
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

import requests
import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

import tiktok_oauth
from worker import HealthHandler, ThreadingHTTPServer


@pytest.fixture
def oauth_server(tmp_path):
    environment = {
        "DATA_DIR": str(tmp_path),
        "INTELLIGENCE_OS_TOKEN": "owner-token",
        "TIKTOK_CLIENT_KEY": "client-key",
        "TIKTOK_CLIENT_SECRET": "client-secret",
        "TIKTOK_REDIRECT_URI": "https://jubilant-harmony-production-5bd1.up.railway.app/api/auth/tiktok/callback",
        "TIKTOK_TOKEN_ENCRYPTION_KEY": "stable-test-encryption-key",
    }
    with patch.dict(os.environ, environment, clear=False):
        server = ThreadingHTTPServer(("127.0.0.1", 0), HealthHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            yield f"http://127.0.0.1:{server.server_port}"
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)


def _headers():
    return {"Authorization": "Bearer owner-token"}


def test_connect_requires_owner_auth_and_returns_exact_login_kit_url(oauth_server):
    unauthorized = requests.get(f"{oauth_server}/api/auth/tiktok/connect?format=json", timeout=5)
    assert unauthorized.status_code == 401

    response = requests.get(f"{oauth_server}/api/auth/tiktok/connect?format=json", headers=_headers(), timeout=5)
    assert response.status_code == 200
    payload = response.json()
    query = parse_qs(urlparse(payload["authorization_url"]).query)
    assert query["redirect_uri"] == [os.environ["TIKTOK_REDIRECT_URI"]]
    assert query["scope"] == [",".join(tiktok_oauth.SCOPES)]
    assert "token" not in payload


def test_callback_consumes_state_once_and_returns_no_credentials(oauth_server):
    authorization = requests.get(f"{oauth_server}/api/auth/tiktok/connect?format=json", headers=_headers(), timeout=5).json()
    state = parse_qs(urlparse(authorization["authorization_url"]).query)["state"][0]
    connected = {"platform": "tiktok", "status": "CONNECTED", "connected": True}

    with patch.object(tiktok_oauth, "complete_authorization", return_value=connected):
        callback = requests.get(
            f"{oauth_server}/api/auth/tiktok/callback",
            params={"code": "single-use-code", "state": state},
            allow_redirects=False,
            timeout=5,
        )
        replay = requests.get(
            f"{oauth_server}/api/auth/tiktok/callback",
            params={"code": "single-use-code", "state": state},
            allow_redirects=False,
            timeout=5,
        )

    assert callback.status_code == 302
    assert callback.headers["Location"] == "/os?view=social&tiktok=connected"
    assert replay.status_code == 400
    assert "single-use-code" not in replay.text
    assert "owner-token" not in replay.text


def test_status_and_disconnect_are_protected_and_secret_free(oauth_server):
    safe_status = {"platform": "tiktok", "status": "CONNECTED", "connected": True, "display_name": "Infenergy"}
    disconnected = {"platform": "tiktok", "status": "NOT_CONNECTED", "connected": False, "warning": None}
    with patch.object(tiktok_oauth, "public_status", return_value=safe_status), patch.object(tiktok_oauth, "disconnect", return_value=disconnected):
        status = requests.get(f"{oauth_server}/api/auth/tiktok/status", headers=_headers(), timeout=5)
        unauthorized_disconnect = requests.post(f"{oauth_server}/api/auth/tiktok/disconnect", json={}, timeout=5)
        disconnect = requests.post(f"{oauth_server}/api/auth/tiktok/disconnect", headers=_headers(), json={}, timeout=5)

    assert status.status_code == 200
    assert status.json() == safe_status
    assert unauthorized_disconnect.status_code == 401
    assert disconnect.status_code == 200
    assert disconnect.json() == disconnected
    assert "owner-token" not in status.text + disconnect.text
