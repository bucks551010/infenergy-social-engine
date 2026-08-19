from __future__ import annotations

import os
import sqlite3
import sys
from datetime import date
from unittest.mock import patch

_REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_REPO, "scripts"))

import dispatch_outbox  # noqa: E402
from content_operations import (  # noqa: E402
    content_detail,
    create_council_session,
    ensure_daily_slots,
    get_db_path,
    mark_ready,
    platform_transaction,
    reconcile_confirmed_transactions,
)


def _ready_package(data_dir: str, platforms: list[str]) -> str:
    day = date(2026, 8, 19).isoformat()
    schedule = {
        "morning": f"{day}T13:00:00+00:00",
        "midday": f"{day}T17:00:00+00:00",
        "evening": f"{day}T23:00:00+00:00",
    }
    ensure_daily_slots(data_dir, day, schedule, {"platforms": platforms})
    decision_id = create_council_session(
        data_dir,
        content_date=day,
        slot="morning",
        blackboard={"human_reality": "real", "brain": {}, "heart": {}, "content_job": "TEACH"},
    )
    package = {
        "post_id": "post-1",
        "fb_caption": "Facebook final\n\nUseful depth",
        "ig_caption": "Instagram final\n\nUseful depth",
        "li_text": "LinkedIn final\n\nUseful depth",
        "destination_url": "https://www.infenergypower.com/product/powerpulse-pro-200/",
        "platform_posts": {
            platform: {
                "final_caption": f"{platform.title()} final\n\nUseful depth",
                "destination_url": "https://www.infenergypower.com/product/powerpulse-pro-200/",
                "utm_url": f"https://www.infenergypower.com/product/powerpulse-pro-200/?utm_source={platform}",
            }
            for platform in platforms
        },
        "routing": {"platforms": platforms},
        "generated_visuals": {platform: f"/data/{platform}.png" for platform in platforms},
    }
    return mark_ready(
        data_dir,
        content_date=day,
        slot="morning",
        scheduled_at=schedule["morning"],
        decision_id=decision_id,
        package=package,
    )


def test_dispatcher_publishes_archived_payload_without_generation(tmp_path):
    data_dir = str(tmp_path)
    outbox_id = _ready_package(data_dir, ["facebook", "instagram", "linkedin"])
    with patch.object(dispatch_outbox.publish_facebook, "publish", return_value={"id": "fb-1"}) as facebook, \
        patch.object(dispatch_outbox.publish_instagram, "publish", return_value={"id": "ig-1"}) as instagram, \
        patch.object(dispatch_outbox.publish_linkedin, "publish", return_value={"id": "li-1"}) as linkedin:
        result = dispatch_outbox.dispatch_due(data_dir=data_dir, now_utc="2026-08-19T13:00:01+00:00")

    assert result["status"] == "PUBLISHED"
    assert facebook.call_args.args[0]["platform_posts"]["facebook"]["final_caption"].count("\n\n") == 1
    assert instagram.call_args.args[0]["platform_posts"]["instagram"]["final_caption"].count("\n\n") == 1
    assert linkedin.call_args.args[0]["platform_posts"]["linkedin"]["final_caption"].count("\n\n") == 1
    assert platform_transaction(data_dir, outbox_id, "facebook")["external_id"] == "fb-1"


def test_partial_retry_never_resends_confirmed_platform(tmp_path):
    data_dir = str(tmp_path)
    _ready_package(data_dir, ["facebook", "instagram"])
    with patch.object(dispatch_outbox.publish_facebook, "publish", return_value={"id": "fb-1"}) as facebook, \
        patch.object(dispatch_outbox.publish_instagram, "publish", side_effect=RuntimeError("temporary")) as instagram:
        first = dispatch_outbox.dispatch_due(data_dir=data_dir, now_utc="2026-08-19T13:00:01+00:00")
        assert first["status"] == "PARTIAL_RETRY"
        instagram.side_effect = None
        instagram.return_value = {"id": "ig-1"}
        second = dispatch_outbox.dispatch_due(data_dir=data_dir, now_utc="2026-08-19T13:00:02+00:00")

    assert second["status"] == "PUBLISHED"
    assert facebook.call_count == 1
    assert instagram.call_count == 2


def test_external_success_remains_after_aggregate_persistence_error(tmp_path):
    data_dir = str(tmp_path)
    outbox_id = _ready_package(data_dir, ["facebook"])
    with patch.object(dispatch_outbox.publish_facebook, "publish", return_value={"id": "fb-1"}), \
        patch.object(dispatch_outbox, "finalize_outbox", side_effect=sqlite3.OperationalError("disk busy")):
        try:
            dispatch_outbox.dispatch_due(data_dir=data_dir, now_utc="2026-08-19T13:00:01+00:00")
        except sqlite3.OperationalError:
            pass
    assert platform_transaction(data_dir, outbox_id, "facebook")["state"] == "CONFIRMED_SUCCESS"
    assert reconcile_confirmed_transactions(data_dir) == [
        {"outbox_id": outbox_id, "reason": "confirmed_transactions_reconciled"}
    ]


def test_dispatcher_recovers_packshot_only_package_before_publisher_call(tmp_path):
    data_dir = str(tmp_path)
    outbox_id = _ready_package(data_dir, ["facebook"])
    database = sqlite3.connect(get_db_path(data_dir))
    row = database.execute("SELECT package_json FROM content_outbox WHERE outbox_id=?", (outbox_id,)).fetchone()
    import json
    package = json.loads(row[0])
    package["generated_visuals"]["render_engines"] = {"facebook": "approved_product_photo"}
    package["generated_visuals"]["artifact_reviews"] = {"facebook": {"verdict": "PASS"}}
    package["visual_plan"] = {"creative_route": "PRODUCT_IN_CONTEXT"}
    database.execute("UPDATE content_outbox SET package_json=? WHERE outbox_id=?", (json.dumps(package), outbox_id))
    database.commit()
    database.close()

    with patch.object(dispatch_outbox.publish_facebook, "publish") as facebook:
        result = dispatch_outbox.dispatch_due(data_dir=data_dir, now_utc="2026-08-19T13:00:01+00:00")

    assert result["status"] == "CONTENT_RECOVERING"
    assert "packshot_only" in result["error"]
    facebook.assert_not_called()
