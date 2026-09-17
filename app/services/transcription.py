"""Speech-to-text for downloaded videos, using faster-whisper on the CPU."""

from dataclasses import dataclass
from pathlib import Path

import faster_whisper


class TranscriptionError(Exception):
    """Raised when a media file could not be transcribed."""


@dataclass(frozen=True)
class Transcript:
    language: str
    segments: list[str]

    @property
    def text(self) -> str:
        return " ".join(s.strip() for s in self.segments if s.strip())


# Loaded models keyed by size. Loading takes seconds, so keep them for the process lifetime.
_MODELS: dict[str, "faster_whisper.WhisperModel"] = {}


def _load_model(model_size: str) -> "faster_whisper.WhisperModel":
    if model_size not in _MODELS:
        _MODELS[model_size] = faster_whisper.WhisperModel(
            model_size, device="cpu", compute_type="int8"
        )
    return _MODELS[model_size]


class Transcriber:
    """Transcribe the speech in a media file and detect its language."""

    def __init__(self, model_size: str = "small") -> None:
        self.model_size = model_size

    def transcribe(self, media_path: str | Path) -> Transcript:
        path = Path(media_path)
        if not path.is_file():
            raise TranscriptionError(f"Media file not found: {path}")
        try:
            model = _load_model(self.model_size)
            segments, info = model.transcribe(str(path), beam_size=5, vad_filter=True)
            # `segments` is a generator: iterating it is what runs the decoder.
            texts = [segment.text for segment in segments]
        except Exception as exc:
            raise TranscriptionError(f"Transcription failed: {exc}") from exc
        return Transcript(language=info.language, segments=texts)
