from pathlib import Path

import pytest
import yt_dlp

from app.services import retrieving_data
from app.services.retrieving_data import (
    DownloadVideo,
    VideoDownloadError,
    is_instagram_url,
    is_tiktok_url,
    is_youtube_url,
)


class FakeYoutubeDL:
    """Stand-in for yt_dlp.YoutubeDL that writes a file instead of downloading."""

    last_options: dict | None = None

    def __init__(self, options):
        FakeYoutubeDL.last_options = options
        self.options = options

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def extract_info(self, url, download=False):
        out_dir = Path(self.options["outtmpl"]).parent
        file_path = out_dir / "My Video [abc123].mp4"
        file_path.write_bytes(b"x" * 1024)
        return {
            "id": "abc123",
            "title": "My Video",
            "duration": 42,
            "requested_downloads": [{"filepath": str(file_path)}],
        }


class FailingYoutubeDL(FakeYoutubeDL):
    def extract_info(self, url, download=False):
        raise yt_dlp.utils.DownloadError("ERROR: Video unavailable")


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://youtube.com/watch?v=dQw4w9WgXcQ",
        "https://m.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://youtu.be/dQw4w9WgXcQ",
        "http://www.youtube.com/shorts/abc123",
    ],
)
def test_is_youtube_url_accepts_youtube_links(url):
    assert is_youtube_url(url) is True


@pytest.mark.parametrize(
    "url",
    [
        "https://www.tiktok.com/@user/video/123",
        "https://vimeo.com/123",
        "https://notyoutube.com/watch?v=abc",
        "https://youtube.com.evil.example/watch?v=abc",
        "ftp://www.youtube.com/watch?v=abc",
        "not a url",
        "",
    ],
)
def test_is_youtube_url_rejects_other_links(url):
    assert is_youtube_url(url) is False


def test_youtube_rejects_non_youtube_url(download_dir):
    downloader = DownloadVideo(download_dir)

    with pytest.raises(ValueError, match="YouTube"):
        downloader.youtube("https://vimeo.com/123")

    assert not download_dir.exists()


def test_youtube_downloads_into_folder_and_returns_metadata(download_dir, monkeypatch):
    monkeypatch.setattr(retrieving_data.yt_dlp, "YoutubeDL", FakeYoutubeDL)

    result = DownloadVideo(download_dir).youtube("https://youtu.be/abc123")

    assert download_dir.is_dir()
    assert result == {
        "title": "My Video",
        "video_id": "abc123",
        "file_path": str(download_dir / "My Video [abc123].mp4"),
        "duration_seconds": 42,
        "file_size_bytes": 1024,
    }
    assert Path(result["file_path"]).is_file()


def test_youtube_requests_a_single_mp4_into_the_download_folder(
    download_dir, monkeypatch
):
    monkeypatch.setattr(retrieving_data.yt_dlp, "YoutubeDL", FakeYoutubeDL)

    DownloadVideo(download_dir).youtube("https://youtu.be/abc123")

    options = FakeYoutubeDL.last_options
    assert options["noplaylist"] is True
    assert options["noprogress"] is True
    assert options["merge_output_format"] == "mp4"
    assert Path(options["outtmpl"]).parent == download_dir
    # Instagram and TikTok "titles" are captions that can run to hundreds of
    # characters, so the template must truncate the title.
    assert "%(title).80s" in options["outtmpl"]


def test_youtube_wraps_download_errors(download_dir, monkeypatch):
    monkeypatch.setattr(retrieving_data.yt_dlp, "YoutubeDL", FailingYoutubeDL)

    with pytest.raises(VideoDownloadError, match="Video unavailable"):
        DownloadVideo(download_dir).youtube("https://youtu.be/abc123")


INSTAGRAM_REEL = (
    "https://www.instagram.com/reel/Dcik7_Zy3Ph/"
    "?utm_source=ig_web_copy_link&stkn=NTc4MTIwNjQ2YQ=="
)
TIKTOK_VIDEO = "https://www.tiktok.com/@tiktok/video/7106594312292453675"


