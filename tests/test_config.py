from pathlib import Path

from app.config import Config


def test_download_dir_defaults_to_folder_next_to_the_repository():
    repo_root = Path(__file__).resolve().parents[1]

    assert Path(Config.DOWNLOAD_DIR) == repo_root.parent / "downloaded_youtube_videos"
