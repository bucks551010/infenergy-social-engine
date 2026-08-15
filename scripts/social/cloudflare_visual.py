"""Cloudflare Workers AI implementation of the normalized image-provider contract."""

from __future__ import annotations

import base64
import io
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests


MODEL = "@cf/black-forest-labs/flux-2-klein-9b"
FIRST_OUTPUT_MP_NEURONS = 1363.64
ADDITIONAL_MP_NEURONS = 181.82
INPUT_MP_NEURONS = 181.82
FREE_DAILY_LIMIT_DEFAULT = 9000.0
MAX_DAILY_REQUESTS = 5
MAX_REFERENCES = 4


def _data_dir() -> Path:
    return Path(os.environ.get("DATA_DIR", Path(__file__).resolve().parents[2] / "data"))


def _ledger_path() -> Path:
    return _data_dir() / "social" / "cloudflare_neuron_ledger.json"


def _utc_day() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def estimate_neurons(width: int, height: int, reference_sizes: list[tuple[int, int]] | None = None) -> dict[str, float]:
    output_mp = (width * height) / 1_000_000
    output_neurons = FIRST_OUTPUT_MP_NEURONS + max(0.0, output_mp - 1.0) * ADDITIONAL_MP_NEURONS
    reference_mp = sum((ref_width * ref_height) / 1_000_000 for ref_width, ref_height in (reference_sizes or []))
    return {
        "output_mp": round(output_mp, 6),
        "reference_input_mp": round(reference_mp, 6),
        "estimated_neurons": round(output_neurons + reference_mp * INPUT_MP_NEURONS, 2),
    }


def _load_ledger() -> dict[str, Any]:
    try:
        data = json.loads(_ledger_path().read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_ledger(data: dict[str, Any]) -> None:
    path = _ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    temporary.replace(path)


def reserve_budget(*, width: int, height: int, reference_sizes: list[tuple[int, int]], retry_number: int) -> tuple[bool, dict[str, Any]]:
    estimate = estimate_neurons(width, height, reference_sizes)
    cap = float(os.environ.get("FREE_AI_DAILY_NEURON_LIMIT", FREE_DAILY_LIMIT_DEFAULT))
    day = _utc_day()
    ledger = _load_ledger()
    daily = ledger.get(day) if isinstance(ledger.get(day), dict) else {"estimated_neurons": 0.0, "requests": 0, "entries": []}
    before = float(daily.get("estimated_neurons", 0.0))
    request_count = int(daily.get("requests", 0))
    if request_count >= MAX_DAILY_REQUESTS:
        return False, {**estimate, "reason": "FREE_AI_DAILY_REQUEST_LIMIT", "daily_estimated_neurons_before": before, "daily_estimated_neurons_after": before}
    if before + estimate["estimated_neurons"] > cap:
        return False, {**estimate, "reason": "FREE_AI_BUDGET_EXHAUSTED", "daily_estimated_neurons_before": before, "daily_estimated_neurons_after": before}
    after = round(before + estimate["estimated_neurons"], 2)
    entry = {
        "at_utc": datetime.now(timezone.utc).isoformat(),
        "provider": "cloudflare",
        "model": MODEL,
        "width": width,
        "height": height,
        "reference_count": len(reference_sizes),
        "retry_number": retry_number,
        "paid_api_used": False,
        **estimate,
        "daily_estimated_neurons_before": before,
        "daily_estimated_neurons_after": after,
    }
    daily.update({"estimated_neurons": after, "requests": request_count + 1, "entries": [*(daily.get("entries") or []), entry][-30:]})
    ledger[day] = daily
    _save_ledger(ledger)
    return True, entry


def normalize_reference(raw: bytes) -> tuple[bytes, tuple[int, int]] | None:
    """Convert a reference to a sub-512px JPEG without changing its content."""
    try:
        from PIL import Image

        image = Image.open(io.BytesIO(raw)).convert("RGB")
        image.thumbnail((511, 511), Image.Resampling.LANCZOS)
        output = io.BytesIO()
        image.save(output, format="JPEG", quality=88, optimize=True)
        return output.getvalue(), image.size
    except Exception:
        return None


def generate(*, prompt: str, output_path: str, width: int, height: int, references: list[bytes], retry_number: int = 0) -> tuple[bool, str, dict[str, Any]]:
    account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID", "").strip()
    token = os.environ.get("CLOUDFLARE_API_TOKEN", "").strip()
    metadata: dict[str, Any] = {
        "visual_generation_attempted": True,
        "visual_generation_mode": "cloudflare_generated",
        "visual_provider": "cloudflare",
        "visual_model": os.environ.get("CLOUDFLARE_IMAGE_MODEL", MODEL).strip() or MODEL,
        "width": width,
        "height": height,
        "retry_number": retry_number,
        "paid_api_used": False,
        "cost_mode": os.environ.get("GENERATION_COST_MODE", "AUTO").strip().upper(),
    }
    if not account_id or not token:
        return False, "FREE_AI_PROVIDER_NOT_CONFIGURED", metadata
    model = metadata["visual_model"]
    if model != MODEL:
        return False, "FREE_AI_MODEL_NOT_ALLOWED", metadata

    normalized = [item for item in (normalize_reference(raw) for raw in references[:MAX_REFERENCES]) if item]
    reference_sizes = [size for _, size in normalized]
    permitted, provenance = reserve_budget(width=width, height=height, reference_sizes=reference_sizes, retry_number=retry_number)
    metadata.update(provenance)
    if not permitted:
        return False, str(provenance["reason"]), metadata

    files: list[tuple[str, tuple[str, bytes, str]]] = []
    for index, (raw, _) in enumerate(normalized):
        files.append((f"input_image_{index}", (f"reference_{index}.jpg", raw, "image/jpeg")))
    try:
        response = requests.post(
            f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}",
            headers={"Authorization": f"Bearer {token}"},
            data={"prompt": prompt, "width": str(width), "height": str(height)},
            files=files,
            timeout=180,
        )
        metadata["provider_http_status"] = response.status_code
        if not response.ok:
            body = " ".join(response.text.split())[:240].replace(token, "[redacted]").replace(account_id, "[redacted_account]")
            if response.status_code == 429 or any(token in body.lower() for token in ("quota", "allocation", "limit", "paid")):
                return False, "FREE_AI_PROVIDER_LIMIT", metadata | {"provider_error_message_sanitized": body}
            return False, f"cloudflare_http_{response.status_code}", metadata | {"provider_error_message_sanitized": body}
        payload = response.json()
        raw_image = base64.b64decode(str((payload.get("result") or {}).get("image") or ""), validate=True)
        if not raw_image:
            return False, "cloudflare_empty_image", metadata
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_bytes(raw_image)
        metadata.update({"artifact_path": output_path, "artifact_exists": True, "artifact_size": len(raw_image), "generation_status": "success"})
        return True, "ok", metadata
    except Exception as exc:
        return False, f"cloudflare_exception:{type(exc).__name__}", metadata | {"generation_status": "failed"}