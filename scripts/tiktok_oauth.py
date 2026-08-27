from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import requests
from cryptography.fernet import Fernet, InvalidToken

AUTHORIZE_URL = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN_URL = "https://open.tiktokapis.com/v2/oauth/token/"
USER_INFO_URL = "https://open.tiktokapis.com/v2/user/info/"
CREATOR_INFO_URL = "https://open.tiktokapis.com/v2/post/publish/creator_info/query/"
REVOKE_URL = "https://open.tiktokapis.com/v2/oauth/revoke/"
SCOPES = ("user.info.basic", "video.upload", "video.publish")
STATE_TTL_MINUTES = 10
TOKEN_REFRESH_SKEW_SECONDS = 300
_LOCK = threading.RLock()


class TikTokOAuthError(RuntimeError):
    pass


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _configured(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value or value.upper() in {"REPLACE_ME", "SET_ME"}:
        raise TikTokOAuthError(f"TikTok configuration is incomplete: {name}")
    return value


def _data_dir() -> Path:
    return Path(os.environ.get("DATA_DIR", Path(__file__).resolve().parents[1] / "data"))


def _state_path() -> Path:
    return _data_dir() / "marketing" / "tiktok_oauth_states.json"


def _account_path() -> Path:
    return _data_dir() / "marketing" / "tiktok_account.json"


def _read_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError):
        return default


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def _cipher() -> Fernet:
    secret = _configured("TIKTOK_TOKEN_ENCRYPTION_KEY")
    key = base64.urlsafe_b64encode(hashlib.sha256(secret.encode("utf-8")).digest())
    return Fernet(key)


def _encrypt(value: str) -> str:
    return _cipher().encrypt(value.encode("utf-8")).decode("ascii")


def _decrypt(value: str) -> str:
    try:
        return _cipher().decrypt(value.encode("ascii")).decode("utf-8")
    except (InvalidToken, ValueError) as exc:
        raise TikTokOAuthError("TikTok credentials require reauthorization") from exc


def client_configuration() -> dict[str, str]:
    return {
        "client_key": _configured("TIKTOK_CLIENT_KEY"),
        "client_secret": _configured("TIKTOK_CLIENT_SECRET"),
    }


def configuration() -> dict[str, str]:
    return {
        **client_configuration(),
        "redirect_uri": _configured("TIKTOK_REDIRECT_URI"),
    }


def create_authorization() -> dict[str, Any]:
    config = configuration()
    if not config["redirect_uri"].startswith("https://"):
        raise TikTokOAuthError("TikTok redirect URI must use HTTPS")
    raw_state = secrets.token_urlsafe(32)
    state_digest = hashlib.sha256(raw_state.encode("utf-8")).hexdigest()
    now = _utc_now()
    expires_at = now + timedelta(minutes=STATE_TTL_MINUTES)
    with _LOCK:
        records = _read_json(_state_path(), {})
        if not isinstance(records, dict):
            records = {}
        records = {
            key: value for key, value in records.items()
            if isinstance(value, dict) and str(value.get("expires_at") or "") > _iso(now)
        }
        records[state_digest] = {"created_at": _iso(now), "expires_at": _iso(expires_at)}
        _write_json(_state_path(), records)
    query = urlencode({
        "client_key": config["client_key"],
        "scope": ",".join(SCOPES),
        "response_type": "code",
        "redirect_uri": config["redirect_uri"],
        "state": raw_state,
    })
    return {"authorization_url": f"{AUTHORIZE_URL}?{query}", "expires_at": _iso(expires_at)}


