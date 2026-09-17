import os
from pathlib import Path

# The repository root is two levels above this file: app/config.py -> app -> repo.
REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DOWNLOAD_DIR = REPO_ROOT / "downloaded_videos"


def env_flag(name: str, default: bool) -> bool:
    """Read a boolean from the environment. Accepts 1/0, true/false, yes/no, on/off."""
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-me")
    # Downloaded videos live in a git-ignored folder inside the repository.
    DOWNLOAD_DIR = os.environ.get("DOWNLOAD_DIR", str(DEFAULT_DOWNLOAD_DIR))
    # Speech-to-text model size for faster-whisper: tiny, base, small, medium, large-v3.
    WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "small")
    # Turn off to skip transcription and translation (fast, download-only responses).
    TRANSCRIPTION_ENABLED = env_flag("TRANSCRIPTION_ENABLED", True)
