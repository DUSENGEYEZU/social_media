from flask import current_app, request

from app.api import api_bp
from app.services.retrieving_data import DownloadVideo, VideoDownloadError


@api_bp.post("/videos/youtube")
def download_youtube_video():
    """Download a YouTube video into the configured folder.

    Body: {"url": "<YouTube video URL>"}
    Returns 201 with the video metadata, 400 for a bad request,
    502 when YouTube or yt-dlp fails.
    """
    payload = request.get_json(silent=True) or {}
    url = payload.get("url")
    if not isinstance(url, str) or not url.strip():
        return {"error": "Request body must be JSON with a non-empty 'url' field."}, 400

    downloader = DownloadVideo(current_app.config["DOWNLOAD_DIR"])
    try:
        metadata = downloader.youtube(url.strip())
    except ValueError as exc:
        return {"error": str(exc)}, 400
    except VideoDownloadError as exc:
        return {"error": f"Download failed: {exc}"}, 502

    return metadata, 201
