import os
from pathlib import Path

# The repository root is two levels above this file: app/config.py -> app -> repo.
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DOWNLOAD_DIR = REPO_ROOT.parent / "downloaded_youtube_videos"


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-me")
    # Downloaded videos are kept outside the repository so they are never committed.
    DOWNLOAD_DIR = os.environ.get("DOWNLOAD_DIR", str(DEFAULT_DOWNLOAD_DIR))
