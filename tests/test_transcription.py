from types import SimpleNamespace
from typing import ClassVar

import pytest

from app.services import transcription
from app.services.transcription import Transcriber, Transcript, TranscriptionError


class FakeWhisperModel:
    instances: ClassVar[list] = []
    segments: ClassVar[list[str]] = [" Hello there. ", "How are you?", "   "]
    language: ClassVar[str] = "en"

    def __init__(self, model_size, **kwargs):
        self.model_size = model_size
        self.kwargs = kwargs
        self.calls = []
        FakeWhisperModel.instances.append(self)

    def transcribe(self, path, **kwargs):
        self.calls.append((path, kwargs))
        segments = (SimpleNamespace(text=t) for t in FakeWhisperModel.segments)
        info = SimpleNamespace(language=FakeWhisperModel.language)
        return segments, info


class ExplodingWhisperModel(FakeWhisperModel):
    def transcribe(self, path, **kwargs):
        raise RuntimeError("decoder blew up")


@pytest.fixture
def fake_whisper(monkeypatch):
    FakeWhisperModel.instances = []
    FakeWhisperModel.segments = [" Hello there. ", "How are you?", "   "]
    FakeWhisperModel.language = "en"
    monkeypatch.setattr(transcription.faster_whisper, "WhisperModel", FakeWhisperModel)
    monkeypatch.setattr(transcription, "_MODELS", {})
    return FakeWhisperModel


@pytest.fixture
def media_file(tmp_path):
    f = tmp_path / "clip.mp4"
    f.write_bytes(b"\x00" * 16)
    return f


def test_transcript_text_joins_non_empty_segments():
    t = Transcript(language="fr", segments=[" Bonjour. ", "", "  Ça va ?  "])
    assert t.text == "Bonjour. Ça va ?"


def test_transcribe_returns_language_and_segments(fake_whisper, media_file):
    result = Transcriber("small").transcribe(media_file)

    assert result == Transcript(
        language="en", segments=[" Hello there. ", "How are you?", "   "]
    )
    assert result.text == "Hello there. How are you?"
    assert fake_whisper.instances[0].calls[0][0] == str(media_file)


def test_transcribe_loads_model_once_per_size(fake_whisper, media_file):
    transcriber = Transcriber("small")
    transcriber.transcribe(media_file)
    Transcriber("small").transcribe(media_file)

    assert len(fake_whisper.instances) == 1
    assert fake_whisper.instances[0].model_size == "small"


def test_transcribe_runs_on_cpu_with_int8(fake_whisper, media_file):
    Transcriber("small").transcribe(media_file)

    kwargs = fake_whisper.instances[0].kwargs
    assert kwargs["device"] == "cpu"
    assert kwargs["compute_type"] == "int8"


def test_transcribe_missing_file_raises_before_loading_model(fake_whisper, tmp_path):
    with pytest.raises(TranscriptionError, match="not found"):
        Transcriber("small").transcribe(tmp_path / "missing.mp4")

    assert fake_whisper.instances == []


def test_transcribe_wraps_model_errors(monkeypatch, media_file):
    monkeypatch.setattr(
        transcription.faster_whisper, "WhisperModel", ExplodingWhisperModel
    )
    monkeypatch.setattr(transcription, "_MODELS", {})

    with pytest.raises(TranscriptionError, match="decoder blew up"):
        Transcriber("small").transcribe(media_file)
