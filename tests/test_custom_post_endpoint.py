import os
import tempfile
import threading
from http.server import HTTPServer
from unittest.mock import patch

import requests

import worker


def test_os_authorized_accepts_either_configured_owner_token():
    with patch.dict(
        os.environ,
        {"INTELLIGENCE_OS_TOKEN": "os-token", "MANUAL_RUN_TOKEN": "manual-token"},
        clear=False,
    ):
        os_authorized = worker._os_authorized(
            type("Handler", (), {"headers": {"Authorization": "Bearer os-token"}})(),
            {},
        )
        manual_authorized = worker._os_authorized(
            type("Handler", (), {"headers": {"Authorization": "Bearer manual-token"}})(),
            {},
        )
        denied = worker._os_authorized(
            type("Handler", (), {"headers": {"Authorization": "Bearer invalid-token"}})(),
            {},
        )

    assert os_authorized == (True, 200, {})
    assert manual_authorized == (True, 200, {})
    assert denied == (False, 401, {"error": "invalid token"})


def setup_function():
    worker._custom_post_artifact_preflight = lambda *_args: []
    worker._verify_iis_publish_package = lambda *_args: []


def _payload():
    return {
        "external_id": "iis-schedule-1",
        "caption": "Exact IIS caption",
        "image_url": "https://example.com/image.png",
        "platforms": ["facebook", "instagram", "linkedin"],
        "live": True,
    }


def _carousel_payload(slide_count=6):
    payload = _payload()
    payload["image_urls"] = [f"https://example.com/slide-{position}.png" for position in range(1, slide_count + 1)]
    return payload


def test_public_media_head_returns_reel_preflight_headers():
    with tempfile.TemporaryDirectory() as data_dir, patch.dict(os.environ, {"DATA_DIR": data_dir}, clear=False):
        media_dir = os.path.join(data_dir, "public_media")
        os.makedirs(media_dir)
        media_path = os.path.join(media_dir, "story.mp4")
        with open(media_path, "wb") as media_file:
            media_file.write(b"video-bytes")

        server = HTTPServer(("127.0.0.1", 0), worker.HealthHandler)
        thread = threading.Thread(target=server.handle_request)
        thread.start()
        try:
            response = requests.head(f"http://127.0.0.1:{server.server_port}/media/story.mp4", timeout=5)
        finally:
            thread.join(timeout=5)
            server.server_close()

    assert response.status_code == 200
    assert response.headers["Content-Type"] == "video/mp4"
    assert response.headers["Content-Length"] == str(len(b"video-bytes"))
    assert response.content == b""


def test_agents_endpoint_marks_query_parameters_for_coercion():
    captured = {}

    def run_agent(name, data_dir, params, *, query_params=False):
        captured.update({"name": name, "params": params, "query_params": query_params})
        return {"slide_count": int(params["slide_count"][0])}

    with tempfile.TemporaryDirectory() as data_dir, patch.dict(
        os.environ,
        {"DATA_DIR": data_dir, "MANUAL_RUN_TOKEN": "test-token"},
        clear=False,
    ), patch("agents.dispatcher.run_agent", run_agent):
        server = HTTPServer(("127.0.0.1", 0), worker.HealthHandler)
        thread = threading.Thread(target=server.handle_request)
        thread.start()
        try:
            response = requests.get(
                f"http://127.0.0.1:{server.server_port}/agents/run",
                params={"name": "carousel_slide_writer", "slide_count": "6", "token": "test-token"},
                timeout=5,
            )
        finally:
            thread.join(timeout=5)
            server.server_close()

    assert response.status_code == 200
    assert response.json()["slide_count"] == 6
    assert captured["name"] == "carousel_slide_writer"
    assert captured["query_params"] is True


def test_custom_post_validates_required_fields():
    status, response = worker._publish_custom_post({})
    assert status == 400
    assert "external_id" in response["error"]


def test_custom_post_requires_two_to_ten_carousel_urls():
    for slide_count in (1, 11):
        status, response = worker._publish_custom_post(_carousel_payload(slide_count))
        assert status == 400
        assert "2 to 10" in response["error"]


