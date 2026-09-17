from flask import current_app, request

from app.api import api_bp
from app.services.retrieving_data import DownloadVideo, VideoDownloadError
from app.services.summarization import Summarizer
from app.services.transcription import Transcriber
from app.services.translation import Translator
from app.services.video_pipeline import process_video


def _download_from(platform_method: str):
    """Shared request handling for every platform download endpoint.

    Reads {"url": ...} from the JSON body, runs the download -> transcribe ->
    translate -> summarise pipeline for the named DownloadVideo method, and maps the outcome
    onto HTTP: 201 with metadata and text fields, 400 for a bad request or
    wrong-platform URL, 502 when the download itself fails.
    """
    payload = request.get_json(silent=True) or {}
    url = payload.get("url")
    if not isinstance(url, str) or not url.strip():
        return {"error": "Request body must be JSON with a non-empty 'url' field."}, 400

    downloader = DownloadVideo(current_app.config["DOWNLOAD_DIR"])
    transcriber = Transcriber(current_app.config["WHISPER_MODEL"])
    translator = Translator()
    summarizer = Summarizer()
    try:
        metadata = process_video(
            url.strip(),
            platform_method,
            downloader,
            transcriber,
            translator,
            summarizer,
            transcription_enabled=current_app.config["TRANSCRIPTION_ENABLED"],
        )
    except ValueError as exc:
        return {"error": str(exc)}, 400
    except VideoDownloadError as exc:
        return {"error": f"Download failed: {exc}"}, 502

    return metadata, 201


@api_bp.post("/videos/youtube")
def download_youtube_video():
    """Download a YouTube video.
    ---
    tags:
      - Videos
    description: >
      Downloads the video as an mp4 into the server's download folder and
      returns its metadata. The request blocks until the download finishes,
      so long videos mean long requests. Playlist URLs download only the
      single video they point at.
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required:
              - url
            properties:
              url:
                type: string
                format: uri
                description: Full URL of a YouTube video (youtube.com or youtu.be).
                example: https://www.youtube.com/watch?v=jNQXAC9IVRw
    responses:
      201:
        description: Video downloaded and saved; transcript, translation and topic included when available.
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/VideoMetadata'
      400:
        description: Body is not JSON, `url` is missing, or the URL is not a YouTube video.
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/Error'
      502:
        description: YouTube or yt-dlp failed, for example a private or removed video.
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/Error'
    """
    return _download_from("youtube")


@api_bp.post("/videos/instagram")
def download_instagram_video():
    """Download an Instagram video.
    ---
    tags:
      - Videos
    description: >
      Downloads a public Instagram post, reel or IGTV video as an mp4 into the
      server's download folder and returns its metadata. Profile and story
      URLs are rejected. Private accounts and login-only content are not
      supported. The request blocks until the download finishes.
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required:
              - url
            properties:
              url:
                type: string
                format: uri
                description: >
                  Full URL of an Instagram post, reel or IGTV video, for example
                  instagram.com/reel/<id>/ or instagram.com/p/<id>/.
                example: https://www.instagram.com/reel/Dcik7_Zy3Ph/
    responses:
      201:
        description: Video downloaded and saved; transcript, translation and topic included when available.
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/VideoMetadata'
      400:
        description: Body is not JSON, `url` is missing, or the URL is not a single Instagram video.
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/Error'
      502:
        description: Instagram or yt-dlp failed, for example a private account or a removed post.
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/Error'
    """
    return _download_from("instagram")


@api_bp.post("/videos/tiktok")
def download_tiktok_video():
    """Download a TikTok video.
    ---
    tags:
      - Videos
    description: >
      Downloads a TikTok video as an mp4 into the server's download folder and
      returns its metadata. Accepts full video URLs and the short links the
      TikTok app shares (vm.tiktok.com, vt.tiktok.com). Profile and tag URLs
      are rejected. The request blocks until the download finishes.
    requestBody:
      required: true
      content:
        application/json:
          schema:
            type: object
            required:
              - url
            properties:
              url:
                type: string
                format: uri
                description: >
                  Full URL of a TikTok video, for example
                  tiktok.com/@user/video/<id> or a vm.tiktok.com short link.
                example: https://www.tiktok.com/@tiktok/video/7106594312292453675
    responses:
      201:
        description: Video downloaded and saved; transcript, translation and topic included when available.
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/VideoMetadata'
      400:
        description: Body is not JSON, `url` is missing, or the URL is not a single TikTok video.
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/Error'
      502:
        description: TikTok or yt-dlp failed, for example a removed or region-locked video.
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/Error'
    """
    return _download_from("tiktok")
