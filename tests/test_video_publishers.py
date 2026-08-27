from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import publish_tiktok
import publish_youtube
import tiktok_oauth
from platform_publishing import PublicationError, connection_health, list_platforms, validate_content


def _content():
    return {
        "title": "The Nine-Minute Blackout",
        "ig_caption": "A Micro Mission story",
        "instagram_reel": {
            "public_urls": {
                "video": "https://media.example/story.mp4",
                "cover": "https://media.example/cover.jpg",
            }
        },
    }


def test_youtube_refreshes_oauth_and_uploads_video():
    token_response = Mock()
    token_response.raise_for_status.return_value = None
    token_response.json.return_value = {"access_token": "access"}
    session_response = Mock()
    session_response.raise_for_status.return_value = None
    session_response.headers = {"Location": "https://upload.example/session"}
    upload_response = Mock(status_code=200)
    upload_response.raise_for_status.return_value = None
    upload_response.json.return_value = {"id": "yt-123"}
    download = Mock()
    download.__enter__ = Mock(return_value=download)
    download.__exit__ = Mock(return_value=False)
    download.raise_for_status.return_value = None
    download.iter_content.return_value = [b"video"]
    with patch.dict(os.environ, {
        "YOUTUBE_CLIENT_ID": "client", "YOUTUBE_CLIENT_SECRET": "secret", "YOUTUBE_REFRESH_TOKEN": "refresh",
    }, clear=False), patch.object(publish_youtube.requests, "get", return_value=download), \
        patch.object(publish_youtube.requests, "post", side_effect=[token_response, session_response]) as post, \
        patch.object(publish_youtube.requests, "put", return_value=upload_response) as put:
        result = publish_youtube.publish(_content())
    assert result["id"] == "yt-123"
    assert result["url"].endswith("yt-123")
    assert result["status"] == "PROCESSING"
    assert post.call_args_list[0].kwargs["data"]["grant_type"] == "refresh_token"
    assert post.call_args_list[1].kwargs["params"]["uploadType"] == "resumable"
    assert put.call_args.args[0] == "https://upload.example/session"


def test_tiktok_refreshes_oauth_and_initializes_direct_post():
    token_response = Mock()
    token_response.raise_for_status.return_value = None
    token_response.json.return_value = {"access_token": "access"}
    creator_response = Mock()
    creator_response.raise_for_status.return_value = None
    creator_response.json.return_value = {"data": {"privacy_level_options": ["SELF_ONLY"]}, "error": {"code": "ok"}}
    publish_response = Mock()
    publish_response.raise_for_status.return_value = None
    publish_response.json.return_value = {"data": {"publish_id": "tt-123"}, "error": {"code": "ok"}}
    with patch.dict(os.environ, {
        "TIKTOK_ACCESS_TOKEN": "", "TIKTOK_CLIENT_KEY": "key", "TIKTOK_CLIENT_SECRET": "secret", "TIKTOK_REFRESH_TOKEN": "refresh",
    }, clear=False), patch.object(publish_tiktok.requests, "post", side_effect=[token_response, creator_response, publish_response]) as post:
        result = publish_tiktok.publish(_content())
    assert result["id"] == "tt-123"
    assert result["status"] == "PROCESSING"
    assert post.call_args_list[0].kwargs["data"]["grant_type"] == "refresh_token"
    assert post.call_args_list[1].args[0] == tiktok_oauth.CREATOR_INFO_URL
    assert post.call_args_list[2].kwargs["json"]["source_info"]["source"] == "PULL_FROM_URL"


def test_platform_registry_gates_video_publishers_and_never_exposes_secrets():
    with patch.dict(os.environ, {
        "YOUTUBE_PUBLISHING_ENABLED": "false", "YOUTUBE_CLIENT_ID": "REPLACE_ME",
        "YOUTUBE_CLIENT_SECRET": "hidden", "YOUTUBE_REFRESH_TOKEN": "hidden",
    }, clear=False):
        health = connection_health("youtube")
        assert health["status"] == "DISABLED"
        assert "YOUTUBE_CLIENT_ID" in health["missing_configuration"]
        assert "hidden" not in str(list_platforms())
        try:
            validate_content("youtube", _content())
        except PublicationError as error:
            assert error.category == "PLATFORM_POLICY_FAILURE"
        else:
            raise AssertionError("disabled YouTube publishing must fail closed")


def test_video_platform_media_validation_requires_https_mp4():
    content = _content()
    content["instagram_reel"]["public_urls"]["video"] = "https://media.example/story.mov"
    with patch.dict(os.environ, {"TIKTOK_PUBLISHING_ENABLED": "true"}, clear=False):
        try:
            validate_content("tiktok", content)
        except PublicationError as error:
            assert error.category == "MEDIA_FAILURE"
            assert not error.retryable
        else:
            raise AssertionError("invalid video media must fail before upload")