def test_custom_post_accepts_carousel_url_boundaries():
    for slide_count in (2, 10):
        payload = _carousel_payload(slide_count)
        payload["external_id"] = f"iis-schedule-{slide_count}"
        payload["live"] = False
        with tempfile.TemporaryDirectory() as data_dir, patch.dict(os.environ, {"DATA_DIR": data_dir}, clear=False):
            status, _ = worker._publish_custom_post(payload)
        assert status == 200


def test_custom_post_rejects_non_https_carousel_url():
    payload = _carousel_payload(8)
    payload["image_urls"][3] = "http://example.com/slide-4.png"
    status, response = worker._publish_custom_post(payload)
    assert status == 400
    assert "public HTTPS URLs" in response["error"]


def test_custom_post_passes_eight_owner_carousel_assets_to_publishers():
    payload = _carousel_payload(8)
    payload["source_system"] = "iis"
    payload["iis_creative_id"] = "approved-iis-creative"
    payload["platforms"] = ["facebook", "instagram"]
    with tempfile.TemporaryDirectory() as data_dir, patch.dict(os.environ, {"DATA_DIR": data_dir}, clear=False), \
        patch("publish_facebook.publish", return_value={"id": "fb-carousel"}) as facebook, \
        patch("publish_instagram.publish", return_value={"id": "ig-carousel"}) as instagram:
        status, _ = worker._publish_custom_post(payload)
    assert status == 200
    assert facebook.call_args.args[0]["owner_supplied_visual"] is True
    assert instagram.call_args.args[0]["owner_supplied_visual"] is True
    assert [asset["public_url"] for asset in facebook.call_args.args[0]["carousel_assets"]] == payload["image_urls"]
    assert [asset["public_url"] for asset in instagram.call_args.args[0]["carousel_assets"]] == payload["image_urls"]


def test_custom_post_routes_reel_to_facebook_and_instagram():
    payload = _carousel_payload(6)
    payload["platforms"] = ["facebook", "instagram"]
    payload["reel"] = {
        "video_url": "https://media.example/story.mp4",
        "cover_url": "https://media.example/story-cover.jpg",
    }
    with tempfile.TemporaryDirectory() as data_dir, patch.dict(os.environ, {"DATA_DIR": data_dir}, clear=False), \
        patch("publish_facebook.publish", return_value={"id": "fb-carousel"}) as facebook, \
        patch("publish_instagram.publish", return_value={"id": "ig-reel"}) as instagram:
        status, _ = worker._publish_custom_post(payload)

    assert status == 200
    facebook_content = facebook.call_args.args[0]
    instagram_content = instagram.call_args.args[0]
    assert "instagram_reel" in facebook_content
    assert facebook_content["platform_posts"]["facebook"]["media_type"] == "REEL"
    assert "instagram_reel" in instagram_content
    assert instagram_content["platform_posts"]["instagram"]["media_type"] == "REEL"


def test_custom_post_routes_optional_instagram_story_with_reel():
    payload = _carousel_payload(6)
    payload["platforms"] = ["instagram"]
    payload["instagram_story"] = True
    payload["reel"] = {
        "video_url": "https://media.example/story.mp4",
        "cover_url": "https://media.example/story-cover.jpg",
    }
    with tempfile.TemporaryDirectory() as data_dir, patch.dict(os.environ, {"DATA_DIR": data_dir}, clear=False), \
        patch("publish_instagram.publish", return_value={"id": "ig-reel", "story_id": "ig-story"}) as instagram:
        status, _ = worker._publish_custom_post(payload)

    assert status == 200
    assert instagram.call_args.args[0]["publish_instagram_story"] is True


