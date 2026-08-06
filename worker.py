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
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "scripts"))

import run_engine

RUN_LOCK = threading.Lock()
LAST_RUN = {
    "status": "idle",
    "slot": None,
    "started_at_utc": None,
    "finished_at_utc": None,
    "error": None,
}
STARTED_AT = datetime.now(timezone.utc)


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


def _start_slot_thread(slot: str, force_live: bool = False) -> bool:
    if RUN_LOCK.locked():
        return False

    thread = threading.Thread(target=run_slot, args=(slot, force_live), daemon=True)
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
            payload = {
                "status": "ok",
                "service": "infenergy-social-engine",
                "time_utc": _utc_now(),
                "uptime_seconds": _uptime_seconds(),
                "last_run": LAST_RUN,
                "dry_run": os.environ.get("SOCIAL_DRY_RUN", "true"),
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

            started = _start_slot_thread(slot, force_live=force_live)
            payload = {
                "accepted": started,
                "slot": slot,
                "force_live": force_live,
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


def run_slot(slot: str, force_live: bool = False) -> None:
    with RUN_LOCK:
        LAST_RUN["status"] = "running"
        LAST_RUN["slot"] = slot
        LAST_RUN["started_at_utc"] = _utc_now()
        LAST_RUN["finished_at_utc"] = None
        LAST_RUN["error"] = None

        print(f"\n[{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}] Starting {slot} run...")
        previous_dry_run = os.environ.get("SOCIAL_DRY_RUN", "true")
        os.environ["POST_SLOT"] = slot
        if force_live:
            os.environ["SOCIAL_DRY_RUN"] = "false"
        try:
            run_engine.main()
            LAST_RUN["status"] = "success"
        except BaseException as e:
            LAST_RUN["status"] = "failed"
            LAST_RUN["error"] = str(e)
            print(f"[ERROR] {slot} run failed: {e}")
            traceback.print_exc()
        finally:
            os.environ["SOCIAL_DRY_RUN"] = previous_dry_run
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
