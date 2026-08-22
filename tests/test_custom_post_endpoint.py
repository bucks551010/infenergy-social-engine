import os
import tempfile
from unittest.mock import patch

import worker


def _payload():
    return {
        "external_id": "iis-schedule-1",
        "caption": "Exact IIS caption",
        "image_url": "https://example.com/image.png",
        "platforms": ["facebook", "instagram", "linkedin"],
        "live": True,
    }


def test_custom_post_validates_required_fields():
    status, response = worker._publish_custom_post({})
    assert status == 400
    assert "external_id" in response["error"]


def test_custom_post_checkpoints_platforms_and_is_idempotent():
    with tempfile.TemporaryDirectory() as data_dir, patch.dict(os.environ, {"DATA_DIR": data_dir}, clear=False), \
        patch("publish_facebook.publish", return_value={"id": "fb-1"}) as facebook, \
        patch("publish_instagram.publish", return_value={"id": "ig-1"}) as instagram, \
        patch("publish_linkedin.publish", return_value={"id": "li-1"}) as linkedin:
        first_status, first = worker._publish_custom_post(_payload())
        second_status, second = worker._publish_custom_post(_payload())

    assert first_status == second_status == 200
    assert first["status"] == second["status"] == "published"
    assert facebook.call_count == instagram.call_count == linkedin.call_count == 1


def test_custom_post_retry_only_replays_failed_platform():
    payload = _payload()
    payload["platforms"] = ["facebook", "instagram"]
    with tempfile.TemporaryDirectory() as data_dir, patch.dict(os.environ, {"DATA_DIR": data_dir}, clear=False), \
        patch("publish_facebook.publish", return_value={"id": "fb-1"}) as facebook, \
        patch("publish_instagram.publish", side_effect=[RuntimeError("temporary"), {"id": "ig-1"}]) as instagram:
        first_status, first = worker._publish_custom_post(payload)
        second_status, second = worker._publish_custom_post(payload)

    assert first_status == 502
    assert first["failed_platforms"] == ["instagram"]
    assert second_status == 200
    assert second["failed_platforms"] == []
    assert facebook.call_count == 1
    assert instagram.call_count == 2