def test_custom_post_routes_reel_to_youtube_and_tiktok():
    payload = _carousel_payload(6)
    payload["platforms"] = ["youtube", "tiktok"]
    payload["reel"] = {
        "video_url": "https://media.example/story.mp4",
        "cover_url": "https://media.example/story-cover.jpg",
    }
    with tempfile.TemporaryDirectory() as data_dir, patch.dict(os.environ, {"DATA_DIR": data_dir, "YOUTUBE_PUBLISHING_ENABLED": "true", "TIKTOK_PUBLISHING_ENABLED": "true", "YOUTUBE_CLIENT_ID": "client", "YOUTUBE_CLIENT_SECRET": "secret", "YOUTUBE_REFRESH_TOKEN": "refresh", "TIKTOK_CLIENT_KEY": "key", "TIKTOK_CLIENT_SECRET": "secret", "TIKTOK_REFRESH_TOKEN": "refresh"}, clear=False), \
        patch("publish_youtube.publish", return_value={"id": "yt-video"}) as youtube, \
        patch("publish_tiktok.publish", return_value={"id": "tt-video"}) as tiktok:
        status, response = worker._publish_custom_post(payload)

    assert status == 200
    assert response["failed_platforms"] == []
    assert youtube.call_args.args[0]["instagram_reel"]["public_urls"]["video"].endswith("story.mp4")
    assert tiktok.call_args.args[0]["instagram_reel"]["public_urls"]["video"].endswith("story.mp4")


def test_custom_post_reconciles_processing_video_without_duplicate_upload():
    payload = _carousel_payload(6)
    payload["platforms"] = ["tiktok"]
    payload["reel"] = {
        "video_url": "https://media.example/story.mp4",
        "cover_url": "https://media.example/story-cover.jpg",
    }
    environment = {
        "DATA_DIR": "", "TIKTOK_PUBLISHING_ENABLED": "true", "TIKTOK_CLIENT_KEY": "key",
        "TIKTOK_CLIENT_SECRET": "secret", "TIKTOK_REFRESH_TOKEN": "refresh",
    }
    with tempfile.TemporaryDirectory() as data_dir:
        environment["DATA_DIR"] = data_dir
        with patch.dict(os.environ, environment, clear=False), \
            patch("publish_tiktok.publish", return_value={"id": "tt-video", "status": "PROCESSING"}) as tiktok, \
            patch("publish_tiktok.get_status", return_value={"id": "tt-video", "status": "PUBLISH_COMPLETE"}) as status_lookup:
            first_status, first = worker._publish_custom_post(payload)
            second_status, second = worker._publish_custom_post(payload)

    assert first_status == 202
    assert first["status"] == "processing"
    assert first["processing_platforms"] == ["tiktok"]
    assert second_status == 200
    assert second["status"] == "published"
    assert tiktok.call_count == 1
    status_lookup.assert_called_once_with("tt-video")


def test_custom_post_blocks_video_platform_without_reel():
    payload = _payload()
    payload["platforms"] = ["youtube"]
    status, response = worker._publish_custom_post(payload)
    assert status == 400
    assert "rendered Reel" in response["error"]


def test_custom_post_routes_platform_specific_captions_to_each_publisher():
    payload = _payload()
    payload["platform_captions"] = {
        "facebook": "Facebook community copy",
        "instagram": "Instagram visual copy",
        "linkedin": "LinkedIn professional copy",
    }
    with tempfile.TemporaryDirectory() as data_dir, patch.dict(os.environ, {"DATA_DIR": data_dir}, clear=False), \
        patch("publish_facebook.publish", return_value={"id": "fb-1"}) as facebook, \
        patch("publish_instagram.publish", return_value={"id": "ig-1"}) as instagram, \
        patch("publish_linkedin.publish", return_value={"id": "li-1"}) as linkedin:
        status, _ = worker._publish_custom_post(payload)

    assert status == 200
    facebook_content = facebook.call_args.args[0]
    assert facebook_content["fb_caption"] == "Facebook community copy"
    assert facebook_content["platform_posts"]["facebook"]["final_caption"] == "Facebook community copy"
    assert instagram.call_args.args[0]["ig_caption"] == "Instagram visual copy"
    assert linkedin.call_args.args[0]["li_text"] == "LinkedIn professional copy"


def test_custom_post_platform_captions_fall_back_to_master_caption():
    payload = _payload()
    payload["platform_captions"] = {"facebook": "Facebook only"}
    payload["platforms"] = ["facebook", "instagram"]
    with tempfile.TemporaryDirectory() as data_dir, patch.dict(os.environ, {"DATA_DIR": data_dir}, clear=False), \
        patch("publish_facebook.publish", return_value={"id": "fb-1"}) as facebook, \
        patch("publish_instagram.publish", return_value={"id": "ig-1"}) as instagram:
        status, _ = worker._publish_custom_post(payload)

    assert status == 200
    assert facebook.call_args.args[0]["fb_caption"] == "Facebook only"
    assert instagram.call_args.args[0]["ig_caption"] == payload["caption"]


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


