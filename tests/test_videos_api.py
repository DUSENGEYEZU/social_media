from typing import ClassVar

import pytest

from app.api import videos
from app.services.retrieving_data import VideoDownloadError
from app.services.transcription import Transcript
from app.services.translation import Translation

METADATA = {
    "title": "My Video",
    "video_id": "abc123",
    "file_path": "/downloads/My Video [abc123].mp4",
    "duration_seconds": 42,
    "file_size_bytes": 1024,
}
# What the API returns when TRANSCRIPTION_ENABLED is false (the test default).
DISABLED_RESPONSE = {
    **METADATA,
    "transcript_language": None,
    "transcript_text": None,
    "translation_language": None,
    "translation_text": None,
    "topic": None,
    "warnings": ["Transcription is disabled."],
}


class FakeDownloader:
    """Stand-in for DownloadVideo that records calls instead of downloading."""

    created_with: ClassVar[str | None] = None
    calls: ClassVar[list[str]] = []
    error: ClassVar[Exception | None] = None

    def __init__(self, download_dir):
        FakeDownloader.created_with = download_dir

    def _record(self, url):
        FakeDownloader.calls.append(url)
        if FakeDownloader.error is not None:
            raise FakeDownloader.error
        return METADATA

    def youtube(self, url):
        return self._record(url)

    def instagram(self, url):
        return self._record(url)

    def tiktok(self, url):
        return self._record(url)

    def facebook(self, url):
        return self._record(url)


@pytest.fixture
def fake_downloader(monkeypatch):
    FakeDownloader.created_with = None
    FakeDownloader.calls = []
    FakeDownloader.error = None
    monkeypatch.setattr(videos, "DownloadVideo", FakeDownloader)
    return FakeDownloader


def test_post_youtube_downloads_and_returns_metadata(
    client, download_dir, fake_downloader
):
    response = client.post(
        "/api/v1/videos/youtube", json={"url": "https://youtu.be/abc123"}
    )

    assert response.status_code == 201
    assert response.get_json() == DISABLED_RESPONSE
    assert fake_downloader.calls == ["https://youtu.be/abc123"]
    assert fake_downloader.created_with == str(download_dir)


def test_post_youtube_without_url_returns_400(client, fake_downloader):
    response = client.post("/api/v1/videos/youtube", json={})

    assert response.status_code == 400
    assert "url" in response.get_json()["error"]
    assert fake_downloader.calls == []


def test_post_youtube_with_non_json_body_returns_400(client, fake_downloader):
    response = client.post("/api/v1/videos/youtube", data="url=https://youtu.be/abc123")

    assert response.status_code == 400
    assert fake_downloader.calls == []


def test_post_youtube_with_non_youtube_url_returns_400(client, download_dir):
    # Uses the real DownloadVideo: it rejects the URL before touching the network.
    response = client.post(
        "/api/v1/videos/youtube", json={"url": "https://vimeo.com/123"}
    )

    assert response.status_code == 400
    assert "YouTube" in response.get_json()["error"]
    assert not download_dir.exists()


def test_post_youtube_when_download_fails_returns_502(client, fake_downloader):
    fake_downloader.error = VideoDownloadError("ERROR: Video unavailable")

    response = client.post(
        "/api/v1/videos/youtube", json={"url": "https://youtu.be/abc123"}
    )

    assert response.status_code == 502
    assert "Video unavailable" in response.get_json()["error"]


INSTAGRAM_REEL = "https://www.instagram.com/reel/Dcik7_Zy3Ph/"
TIKTOK_VIDEO = "https://www.tiktok.com/@tiktok/video/7106594312292453675"
FACEBOOK_VIDEO = "https://www.facebook.com/watch/?v=1234567890123"

PLATFORM_ROUTES = [
    pytest.param(
        "/api/v1/videos/instagram", "Instagram", INSTAGRAM_REEL, id="instagram"
    ),
    pytest.param("/api/v1/videos/tiktok", "TikTok", TIKTOK_VIDEO, id="tiktok"),
    pytest.param("/api/v1/videos/facebook", "Facebook", FACEBOOK_VIDEO, id="facebook"),
]


@pytest.mark.parametrize("route, platform, good_url", PLATFORM_ROUTES)
def test_post_platform_downloads_and_returns_metadata(
    client, download_dir, fake_downloader, route, platform, good_url
):
    response = client.post(route, json={"url": good_url})

    assert response.status_code == 201
    assert response.get_json() == DISABLED_RESPONSE
    assert fake_downloader.calls == [good_url]
    assert fake_downloader.created_with == str(download_dir)


@pytest.mark.parametrize("route, platform, good_url", PLATFORM_ROUTES)
def test_post_platform_without_url_returns_400(
    client, fake_downloader, route, platform, good_url
):
    response = client.post(route, json={})

    assert response.status_code == 400
    assert "url" in response.get_json()["error"]
    assert fake_downloader.calls == []


@pytest.mark.parametrize("route, platform, good_url", PLATFORM_ROUTES)
def test_post_platform_with_url_from_another_site_returns_400(
    client, download_dir, route, platform, good_url
):
    # Uses the real DownloadVideo: it rejects the URL before touching the network.
    response = client.post(route, json={"url": "https://vimeo.com/123"})

    assert response.status_code == 400
    assert platform in response.get_json()["error"]
    assert not download_dir.exists()


@pytest.mark.parametrize("route, platform, good_url", PLATFORM_ROUTES)
def test_post_platform_when_download_fails_returns_502(
    client, fake_downloader, route, platform, good_url
):
    fake_downloader.error = VideoDownloadError("ERROR: Video unavailable")

    response = client.post(route, json={"url": good_url})

    assert response.status_code == 502
    assert "Video unavailable" in response.get_json()["error"]


class FakeTranscriber:
    model_size = None

    def __init__(self, model_size):
        FakeTranscriber.model_size = model_size

    def transcribe(self, path):
        return Transcript("en", ["Hello.", "Bye."])


class FakeTranslator:
    def translate(self, segments, source_language):
        return Translation("fr", "Salut. Au revoir.")


class FakeSummarizer:
    def summarize(self, text):
        return "A short greeting video."


def test_post_youtube_with_transcription_returns_text_fields(
    app, client, fake_downloader, monkeypatch
):
    app.config["TRANSCRIPTION_ENABLED"] = True
    app.config["WHISPER_MODEL"] = "tiny"
    monkeypatch.setattr(videos, "Transcriber", FakeTranscriber)
    monkeypatch.setattr(videos, "Translator", FakeTranslator)
    monkeypatch.setattr(videos, "Summarizer", FakeSummarizer)

    response = client.post(
        "/api/v1/videos/youtube", json={"url": "https://youtu.be/abc123"}
    )

    assert response.status_code == 201
    body = response.get_json()
    assert body["transcript_language"] == "en"
    assert body["transcript_text"] == "Hello. Bye."
    assert body["translation_language"] == "fr"
    assert body["translation_text"] == "Salut. Au revoir."
    assert body["topic"] == "A short greeting video."
    assert body["warnings"] == []
    assert FakeTranscriber.model_size == "tiny"