def consume_state(raw_state: str) -> None:
    if not raw_state:
        raise TikTokOAuthError("Missing OAuth state")
    digest = hashlib.sha256(raw_state.encode("utf-8")).hexdigest()
    with _LOCK:
        records = _read_json(_state_path(), {})
        record = records.pop(digest, None) if isinstance(records, dict) else None
        _write_json(_state_path(), records if isinstance(records, dict) else {})
    if not isinstance(record, dict):
        raise TikTokOAuthError("Invalid or already used OAuth state")
    try:
        expires_at = datetime.fromisoformat(str(record["expires_at"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise TikTokOAuthError("Invalid OAuth state") from exc
    if expires_at <= _utc_now():
        raise TikTokOAuthError("Expired OAuth state")


def _token_payload(response: requests.Response) -> dict[str, Any]:
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or not str(payload.get("access_token") or "").strip():
        raise TikTokOAuthError("TikTok token request failed")
    return payload


def exchange_code(code: str) -> dict[str, Any]:
    if not code:
        raise TikTokOAuthError("Missing authorization code")
    config = configuration()
    try:
        response = requests.post(
            TOKEN_URL,
            data={
                "client_key": config["client_key"],
                "client_secret": config["client_secret"],
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": config["redirect_uri"],
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30,
        )
        return _token_payload(response)
    except (requests.RequestException, ValueError) as exc:
        raise TikTokOAuthError("TikTok authorization could not be completed") from exc


def fetch_user(access_token: str) -> dict[str, Any]:
    try:
        response = requests.get(
            USER_INFO_URL,
            params={"fields": "open_id,display_name,avatar_url"},
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        data = payload.get("data") if isinstance(payload, dict) else {}
        user = data.get("user") if isinstance(data, dict) else {}
        return user if isinstance(user, dict) else {}
    except (requests.RequestException, ValueError):
        return {}


def persist_tokens(payload: dict[str, Any], user: dict[str, Any] | None = None) -> dict[str, Any]:
    now = _utc_now()
    access_token = str(payload.get("access_token") or "").strip()
    refresh_token = str(payload.get("refresh_token") or "").strip()
    if not access_token or not refresh_token:
        raise TikTokOAuthError("TikTok did not return durable credentials")
    expires_in = max(0, int(payload.get("expires_in") or 0))
    refresh_expires_in = max(0, int(payload.get("refresh_expires_in") or 0))
    current = load_account(include_tokens=False) or {}
    profile = user if isinstance(user, dict) else {}
    record = {
        "platform": "tiktok",
        "status": "CONNECTED",
        "open_id": str(payload.get("open_id") or profile.get("open_id") or current.get("open_id") or ""),
        "display_name": str(profile.get("display_name") or current.get("display_name") or ""),
        "avatar_url": str(profile.get("avatar_url") or current.get("avatar_url") or ""),
        "scope": str(payload.get("scope") or current.get("scope") or ""),
        "access_token_encrypted": _encrypt(access_token),
        "refresh_token_encrypted": _encrypt(refresh_token),
        "access_token_expires_at": _iso(now + timedelta(seconds=expires_in)),
        "refresh_token_expires_at": _iso(now + timedelta(seconds=refresh_expires_in)),
        "connected_at": str(current.get("connected_at") or _iso(now)),
        "updated_at": _iso(now),
        "last_error": None,
    }
    with _LOCK:
        _write_json(_account_path(), record)
    return public_status(record)


def load_account(*, include_tokens: bool = False) -> dict[str, Any] | None:
    with _LOCK:
        record = _read_json(_account_path(), None)
    if not isinstance(record, dict) or record.get("status") != "CONNECTED":
        return None
    if include_tokens:
        record = dict(record)
        record["access_token"] = _decrypt(str(record.get("access_token_encrypted") or ""))
        record["refresh_token"] = _decrypt(str(record.get("refresh_token_encrypted") or ""))
    return record


def public_status(record: dict[str, Any] | None = None) -> dict[str, Any]:
    account = record if isinstance(record, dict) else load_account(include_tokens=False)
    if not account:
        return {"platform": "tiktok", "status": "NOT_CONNECTED", "connected": False}
    status = str(account.get("status") or "ERROR")
    try:
        refresh_expiry = datetime.fromisoformat(str(account.get("refresh_token_expires_at") or ""))
        if refresh_expiry <= _utc_now():
            status = "REAUTHORIZATION_REQUIRED"
    except ValueError:
        status = "ERROR"
    return {
        "platform": "tiktok",
        "status": status,
        "connected": status == "CONNECTED",
        "open_id": account.get("open_id"),
        "display_name": account.get("display_name"),
        "avatar_url": account.get("avatar_url"),
        "scope": account.get("scope"),
        "connected_at": account.get("connected_at"),
        "access_token_expires_at": account.get("access_token_expires_at"),
        "refresh_token_expires_at": account.get("refresh_token_expires_at"),
        "last_error": account.get("last_error"),
    }


def _mark_reauthorization_required() -> None:
    with _LOCK:
        record = _read_json(_account_path(), None)
        if not isinstance(record, dict):
            return
        record["status"] = "REAUTHORIZATION_REQUIRED"
        record["last_error"] = "TikTok authorization must be renewed"
        record["updated_at"] = _iso(_utc_now())
        _write_json(_account_path(), record)


def complete_authorization(code: str) -> dict[str, Any]:
    payload = exchange_code(code)
    access_token = str(payload.get("access_token") or "")
    user = fetch_user(access_token)
    return persist_tokens(payload, user)


def _refresh(refresh_token: str) -> dict[str, Any]:
    config = client_configuration()
    try:
        response = requests.post(
            TOKEN_URL,
            data={
                "client_key": config["client_key"],
                "client_secret": config["client_secret"],
                "refresh_token": refresh_token,
                "grant_type": "refresh_token",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=30,
        )
        return _token_payload(response)
    except (requests.RequestException, ValueError) as exc:
        raise TikTokOAuthError("TikTok credentials require reauthorization") from exc


def access_token() -> str:
    account = load_account(include_tokens=True)
    if account:
        try:
            expires_at = datetime.fromisoformat(str(account.get("access_token_expires_at") or ""))
        except ValueError:
            expires_at = _utc_now()
        if expires_at > _utc_now() + timedelta(seconds=TOKEN_REFRESH_SKEW_SECONDS):
            return str(account["access_token"])
        try:
            payload = _refresh(str(account["refresh_token"]))
        except TikTokOAuthError:
            _mark_reauthorization_required()
            raise
        if not payload.get("refresh_token"):
            payload["refresh_token"] = account["refresh_token"]
        if not payload.get("refresh_expires_in"):
            refresh_expiry = datetime.fromisoformat(str(account["refresh_token_expires_at"]))
            payload["refresh_expires_in"] = max(0, int((refresh_expiry - _utc_now()).total_seconds()))
        if not payload.get("open_id"):
            payload["open_id"] = account.get("open_id")
        if not payload.get("scope"):
            payload["scope"] = account.get("scope")
        persist_tokens(payload, account)
        return str(payload["access_token"])
    configured = os.environ.get("TIKTOK_ACCESS_TOKEN", "").strip()
    if configured and configured.upper() not in {"REPLACE_ME", "SET_ME"}:
        return configured
    refresh_token = _configured("TIKTOK_REFRESH_TOKEN")
    payload = _refresh(refresh_token)
    return str(payload["access_token"])


def creator_info(token: str | None = None) -> dict[str, Any]:
    try:
        response = requests.post(
            CREATOR_INFO_URL,
            headers={"Authorization": f"Bearer {token or access_token()}", "Content-Type": "application/json; charset=UTF-8"},
            json={},
            timeout=30,
        )
        response.raise_for_status()
        payload = response.json()
        error = payload.get("error") if isinstance(payload, dict) else {}
        if isinstance(error, dict) and str(error.get("code") or "ok") != "ok":
            raise TikTokOAuthError("TikTok creator settings are unavailable")
        data = payload.get("data") if isinstance(payload, dict) else {}
        return data if isinstance(data, dict) else {}
    except (requests.RequestException, ValueError) as exc:
        raise TikTokOAuthError("TikTok creator settings are unavailable") from exc


def disconnect() -> dict[str, Any]:
    account = load_account(include_tokens=True)
    revoke_warning = None
    if account:
        try:
            config = client_configuration()
            response = requests.post(
                REVOKE_URL,
                data={
                    "client_key": config["client_key"],
                    "client_secret": config["client_secret"],
                    "token": account["access_token"],
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                timeout=30,
            )
            response.raise_for_status()
        except (requests.RequestException, TikTokOAuthError):
            revoke_warning = "TikTok revoke could not be confirmed; local credentials were removed"
    with _LOCK:
        try:
            _account_path().unlink()
        except FileNotFoundError:
            pass
    return {"platform": "tiktok", "status": "NOT_CONNECTED", "connected": False, "warning": revoke_warning}
