import os
import sys
import time
import json
import threading
import subprocess
import traceback
from urllib.parse import urlparse, parse_qs
import schedule
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from datetime import datetime, timezone, timedelta
import glob

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "scripts"))

import run_engine
import generate_posts
from campaign_runtime import eligible_channels_for_slot, load_channel_schedule, load_funnel_config, stage_for_slot

RUN_LOCK = threading.Lock()
LAST_RUN = {
    "status": "idle",
    "slot": None,
    "started_at_utc": None,
    "finished_at_utc": None,
    "error": None,
}
STARTED_AT = datetime.now(timezone.utc)


def _data_dir() -> str:
    return os.environ.get("DATA_DIR", os.path.join(os.path.dirname(__file__), "data"))


def _load_json(path: str, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _load_history(limit: int = 20) -> list[dict]:
    history_path = os.path.join(_data_dir(), "post_history.json")
    history = _load_json(history_path, {"posts": []})
    posts = history.get("posts", []) if isinstance(history, dict) else []
    if not isinstance(posts, list):
        return []
    return posts[-limit:]


def _latest_file(pattern: str) -> str:
    paths = glob.glob(pattern)
    if not paths:
        return ""
    return max(paths, key=os.path.getmtime)


def _load_latest_campaign_plan() -> dict:
    pattern = os.path.join(_data_dir(), "marketing", "campaign_plan_*.json")
    latest = _latest_file(pattern)
    if not latest:
        return {}
    data = _load_json(latest, {})
    if isinstance(data, dict):
        data["_artifact"] = latest
    return data if isinstance(data, dict) else {}


def _load_latest_structured_campaign() -> dict:
    pattern = os.path.join(_data_dir(), "marketing", "campaigns", "campaign_*.json")
    latest = _latest_file(pattern)
    if not latest:
        return {}
    data = _load_json(latest, {})
    if isinstance(data, dict):
        data["_artifact"] = latest
    return data if isinstance(data, dict) else {}


def _quality_summary(posts: list[dict]) -> dict:
    scores = [p.get("quality_score") for p in posts if isinstance(p.get("quality_score"), (int, float))]
    avg = round(sum(scores) / len(scores), 2) if scores else None
    warning_count = sum(len(p.get("quality_warnings", []) or []) for p in posts if isinstance(p, dict))
    return {
        "samples": len(scores),
        "average_quality_score": avg,
        "quality_warning_count": warning_count,
    }


def _quality_report(posts: list[dict]) -> dict:
    scores = [float(p.get("quality_score")) for p in posts if isinstance(p.get("quality_score"), (int, float))]
    rejected = [p for p in posts if isinstance(p, dict) and str(p.get("status", "")).startswith("skipped_")]

    reason_counts: dict[str, int] = {}
    platform_counts: dict[str, int] = {}
    stage_counts: dict[str, int] = {}

    for p in posts:
        if not isinstance(p, dict):
            continue
        stage = str(p.get("funnel_stage", "")).strip().upper()
        if stage:
            stage_counts[stage] = stage_counts.get(stage, 0) + 1

        for platform_record in p.get("platform_records", []) or []:
            if not isinstance(platform_record, dict):
                continue
            platform = str(platform_record.get("platform", "")).strip().lower()
            if platform:
                platform_counts[platform] = platform_counts.get(platform, 0) + 1
            err = str(platform_record.get("error") or "").strip()
            if err:
                reason_counts[err] = reason_counts.get(err, 0) + 1

        for r in p.get("duplicate_reasons", []) or []:
            key = str(r).strip()
            if key:
                reason_counts[key] = reason_counts.get(key, 0) + 1

        for r in p.get("validation_errors", []) or []:
            key = str(r).strip()
            if key:
                reason_counts[key] = reason_counts.get(key, 0) + 1

    recurring = sorted(reason_counts.items(), key=lambda kv: kv[1], reverse=True)
    return {
        "sample_size": len(posts),
        "scores": {
            "count": len(scores),
            "average": round(sum(scores) / len(scores), 2) if scores else None,
            "min": min(scores) if scores else None,
            "max": max(scores) if scores else None,
        },
        "rejected_posts": [
            {
                "post_id": p.get("post_id"),
                "date": p.get("date"),
                "slot": p.get("slot"),
                "status": p.get("status"),
                "duplicate_reasons": p.get("duplicate_reasons", []),
                "validation_errors": p.get("validation_errors", []),
            }
            for p in rejected[-50:]
        ],
        "rejection_reasons": [{"reason": k, "count": v} for k, v in recurring[:30]],
        "recurring_generation_problems": [{"problem": k, "count": v} for k, v in recurring[:15]],
        "platform_distribution": platform_counts,
        "funnel_stage_distribution": stage_counts,
    }


def _parse_preview_params(params: dict) -> dict:
    platform = str(params.get("platform", [""])[0]).strip().lower()
    slot = str(params.get("slot", ["morning"])[0]).strip().lower()
    funnel_stage = str(params.get("funnel_stage", [""])[0]).strip().upper()
    product_id = str(params.get("product_id", [""])[0]).strip()
    if slot not in ("morning", "midday", "evening"):
        slot = "morning"
    if platform and platform not in ("facebook", "instagram", "linkedin", "wordpress"):
        platform = ""
    if funnel_stage and funnel_stage not in ("ATTENTION", "EDUCATION", "DESIRE", "TRUST", "CONVERSION"):
        funnel_stage = ""
    return {
        "platform": platform,
        "slot": slot,
        "funnel_stage": funnel_stage,
        "product_id": product_id,
    }


def _content_preview(preview_params: dict) -> dict:
    content = generate_posts.generate(
        preview_params["slot"],
        funnel_stage_override=str(preview_params.get("funnel_stage", "")),
        product_id_override=str(preview_params.get("product_id", "")),
    )
    platform = preview_params.get("platform", "")
    requested_stage = preview_params.get("funnel_stage", "")
    requested_product_id = preview_params.get("product_id", "")
    notes: list[str] = []

    if requested_stage:
        if str(content.get("funnel_stage", "")).upper() == requested_stage:
            notes.append("funnel_stage_override_applied")
        else:
            notes.append("funnel_stage_override_not_applied")

    if requested_product_id:
        matched = str(content.get("product_id", "")) == requested_product_id
        notes.append("requested_product_matched" if matched else "requested_product_not_matched")

    if platform:
        platform_posts = content.get("platform_posts", {})
        if isinstance(platform_posts, dict):
            selected = platform_posts.get(platform)
            content["platform_posts"] = {platform: selected} if isinstance(selected, dict) else {}

    content["preview_only"] = True
    content["preview_filters"] = preview_params
    content["preview_notes"] = notes
    return content


def _schedule_preview(days: int = 7) -> list[dict]:
    history = _load_json(os.path.join(_data_dir(), "post_history.json"), {"posts": []})
    schedule = load_channel_schedule()
    funnel_config = load_funnel_config()
    now = datetime.now(timezone.utc)
    out: list[dict] = []

    for offset in range(days):
        when = now + timedelta(days=offset)
        day_entry = {
            "date": when.date().isoformat(),
            "weekday": when.strftime("%A").lower(),
            "slots": {},
        }
        for slot in ("morning", "midday", "evening"):
            stage = stage_for_slot(slot, history=history, funnel_config=funnel_config)
            eligibility = eligible_channels_for_slot(
                slot=slot,
                funnel_stage=stage,
                schedule=schedule,
                now_utc=when,
                manual_platforms=[],
            )
            day_entry["slots"][slot] = {
                "funnel_stage": stage,
                "eligible_channels": {
                    name: {"eligible": bool(values[0]), "reason": str(values[1])}
                    for name, values in eligibility.items()
                },
            }
        out.append(day_entry)
    return out


def _authorized(params: dict) -> tuple[bool, int, dict]:
    token = os.environ.get("MANUAL_RUN_TOKEN", "")
    provided = str(params.get("token", [""])[0])
    if not token:
        return False, 403, {"error": "MANUAL_RUN_TOKEN not configured"}
    if provided != token:
        return False, 401, {"error": "invalid token"}
    return True, 200, {}


def _uptime_seconds() -> int:
    return int((datetime.now(timezone.utc) - STARTED_AT).total_seconds())


def _run_script(script_name: str) -> tuple[bool, str]:
    scripts_dir = os.path.join(os.path.dirname(__file__), "scripts")
    script_path = os.path.join(scripts_dir, script_name)
    try:
        completed = subprocess.run(
            [sys.executable, script_path],
            cwd=os.path.dirname(__file__),
            capture_output=True,
            text=True,
            check=False,
            timeout=600,
        )
        output = (completed.stdout or "") + (completed.stderr or "")
        if completed.returncode == 0:
            return True, output[-3000:]
        return False, output[-3000:]
    except Exception as e:
        return False, str(e)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _start_slot_thread(slot: str, force_live: bool = False, platforms_override: str = "", duplicate_mode: str = "") -> bool:
    if RUN_LOCK.locked():
        return False

    thread = threading.Thread(target=run_slot, args=(slot, force_live, platforms_override, duplicate_mode), daemon=True)
    thread.start()
    return True


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path in ("/", "/health", "/healthz"):
            payload = {
                "status": "ok",
                "service": "infenergy-social-engine",
                "time_utc": _utc_now(),
                "uptime_seconds": _uptime_seconds(),
            }
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/status":
            recent_posts = _load_history(limit=10)
            payload = {
                "status": "ok",
                "service": "infenergy-social-engine",
                "time_utc": _utc_now(),
                "uptime_seconds": _uptime_seconds(),
                "last_run": LAST_RUN,
                "dry_run": os.environ.get("SOCIAL_DRY_RUN", "true"),
                "recent_quality": _quality_summary(recent_posts),
            }
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/history":
            params = parse_qs(parsed.query)
            limit = int(params.get("limit", ["20"])[0])
            limit = max(1, min(200, limit))
            posts = _load_history(limit=limit)
            payload = {
                "status": "ok",
                "time_utc": _utc_now(),
                "count": len(posts),
                "posts": posts,
            }
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/campaign":
            plan = _load_latest_campaign_plan()
            payload = {
                "status": "ok",
                "time_utc": _utc_now(),
                "campaign": plan,
            }
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/campaign-current":
            params = parse_qs(parsed.query)
            authorized, status_code, error_payload = _authorized(params)
            if not authorized:
                body = json.dumps(error_payload).encode("utf-8")
                self.send_response(status_code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            campaign = _load_latest_structured_campaign()
            payload = {
                "status": "ok",
                "time_utc": _utc_now(),
                "campaign": campaign,
            }
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/content-preview":
            params = parse_qs(parsed.query)
            authorized, status_code, error_payload = _authorized(params)
            if not authorized:
                body = json.dumps(error_payload).encode("utf-8")
                self.send_response(status_code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            preview_params = _parse_preview_params(params)
            payload = {
                "status": "ok",
                "time_utc": _utc_now(),
                "preview": _content_preview(preview_params),
            }
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/schedule-preview":
            params = parse_qs(parsed.query)
            authorized, status_code, error_payload = _authorized(params)
            if not authorized:
                body = json.dumps(error_payload).encode("utf-8")
                self.send_response(status_code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            payload = {
                "status": "ok",
                "time_utc": _utc_now(),
                "days": _schedule_preview(days=7),
            }
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/quality-report":
            params = parse_qs(parsed.query)
            authorized, status_code, error_payload = _authorized(params)
            if not authorized:
                body = json.dumps(error_payload).encode("utf-8")
                self.send_response(status_code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            limit = int(params.get("limit", ["200"])[0])
            limit = max(10, min(500, limit))
            posts = _load_history(limit=limit)
            payload = {
                "status": "ok",
                "time_utc": _utc_now(),
                "report": _quality_report(posts),
            }
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/run-marketing":
            token = os.environ.get("MANUAL_RUN_TOKEN", "")
            params = parse_qs(parsed.query)
            provided = params.get("token", [""])[0]
            if not token:
                body = b'{"error":"MANUAL_RUN_TOKEN not configured"}'
                self.send_response(403)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if provided != token:
                body = b'{"error":"invalid token"}'
                self.send_response(401)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            ok, output = _run_script("run_marketing_team.py")
            payload = {
                "ok": ok,
                "message": "marketing team run complete" if ok else "marketing team run failed",
                "time_utc": _utc_now(),
                "output_tail": output,
            }
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200 if ok else 500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/run-weekly":
            token = os.environ.get("MANUAL_RUN_TOKEN", "")
            params = parse_qs(parsed.query)
            provided = params.get("token", [""])[0]
            if not token:
                body = b'{"error":"MANUAL_RUN_TOKEN not configured"}'
                self.send_response(403)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if provided != token:
                body = b'{"error":"invalid token"}'
                self.send_response(401)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            ok, output = _run_script("run_marketing_weekly.py")
            payload = {
                "ok": ok,
                "message": "weekly planner run complete" if ok else "weekly planner run failed",
                "time_utc": _utc_now(),
                "output_tail": output,
            }
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200 if ok else 500)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/run-now":
            token = os.environ.get("MANUAL_RUN_TOKEN", "")
            params = parse_qs(parsed.query)
            provided = params.get("token", [""])[0]
            slot = params.get("slot", ["morning"])[0]
            force_live = params.get("live", ["false"])[0].lower() in ("1", "true", "yes")
            platforms_override = params.get("platforms", [""])[0]
            duplicate_mode = params.get("duplicate_mode", [""])[0].strip().lower()
            if duplicate_mode and duplicate_mode not in ("strict", "exact_only", "allow_all"):
                duplicate_mode = ""
            if slot not in ("morning", "midday", "evening"):
                slot = "morning"

            if not token:
                body = b'{"error":"MANUAL_RUN_TOKEN not configured"}'
                self.send_response(403)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            if provided != token:
                body = b'{"error":"invalid token"}'
                self.send_response(401)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return

            started = _start_slot_thread(
                slot,
                force_live=force_live,
                platforms_override=platforms_override,
                duplicate_mode=duplicate_mode,
            )
            payload = {
                "accepted": started,
                "slot": slot,
                "force_live": force_live,
                "platforms": platforms_override,
                "duplicate_mode": duplicate_mode or "env_default",
                "message": "run started" if started else "run already in progress",
                "time_utc": _utc_now(),
            }
            body = json.dumps(payload).encode("utf-8")
            self.send_response(202 if started else 409)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        self.send_response(404)
        self.end_headers()

    def log_message(self, format, *args):
        return


def start_health_server() -> None:
    port = int(os.environ.get("PORT", "8080"))
    server = ThreadingHTTPServer(("0.0.0.0", port), HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    print(f"Health endpoint listening on 0.0.0.0:{port}")


def run_slot(slot: str, force_live: bool = False, platforms_override: str = "", duplicate_mode: str = "") -> None:
    with RUN_LOCK:
        LAST_RUN["status"] = "running"
        LAST_RUN["slot"] = slot
        LAST_RUN["started_at_utc"] = _utc_now()
        LAST_RUN["finished_at_utc"] = None
        LAST_RUN["error"] = None

        print(f"\n[{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}] Starting {slot} run...")
        previous_dry_run = os.environ.get("SOCIAL_DRY_RUN", "true")
        previous_platforms = os.environ.get("POST_PLATFORMS", "")
        previous_duplicate_mode = os.environ.get("MANUAL_DUPLICATE_MODE", "")
        os.environ["POST_SLOT"] = slot
        os.environ["POST_PLATFORMS"] = platforms_override
        if duplicate_mode:
            os.environ["MANUAL_DUPLICATE_MODE"] = duplicate_mode
        if force_live:
            os.environ["SOCIAL_DRY_RUN"] = "false"
        try:
            timeout_sec = int(os.environ.get("RUN_SLOT_TIMEOUT_SEC", "420"))
            scripts_dir = os.path.join(os.path.dirname(__file__), "scripts")
            run_engine_path = os.path.join(scripts_dir, "run_engine.py")
            env = os.environ.copy()

            completed = subprocess.run(
                [sys.executable, run_engine_path],
                cwd=os.path.dirname(__file__),
                capture_output=True,
                text=True,
                env=env,
                timeout=timeout_sec,
                check=False,
            )

            output = ((completed.stdout or "") + "\n" + (completed.stderr or "")).strip()
            if output:
                print(output[-4000:])

            if completed.returncode != 0:
                raise RuntimeError(f"run_engine exit={completed.returncode} output_tail={output[-1500:]}")

            LAST_RUN["status"] = "success"
        except subprocess.TimeoutExpired as e:
            partial = ((e.stdout or "") + "\n" + (e.stderr or "")).strip()
            LAST_RUN["status"] = "failed"
            LAST_RUN["error"] = f"run_timeout_after_{timeout_sec}s"
            if partial:
                print(partial[-4000:])
            print(f"[ERROR] {slot} run timed out after {timeout_sec}s")
        except BaseException as e:
            LAST_RUN["status"] = "failed"
            LAST_RUN["error"] = str(e)
            print(f"[ERROR] {slot} run failed: {e}")
            traceback.print_exc()
        finally:
            os.environ["SOCIAL_DRY_RUN"] = previous_dry_run
            os.environ["POST_PLATFORMS"] = previous_platforms
            if previous_duplicate_mode:
                os.environ["MANUAL_DUPLICATE_MODE"] = previous_duplicate_mode
            elif "MANUAL_DUPLICATE_MODE" in os.environ:
                del os.environ["MANUAL_DUPLICATE_MODE"]
            LAST_RUN["finished_at_utc"] = _utc_now()


# All times in UTC — currently mapped to Central Time (CT)
# 8am CT = 13:00 UTC | 12pm CT = 17:00 UTC | 6pm CT = 23:00 UTC
# Change POST_SCHEDULE_MORNING/MIDDAY/EVENING env vars to override
morning_utc = os.environ.get("POST_SCHEDULE_MORNING", "13:00")
midday_utc  = os.environ.get("POST_SCHEDULE_MIDDAY",  "17:00")
evening_utc = os.environ.get("POST_SCHEDULE_EVENING", "23:00")

def main() -> None:
    schedule.clear()
    schedule.every().day.at(morning_utc).do(run_slot, "morning")
    schedule.every().day.at(midday_utc).do(run_slot, "midday")
    schedule.every().day.at(evening_utc).do(run_slot, "evening")

    start_health_server()

    print("=== INF Energy Social Engine — Railway Worker ===")
    print(f"Scheduled (UTC): morning={morning_utc}  midday={midday_utc}  evening={evening_utc}")
    print(f"Dry run: {os.environ.get('SOCIAL_DRY_RUN', 'true')}")
    print("Manual run endpoint: /run-now?slot=morning&token=... (requires MANUAL_RUN_TOKEN)")
    print("Waiting for next scheduled run...\n")

    if os.environ.get("RUN_ON_STARTUP", "false").lower() == "true":
        print("RUN_ON_STARTUP=true, launching startup run for morning slot")
        _start_slot_thread("morning")

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