@pytest.mark.parametrize(
    "url",
    [
        INSTAGRAM_REEL,
        "https://www.instagram.com/p/CxYz123AbCd/",
        "https://instagram.com/reels/Dcik7_Zy3Ph/",
        "https://www.instagram.com/tv/CxYz123AbCd/",
        "https://m.instagram.com/reel/Dcik7_Zy3Ph",
    ],
)
def test_is_instagram_url_accepts_post_reel_and_tv_links(url):
    assert is_instagram_url(url) is True


@pytest.mark.parametrize(
    "url",
    [
        "https://www.instagram.com/nasa/",
        "https://www.instagram.com/stories/nasa/123456/",
        "https://www.instagram.com/",
        "https://www.instagram.com/explore/",
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://instagram.com.evil.example/reel/Dcik7_Zy3Ph/",
        "ftp://www.instagram.com/reel/Dcik7_Zy3Ph/",
        "not a url",
        "",
    ],
)
def test_is_instagram_url_rejects_profiles_stories_and_other_sites(url):
    assert is_instagram_url(url) is False


@pytest.mark.parametrize(
    "url",
    [
        TIKTOK_VIDEO,
        "https://tiktok.com/@some.user/video/7106594312292453675?is_from_webapp=1",
        "https://m.tiktok.com/v/7106594312292453675.html",
        "https://vm.tiktok.com/ZMabcdef/",
        "https://vt.tiktok.com/ZSabcdef/",
        "https://www.tiktok.com/t/ZTabcdef/",
    ],
)
def test_is_tiktok_url_accepts_video_and_short_links(url):
    assert is_tiktok_url(url) is True


@pytest.mark.parametrize(
    "url",
    [
        "https://www.tiktok.com/@tiktok",
        "https://www.tiktok.com/",
        "https://www.tiktok.com/tag/fyp",
        "https://vm.tiktok.com/",
        "https://www.instagram.com/reel/Dcik7_Zy3Ph/",
        "https://tiktok.com.evil.example/@x/video/1",
        "ftp://www.tiktok.com/@tiktok/video/1",
        "not a url",
        "",
    ],
)
def test_is_tiktok_url_rejects_profiles_tags_and_other_sites(url):
    assert is_tiktok_url(url) is False


PLATFORMS = [
    pytest.param(
        "instagram", "Instagram", INSTAGRAM_REEL, TIKTOK_VIDEO, id="instagram"
    ),
    pytest.param("tiktok", "TikTok", TIKTOK_VIDEO, INSTAGRAM_REEL, id="tiktok"),
]


@pytest.mark.parametrize("method, platform, good_url, wrong_url", PLATFORMS)
def test_platform_method_rejects_url_from_another_platform(
    download_dir, method, platform, good_url, wrong_url
):
    downloader = DownloadVideo(download_dir)

    with pytest.raises(ValueError, match=platform):
        getattr(downloader, method)(wrong_url)

    assert not download_dir.exists()


@pytest.mark.parametrize("method, platform, good_url, wrong_url", PLATFORMS)
def test_platform_method_downloads_and_returns_metadata(
    download_dir, monkeypatch, method, platform, good_url, wrong_url
):
    monkeypatch.setattr(retrieving_data.yt_dlp, "YoutubeDL", FakeYoutubeDL)

    result = getattr(DownloadVideo(download_dir), method)(good_url)

    assert download_dir.is_dir()
    assert result == {
        "title": "My Video",
        "video_id": "abc123",
        "file_path": str(download_dir / "My Video [abc123].mp4"),
        "duration_seconds": 42,
        "file_size_bytes": 1024,
    }
    assert Path(FakeYoutubeDL.last_options["outtmpl"]).parent == download_dir


@pytest.mark.parametrize("method, platform, good_url, wrong_url", PLATFORMS)
def test_platform_method_wraps_download_errors(
    download_dir, monkeypatch, method, platform, good_url, wrong_url
):
    monkeypatch.setattr(retrieving_data.yt_dlp, "YoutubeDL", FailingYoutubeDL)

    with pytest.raises(VideoDownloadError, match="Video unavailable"):
        getattr(DownloadVideo(download_dir), method)(good_url)
