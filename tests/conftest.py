import pytest

from app import create_app
from app.config import Config


@pytest.fixture
def download_dir(tmp_path):
    return tmp_path / "downloads"


@pytest.fixture
def app(download_dir):
    class TestConfig(Config):
        TESTING = True
        SECRET_KEY = "test-secret"
        DOWNLOAD_DIR = str(download_dir)
        TRANSCRIPTION_ENABLED = False

    return create_app(TestConfig)


@pytest.fixture
def client(app):
    return app.test_client()
