from pathlib import Path

import pytest

from app.config import Config, env_flag


def test_download_dir_defaults_to_folder_inside_the_repository():
    repo_root = Path(__file__).resolve().parents[1]

    assert Path(Config.DOWNLOAD_DIR) == repo_root / "downloaded_videos"


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on", " True "])
def test_env_flag_reads_truthy_values(monkeypatch, value):
    monkeypatch.setenv("SOME_FLAG", value)
    assert env_flag("SOME_FLAG", default=False) is True


@pytest.mark.parametrize("value", ["0", "false", "no", "off", ""])
def test_env_flag_reads_falsy_values(monkeypatch, value):
    monkeypatch.setenv("SOME_FLAG", value)
    assert env_flag("SOME_FLAG", default=True) is False


def test_env_flag_uses_default_when_unset(monkeypatch):
    monkeypatch.delenv("SOME_FLAG", raising=False)
    assert env_flag("SOME_FLAG", default=True) is True
    assert env_flag("SOME_FLAG", default=False) is False


def test_transcription_settings_have_defaults():
    assert Config.WHISPER_MODEL == "small"
    assert Config.TRANSCRIPTION_ENABLED is True
