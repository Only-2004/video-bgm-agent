"""Tests for the three API endpoints: upload, analyze, match, and status."""

import io
import os
import uuid
from unittest.mock import patch, MagicMock, AsyncMock

import pytest
from fastapi.testclient import TestClient

from main import app
from routers import upload
from config import UPLOAD_DIR

client = TestClient(app)

os.makedirs(UPLOAD_DIR, exist_ok=True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dummy_analysis_result():
    """Return a minimal VideoAnalysisResult dict for mocking."""
    return {
        "video_id": "test-video",
        "visual": {
            "scene": "室内",
            "objects": [],
            "people_count": "单人",
            "activity": "休闲",
            "color_tone": "暖色调",
            "lighting": "自然光",
            "visual_style": "写实",
        },
        "audio": {
            "has_speech": False,
            "speech_segments": [],
            "ambient_noise_level": "安静",
            "music_playing": False,
            "emotional_tone": "平静",
            "audio_events": [],
        },
        "temporal": {
            "scene_changes": 3,
            "editing_rhythm": "中等",
            "key_moments": [5.0, 15.0],
            "narrative_pace": "平缓",
            "rhythm_curve": [0.3, 0.5, 0.7],
        },
        "text": {
            "has_subtitles": False,
            "subtitle_content": "",
            "on_screen_text": [],
            "text_sentiment": "中性",
        },
        "semantic": {
            "narrative_structure": "线性叙事",
            "emotion": "愉快",
            "emotion_curve": ["平静", "愉快", "平静"],
            "theme": "旅行",
            "purpose": "生活记录",
        },
        "emotion_curve": {
            "time_points": [0, 5, 10],
            "emotions": ["平静", "愉快", "平静"],
            "intensity": [0.3, 0.6, 0.3],
        },
        "confidence": 0.85,
        "created_at": "2026-01-01T00:00:00",
    }


# ---------------------------------------------------------------------------
# Upload tests
# ---------------------------------------------------------------------------

class TestUploadEndpoint:
    """Tests for POST /api/upload."""

    @patch("routers.upload.open", create=True)
    def test_upload_returns_video_id_and_status(self, mock_open):
        """Upload endpoint returns video_id and status (no file_path)."""
        mock_open.return_value.__enter__ = lambda s: s
        mock_open.return_value.__exit__ = MagicMock(return_value=False)
        mock_open.return_value.write = MagicMock()

        file_content = b"fake-video-bytes"
        response = client.post(
            "/api/upload",
            files={"video": ("test.mp4", io.BytesIO(file_content), "video/mp4")},
        )
        assert response.status_code == 200
        data = response.json()
        assert "video_id" in data
        assert data["status"] == "uploaded"
        assert "file_path" not in data

    @patch("routers.upload.open", create=True)
    def test_upload_rejects_bad_content_type(self, mock_open):
        """Upload endpoint rejects non-video content types."""
        mock_open.return_value.__enter__ = lambda s: s
        mock_open.return_value.__exit__ = MagicMock(return_value=False)
        mock_open.return_value.write = MagicMock()

        response = client.post(
            "/api/upload",
            files={"video": ("test.txt", io.BytesIO(b"data"), "text/plain")},
        )
        assert response.status_code == 400

    @patch("routers.upload.open", create=True)
    def test_upload_accepts_various_video_types(self, mock_open):
        """Upload endpoint accepts multiple video MIME types."""
        mock_open.return_value.__enter__ = lambda s: s
        mock_open.return_value.__exit__ = MagicMock(return_value=False)
        mock_open.return_value.write = MagicMock()

        for mime in ["video/mp4", "video/quicktime", "video/webm"]:
            response = client.post(
                "/api/upload",
                files={"video": ("test.mp4", io.BytesIO(b"data"), mime)},
            )
            assert response.status_code == 200, f"Failed for {mime}"


# ---------------------------------------------------------------------------
# Route cleanup tests — removed endpoints should return 404
# ---------------------------------------------------------------------------

class TestRootRoute:
    """Tests for GET / (root HTML route)."""

    def test_root_returns_response(self):
        """Root route returns either HTML or a JSON message."""
        response = client.get("/")
        assert response.status_code == 200

    def test_demo_route_removed(self):
        """The /demo route should no longer exist."""
        response = client.get("/demo")
        assert response.status_code in (404, 405)


# ---------------------------------------------------------------------------
# Route existence tests
# ---------------------------------------------------------------------------

class TestRouteCleanup:
    """Verify that removed/extra routes no longer exist."""

    def test_get_upload_info_removed(self):
        """GET /api/upload/{video_id} should no longer exist."""
        response = client.get("/api/upload/some-id")
        # Should be 405 Method Not Allowed (POST exists but GET removed)
        assert response.status_code in (404, 405)
