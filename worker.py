import os
import sys
import time
import json
import threading
import schedule
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "scripts"))

import run_engine


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/", "/health", "/healthz"):
            payload = {
                "status": "ok",
                "service": "infenergy-social-engine",
                "time_utc": datetime.now(timezone.utc).isoformat(),
            }
            body = json.dumps(payload).encode("utf-8")
            self.send_response(200)
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


def run_slot(slot: str) -> None:
    print(f"\n[{datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}] Starting {slot} run...")
    os.environ["POST_SLOT"] = slot
    try:
        run_engine.main()
    except Exception as e:
        print(f"[ERROR] {slot} run failed: {e}")


# All times in UTC — currently mapped to Central Time (CT)
# 8am CT = 13:00 UTC | 12pm CT = 17:00 UTC | 6pm CT = 23:00 UTC
# Change POST_SCHEDULE_MORNING/MIDDAY/EVENING env vars to override
morning_utc = os.environ.get("POST_SCHEDULE_MORNING", "13:00")
midday_utc  = os.environ.get("POST_SCHEDULE_MIDDAY",  "17:00")
evening_utc = os.environ.get("POST_SCHEDULE_EVENING", "23:00")

schedule.every().day.at(morning_utc).do(run_slot, "morning")
schedule.every().day.at(midday_utc).do(run_slot, "midday")
schedule.every().day.at(evening_utc).do(run_slot, "evening")

start_health_server()

print("=== INF Energy Social Engine — Railway Worker ===")
print(f"Scheduled (UTC): morning={morning_utc}  midday={midday_utc}  evening={evening_utc}")
print(f"Dry run: {os.environ.get('SOCIAL_DRY_RUN', 'true')}")
print("Waiting for next scheduled run...\n")

while True:
    schedule.run_pending()
    time.sleep(30)
