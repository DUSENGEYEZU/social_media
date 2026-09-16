"""Retrieve media from social media platforms."""

from pathlib import Path
from urllib.parse import urlparse

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


class VideoDownloadError(Exception):
    """Raised when a video could not be downloaded."""


def is_youtube_url(url: str) -> bool:
    """Return True when the URL points at a YouTube video page."""
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and parsed.netloc.lower() in YOUTUBE_HOSTS


class DownloadVideo:
    """Download videos from social media platforms into a local folder."""

    def __init__(self, download_dir: str | Path) -> None:
        self.download_dir = Path(download_dir)

    def youtube(self, url: str) -> dict:
        """Download a YouTube video as mp4 and return its metadata.

        Raises ValueError for a non-YouTube URL and VideoDownloadError when
        yt-dlp cannot fetch the video.
        """
        if not is_youtube_url(url):
            raise ValueError(f"Not a YouTube URL: {url!r}")

        self.download_dir.mkdir(parents=True, exist_ok=True)

        options = {
            "outtmpl": str(self.download_dir / "%(title)s [%(id)s].%(ext)s"),
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
