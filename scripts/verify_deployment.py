"""Verify that a deployment is healthy and running the expected immutable revision."""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request


def verify(base_url: str, expected_sha: str, *, timeout_seconds: int = 20) -> dict:
    request = urllib.request.Request(f"{base_url.rstrip('/')}/health", headers={"User-Agent": "Infenergy-Deploy-Verifier/1.0"})
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        payload = json.load(response)
    deployment = payload.get("deployment") if isinstance(payload.get("deployment"), dict) else {}
    validation = payload.get("startup_validation") if isinstance(payload.get("startup_validation"), dict) else {}
    running_sha = str(deployment.get("build_sha") or "")
    blockers = validation.get("blockers") if isinstance(validation.get("blockers"), list) else []
    errors = []
    if str(payload.get("status") or "").lower() not in {"ok", "healthy"}:
        errors.append("HEALTH_NOT_READY")
    if blockers:
        errors.extend(str(item) for item in blockers)
    if not expected_sha or running_sha != expected_sha:
        errors.append("DEPLOYMENT_REVISION_MISMATCH")
    return {"verified": not errors, "expected_sha": expected_sha, "running_sha": running_sha, "errors": list(dict.fromkeys(errors))}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--expected-sha", required=True)
    arguments = parser.parse_args()
    result = verify(arguments.url, arguments.expected_sha)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["verified"] else 1


if __name__ == "__main__":
    sys.exit(main())