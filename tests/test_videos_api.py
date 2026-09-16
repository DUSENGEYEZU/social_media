from typing import ClassVar

import pytest

from app.api import videos
from app.services.retrieving_data import VideoDownloadError

METADATA = {
    "title": "My Video",
    "video_id": "abc123",
    "file_path": "/downloads/My Video [abc123].mp4",
    "duration_seconds": 42,
    "file_size_bytes": 1024,
}


class FakeDownloader:
    """Stand-in for DownloadVideo that records calls instead of downloading."""

    created_with: ClassVar[str | None] = None
    calls: ClassVar[list[str]] = []
    error: ClassVar[Exception | None] = None

    def __init__(self, download_dir):
        FakeDownloader.created_with = download_dir

    def youtube(self, url):
        FakeDownloader.calls.append(url)
        if FakeDownloader.error is not None:
            raise FakeDownloader.error
        return METADATA


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
    assert response.get_json() == METADATA
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