def test_custom_post_marks_skipped_publisher_result_as_failed():
    payload = _payload()
    payload["platforms"] = ["instagram"]
    with tempfile.TemporaryDirectory() as data_dir, patch.dict(os.environ, {"DATA_DIR": data_dir}, clear=False), \
        patch("publish_instagram.publish", return_value={"id": "skipped", "reason": "image_unavailable"}):
        status, response = worker._publish_custom_post(payload)

    assert status == 502
    assert response["failed_platforms"] == ["instagram"]
    assert response["platforms"]["instagram"]["status"] == "failed"
    assert response["platforms"]["instagram"]["error"] == "image_unavailable"


def test_custom_post_requires_final_artifact_review_without_owner_bypass():
    payload = _payload()
    payload["platforms"] = ["facebook"]
    with tempfile.TemporaryDirectory() as data_dir, patch.dict(os.environ, {"DATA_DIR": data_dir}, clear=False), \
        patch("publish_facebook.publish", return_value={"id": "fb-1"}) as facebook:
        status, _ = worker._publish_custom_post(payload)

    assert status == 200
    assert facebook.call_args.args[0]["owner_supplied_visual"] is False


def test_custom_post_stops_before_publish_when_artifact_preflight_requires_repair():
    payload = _payload()
    payload["platforms"] = ["facebook"]
    with tempfile.TemporaryDirectory() as data_dir, patch.dict(os.environ, {"DATA_DIR": data_dir}, clear=False), \
        patch.object(worker, "_custom_post_artifact_preflight", return_value=["visual_1_originality_review_not_passed"]), \
        patch("publish_facebook.publish") as facebook:
        status, response = worker._publish_custom_post(payload)

    assert status == 422
    assert response["status"] == "quality_repair_required"
    assert response["issues"] == ["visual_1_originality_review_not_passed"]
    facebook.assert_not_called()


def test_custom_post_stops_before_publish_when_iis_provenance_is_not_current():
    payload = _payload()
    payload.update({"platforms": ["facebook"], "source_system": "iis", "iis_creative_id": "creative-1"})
    with tempfile.TemporaryDirectory() as data_dir, patch.dict(os.environ, {"DATA_DIR": data_dir}, clear=False), \
        patch.object(worker, "_verify_iis_publish_package", return_value=["submitted_images_not_in_approved_iis_package"]), \
        patch("publish_facebook.publish") as facebook:
        status, response = worker._publish_custom_post(payload)

    assert status == 422
    assert response["error"] == "iis_publish_package_verification_failed"
    facebook.assert_not_called()


def test_iis_single_image_export_is_an_approved_publish_asset():
    studio_url = "https://studio.example"
    package = {
        "image": {"id": "approved-image"},
        "delivery": {"carousel": []},
    }

    approved = worker._approved_iis_image_identities(package, studio_url)

    assert worker._asset_url_identity(
        "https://studio.example/api/assets/approved-image?version=2"
    ) in approved
    assert worker._asset_url_identity(
        "https://studio.example/api/assets/different-image"
    ) not in approved


def test_custom_post_retries_legacy_published_skipped_checkpoint():
    payload = _payload()
    payload["platforms"] = ["instagram"]
    with tempfile.TemporaryDirectory() as data_dir:
        history_path = os.path.join(data_dir, "custom_post_history.json")
        with open(history_path, "w", encoding="utf-8") as history_file:
            history_file.write('{"iis-schedule-1":{"platforms":{"instagram":{"status":"published","result":{"id":"skipped","reason":"old_gate"}}}}}')
        with patch.dict(os.environ, {"DATA_DIR": data_dir}, clear=False), \
            patch("publish_instagram.publish", return_value={"id": "ig-1"}) as instagram:
            status, response = worker._publish_custom_post(payload)

    assert status == 200
    assert response["platforms"]["instagram"]["result"]["id"] == "ig-1"
    assert instagram.call_count == 1