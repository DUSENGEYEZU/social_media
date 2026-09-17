"""Retrieve media from social media platforms."""

import re
from collections.abc import Callable
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import yt_dlp

YOUTUBE_HOSTS = frozenset(
    {
        "youtube.com",
        "www.youtube.com",
        "m.youtube.com",
        "music.youtube.com",
        "youtu.be",
    }
)

INSTAGRAM_HOSTS = frozenset({"instagram.com", "www.instagram.com", "m.instagram.com"})
# Single-video pages only: posts, reels and IGTV. Profiles and stories are not.
_INSTAGRAM_VIDEO_PATH = re.compile(r"^/(p|reel|reels|tv)/[A-Za-z0-9_-]+/?$")

TIKTOK_HOSTS = frozenset({"tiktok.com", "www.tiktok.com", "m.tiktok.com"})
# Short links from the mobile app: https://vm.tiktok.com/<code>/
TIKTOK_SHORT_HOSTS = frozenset({"vm.tiktok.com", "vt.tiktok.com"})
_TIKTOK_VIDEO_PATH = re.compile(
    r"^/(@[^/]+/video/\d+|v/\d+(\.html)?|t/[A-Za-z0-9]+)/?$"
)

FACEBOOK_HOSTS = frozenset(
    {
        "facebook.com",
        "www.facebook.com",
        "m.facebook.com",
        "web.facebook.com",
        "fb.com",
        "www.fb.com",
    }
)
# Short links from the share button: https://fb.watch/<code>/
FACEBOOK_SHORT_HOSTS = frozenset({"fb.watch"})
# Single-video pages: /<page>/videos/[<slug>/]<id>, /<page>/reels/<id>, /reel/<id>,
# /share/v/<code> and /share/r/<code>. Pages, groups and the videos tab are not.
_FACEBOOK_VIDEO_PATH = re.compile(
    r"^/(reel/\d+|share/[vr]/[A-Za-z0-9_-]+|[^/]+/videos/(?:[^/]+/)?\d+|[^/]+/reels/\d+)/?$"
)
# /watch/?v=<id> and /video.php?v=<id> carry the id in the query string.
_FACEBOOK_WATCH_PATHS = frozenset({"/watch", "/watch/", "/video.php"})

_HTTP_SCHEMES = frozenset({"http", "https"})


class VideoDownloadError(Exception):
    """Raised when a video could not be downloaded."""


def is_youtube_url(url: str) -> bool:
    """Return True when the URL points at a YouTube video page."""
    parsed = urlparse(url)
    return parsed.scheme in _HTTP_SCHEMES and parsed.netloc.lower() in YOUTUBE_HOSTS


def is_instagram_url(url: str) -> bool:
    """Return True when the URL points at a single Instagram post, reel or IGTV video."""
    parsed = urlparse(url)
    return (
        parsed.scheme in _HTTP_SCHEMES
        and parsed.netloc.lower() in INSTAGRAM_HOSTS
        and _INSTAGRAM_VIDEO_PATH.match(parsed.path) is not None
    )


def is_tiktok_url(url: str) -> bool:
    """Return True when the URL points at a single TikTok video or a TikTok short link."""
    parsed = urlparse(url)
    if parsed.scheme not in _HTTP_SCHEMES:
        return False
    host = parsed.netloc.lower()
    if host in TIKTOK_SHORT_HOSTS:
        return parsed.path.strip("/") != ""
    return host in TIKTOK_HOSTS and _TIKTOK_VIDEO_PATH.match(parsed.path) is not None


def is_facebook_url(url: str) -> bool:
    """Return True when the URL points at a single Facebook video, reel or share link."""
    parsed = urlparse(url)
    if parsed.scheme not in _HTTP_SCHEMES:
        return False
    host = parsed.netloc.lower()
    if host in FACEBOOK_SHORT_HOSTS:
        return parsed.path.strip("/") != ""
    if host not in FACEBOOK_HOSTS:
        return False
    if parsed.path in _FACEBOOK_WATCH_PATHS:
        return bool(parse_qs(parsed.query).get("v", [""])[0])
    return _FACEBOOK_VIDEO_PATH.match(parsed.path) is not None


class DownloadVideo:
    """Download videos from social media platforms into a local folder.

    One public method per platform. Each validates the URL for its platform and
    then hands off to the shared yt-dlp download.
    """

    def __init__(self, download_dir: str | Path) -> None:
        self.download_dir = Path(download_dir)

    def youtube(self, url: str) -> dict:
        """Download a YouTube video as mp4 and return its metadata."""
        return self._download(url, is_youtube_url, "YouTube")

    def instagram(self, url: str) -> dict:
        """Download an Instagram post, reel or IGTV video as mp4 and return its metadata."""
        return self._download(url, is_instagram_url, "Instagram")

    def tiktok(self, url: str) -> dict:
        """Download a TikTok video as mp4 and return its metadata."""
        return self._download(url, is_tiktok_url, "TikTok")

    def facebook(self, url: str) -> dict:
        """Download a public Facebook video or reel as mp4 and return its metadata."""
        return self._download(url, is_facebook_url, "Facebook")

    def _download(
        self, url: str, is_valid: Callable[[str], bool], platform: str
    ) -> dict:
        """Validate the URL for ``platform`` and download it with yt-dlp.

        Raises ValueError for a URL that is not a single video on that platform,
        and VideoDownloadError when yt-dlp cannot fetch the video.
        """
        if not is_valid(url):
            raise ValueError(f"Not a valid {platform} video URL: {url!r}")

        self.download_dir.mkdir(parents=True, exist_ok=True)

        options = {
            # Title is truncated: Instagram and TikTok use the caption as the
            # title, and captions can run to hundreds of characters.
            "outtmpl": str(self.download_dir / "%(title).80s [%(id)s].%(ext)s"),
            "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
            "merge_output_format": "mp4",
            "noplaylist": True,
            "quiet": True,
            "noprogress": True,
            "no_warnings": True,
        }

        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(url, download=True)
        except yt_dlp.utils.DownloadError as exc:
            raise VideoDownloadError(str(exc)) from exc

        file_path = Path(info["requested_downloads"][0]["filepath"])

        return {
            "title": info.get("title"),
            "video_id": info.get("id"),
            "file_path": str(file_path),
            "duration_seconds": info.get("duration"),
            "file_size_bytes": file_path.stat().st_size
            if file_path.is_file()
            else None,
        }
