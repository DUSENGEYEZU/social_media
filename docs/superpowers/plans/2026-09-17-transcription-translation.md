---
noteId: "d0ffdcf0b26b11f18d914dfa2d9ccc1b"
tags: []

---

# Transcription and Translation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every downloaded video gets a local speech-to-text transcript and an English/French translation, returned in the same API response.

**Architecture:** Two new service classes (`Transcriber`, `Translator`) wrap faster-whisper and MarianMT behind small interfaces with module-level model caches. A `process_video` pipeline function composes download, transcription and translation with graceful degradation. Route handlers call the pipeline; `DownloadVideo` is untouched.

**Tech Stack:** Python 3.13, Flask 3, faster-whisper, transformers + torch (CPU) + sentencepiece + sacremoses, pytest.

**Spec:** `docs/superpowers/specs/2026-09-17-transcription-translation-design.md`

**Commits:** Project convention is that the owner commits himself (see memory `no-push-user-pushes-himself`). Tasks therefore end at "all tests green" instead of a commit step.

## Global Constraints

- No external API keys. All models run locally.
- Test suite must stay offline: fake `WhisperModel` and the Marian loader; never download a model in tests.
- Existing 72 tests keep passing.
- New response fields exactly: `transcript_language`, `transcript_text`, `translation_language`, `translation_text`, `warnings`.
- Language rule: `en` -> `fr`, `fr` -> `en`, anything else -> `null` translation plus a warning.
- A successful download is never turned into an error by a later step.
- Run everything with `uv run ...`; format with `uv run ruff format .`; lint with `uv run ruff check .`.

---

### Task 1: Dependencies and configuration

**Files:**
- Modify: `pyproject.toml` (dependencies; add CPU torch index for Linux)
- Modify: `app/config.py`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `Config.WHISPER_MODEL: str` (default `"small"`), `Config.TRANSCRIPTION_ENABLED: bool` (default `True`), helper `env_flag(name: str, default: bool) -> bool`.

- [ ] **Step 1: Add dependencies**

```bash
uv add faster-whisper transformers torch sentencepiece sacremoses
```

Then add to `pyproject.toml` so a Linux server gets the CPU-only torch wheel instead of a 2 GB CUDA build:

```toml
[[tool.uv.index]]
name = "pytorch-cpu"
url = "https://download.pytorch.org/whl/cpu"
explicit = true

[tool.uv.sources]
torch = [{ index = "pytorch-cpu", marker = "sys_platform == 'linux'" }]
```

Run `uv lock && uv sync` and confirm `uv run python -c "import faster_whisper, transformers, torch; print('ok')"` prints `ok`.

- [ ] **Step 2: Write the failing config tests** (append to `tests/test_config.py`)

```python
import pytest

from app.config import env_flag


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
```

- [ ] **Step 3: Run to verify failure**: `uv run pytest tests/test_config.py -q` -> ImportError on `env_flag`.

- [ ] **Step 4: Implement in `app/config.py`**

```python
def env_flag(name: str, default: bool) -> bool:
    """Read a boolean from the environment. Accepts 1/0, true/false, yes/no, on/off."""
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Config:
    ...
    # Speech-to-text model size for faster-whisper: tiny, base, small, medium, large-v3.
    WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "small")
    # Turn off to skip transcription and translation (fast downloads only).
    TRANSCRIPTION_ENABLED = env_flag("TRANSCRIPTION_ENABLED", True)
```

- [ ] **Step 5: Run**: `uv run pytest tests/test_config.py -q` -> all pass.

---

### Task 2: Transcriber service

**Files:**
- Create: `app/services/transcription.py`
- Test: `tests/test_transcription.py`

**Interfaces:**
- Produces: `class Transcript(language: str, segments: list[str])` with property `text -> str` (segments stripped and joined by single spaces, empty ones dropped); `class TranscriptionError(Exception)`; `class Transcriber(model_size: str = "small")` with `transcribe(media_path: str | Path) -> Transcript`; module attribute `_MODELS: dict[str, WhisperModel]` (cache, cleared by tests).

- [ ] **Step 1: Write failing tests** (`tests/test_transcription.py`)

```python
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.services import transcription
from app.services.transcription import Transcriber, TranscriptionError, Transcript


class FakeWhisperModel:
    instances: list = []
    segments = [" Hello there. ", "How are you?", "   "]
    language = "en"

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
```

- [ ] **Step 2: Run to verify failure**: `uv run pytest tests/test_transcription.py -q` -> ModuleNotFoundError.

- [ ] **Step 3: Implement `app/services/transcription.py`**

```python
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
            texts = [
                segment.text for segment in segments
            ]  # generator: iterating runs the decode
        except Exception as exc:
            raise TranscriptionError(f"Transcription failed: {exc}") from exc
        return Transcript(language=info.language, segments=texts)
```

- [ ] **Step 4: Run**: `uv run pytest tests/test_transcription.py -q` -> all pass.

---

### Task 3: Translator service

**Files:**
- Create: `app/services/translation.py`
- Test: `tests/test_translation.py`

**Interfaces:**
- Produces: `class Translation(language: str, text: str)`; `class TranslationError(Exception)`; `TARGET_LANGUAGE = {"en": "fr", "fr": "en"}`; `class Translator` with `target_language(source_language: str) -> str | None` and `translate(segments: list[str], source_language: str) -> Translation | None`; module function `_load_marian(model_name: str) -> tuple[tokenizer, model]` (seam for tests); `BATCH_SIZE = 16`.

- [ ] **Step 1: Write failing tests** (`tests/test_translation.py`)

```python
import pytest

from app.services import translation
from app.services.translation import Translation, TranslationError, Translator


class FakeTokenizer:
    def __call__(self, texts, **kwargs):
        return {"texts": list(texts)}

    def batch_decode(self, outputs, skip_special_tokens=True):
        return list(outputs)


class FakeModel:
    def __init__(self, tag):
        self.tag = tag
        self.batches: list[list[str]] = []

    def generate(self, texts):
        self.batches.append(texts)
        return [f"[{self.tag}] {t}" for t in texts]


@pytest.fixture
def fake_marian(monkeypatch):
    loaded: dict[str, FakeModel] = {}

    def _load(model_name):
        if model_name not in loaded:
            loaded[model_name] = FakeModel(model_name.rsplit("-", 1)[-1])
        return FakeTokenizer(), loaded[model_name]

    monkeypatch.setattr(translation, "_load_marian", _load)
    return loaded


@pytest.mark.parametrize("source, target", [("en", "fr"), ("fr", "en"), ("EN", "fr")])
def test_target_language_swaps_english_and_french(source, target):
    assert Translator().target_language(source) == target


@pytest.mark.parametrize("source", ["rw", "sw", "de", ""])
def test_target_language_is_none_for_other_languages(source):
    assert Translator().target_language(source) is None


def test_translate_english_segments_to_french(fake_marian):
    result = Translator().translate([" Hello. ", "", "Bye."], "en")

    assert result == Translation(language="fr", text="[fr] Hello. [fr] Bye.")
    assert list(fake_marian) == ["Helsinki-NLP/opus-mt-en-fr"]


def test_translate_french_segments_to_english(fake_marian):
    result = Translator().translate(["Bonjour."], "fr")

    assert result == Translation(language="en", text="[en] Bonjour.")
    assert list(fake_marian) == ["Helsinki-NLP/opus-mt-fr-en"]


def test_translate_returns_none_for_unsupported_language(fake_marian):
    assert Translator().translate(["Muraho."], "rw") is None
    assert fake_marian == {}


def test_translate_batches_long_transcripts(fake_marian):
    segments = [f"Sentence {i}." for i in range(40)]

    Translator().translate(segments, "en")

    batches = fake_marian["Helsinki-NLP/opus-mt-en-fr"].batches
    assert [len(b) for b in batches] == [16, 16, 8]


def test_translate_empty_transcript_gives_empty_text(fake_marian):
    assert Translator().translate(["", "  "], "en") == Translation(
        language="fr", text=""
    )
    assert fake_marian == {}


def test_translate_wraps_model_errors(monkeypatch):
    def _explode(model_name):
        raise RuntimeError("no weights")

    monkeypatch.setattr(translation, "_load_marian", _explode)

    with pytest.raises(TranslationError, match="no weights"):
        Translator().translate(["Hello."], "en")
```

- [ ] **Step 2: Run to verify failure**: `uv run pytest tests/test_translation.py -q` -> ModuleNotFoundError.

- [ ] **Step 3: Implement `app/services/translation.py`**

```python
"""English <-> French translation of transcripts with local MarianMT models."""

from dataclasses import dataclass

TARGET_LANGUAGE = {"en": "fr", "fr": "en"}
MODEL_NAMES = {
    ("en", "fr"): "Helsinki-NLP/opus-mt-en-fr",
    ("fr", "en"): "Helsinki-NLP/opus-mt-fr-en",
}
# Marian models accept ~512 tokens; Whisper segments are short, so batch by count.
BATCH_SIZE = 16


class TranslationError(Exception):
    """Raised when the translation model fails."""


@dataclass(frozen=True)
class Translation:
    language: str
    text: str


_MODELS: dict[str, tuple] = {}


def _load_marian(model_name: str) -> tuple:
    """Load (tokenizer, model) once per model name. Imports lazily: torch is heavy."""
    if model_name not in _MODELS:
        from transformers import MarianMTModel, MarianTokenizer

        tokenizer = MarianTokenizer.from_pretrained(model_name)
        model = MarianMTModel.from_pretrained(model_name)
        model.eval()
        _MODELS[model_name] = (tokenizer, model)
    return _MODELS[model_name]


class Translator:
    """Translate English to French and French to English."""

    def target_language(self, source_language: str) -> str | None:
        return TARGET_LANGUAGE.get(source_language.lower())

    def translate(
        self, segments: list[str], source_language: str
    ) -> Translation | None:
        target = self.target_language(source_language)
        if target is None:
            return None
        texts = [s.strip() for s in segments if s.strip()]
        if not texts:
            return Translation(language=target, text="")

        model_name = MODEL_NAMES[(source_language.lower(), target)]
        try:
            tokenizer, model = _load_marian(model_name)
            outputs: list[str] = []
            for start in range(0, len(texts), BATCH_SIZE):
                batch = texts[start : start + BATCH_SIZE]
                inputs = tokenizer(
                    batch, return_tensors="pt", padding=True, truncation=True
                )
                generated = model.generate(**inputs)
                outputs.extend(
                    tokenizer.batch_decode(generated, skip_special_tokens=True)
                )
        except Exception as exc:
            raise TranslationError(f"Translation failed: {exc}") from exc

        return Translation(language=target, text=" ".join(o.strip() for o in outputs))
```

- [ ] **Step 4: Run**: `uv run pytest tests/test_translation.py -q` -> all pass.

---

### Task 4: Video pipeline

**Files:**
- Create: `app/services/video_pipeline.py`
- Test: `tests/test_video_pipeline.py`

**Interfaces:**
- Consumes: `DownloadVideo` methods (return metadata dict with `file_path`), `Transcriber.transcribe`, `Translator.translate`, `TranscriptionError`, `TranslationError`.
- Produces: `process_video(url: str, platform_method: str, downloader, transcriber, translator, *, transcription_enabled: bool = True) -> dict`. Download exceptions (`ValueError`, `VideoDownloadError`) propagate unchanged.

- [ ] **Step 1: Write failing tests** (`tests/test_video_pipeline.py`)

```python
import pytest

from app.services.retrieving_data import VideoDownloadError
from app.services.transcription import Transcript, TranscriptionError
from app.services.translation import Translation, TranslationError
from app.services.video_pipeline import process_video

METADATA = {
    "title": "My Video",
    "video_id": "abc123",
    "file_path": "/downloads/My Video [abc123].mp4",
    "duration_seconds": 42,
    "file_size_bytes": 1024,
}
EMPTY_TEXT_FIELDS = {
    "transcript_language": None,
    "transcript_text": None,
    "translation_language": None,
    "translation_text": None,
}


class FakeDownloader:
    def __init__(self, error=None):
        self.error = error
        self.calls = []

    def youtube(self, url):
        self.calls.append(("youtube", url))
        if self.error:
            raise self.error
        return dict(METADATA)


class FakeTranscriber:
    def __init__(self, transcript=None, error=None):
        self.transcript = transcript
        self.error = error
        self.paths = []

    def transcribe(self, path):
        self.paths.append(path)
        if self.error:
            raise self.error
        return self.transcript


class FakeTranslator:
    def __init__(self, translation=None, error=None):
        self.translation = translation
        self.error = error
        self.calls = []

    def translate(self, segments, source_language):
        self.calls.append((segments, source_language))
        if self.error:
            raise self.error
        return self.translation


def run(downloader=None, transcriber=None, translator=None, **kwargs):
    return process_video(
        "https://youtu.be/abc123",
        "youtube",
        downloader or FakeDownloader(),
        transcriber or FakeTranscriber(Transcript("en", ["Hello.", "Bye."])),
        translator or FakeTranslator(Translation("fr", "Salut. Au revoir.")),
        **kwargs,
    )


def test_full_pipeline_returns_metadata_transcript_and_translation():
    transcriber = FakeTranscriber(Transcript("en", ["Hello.", "Bye."]))
    translator = FakeTranslator(Translation("fr", "Salut. Au revoir."))

    result = run(transcriber=transcriber, translator=translator)

    assert result == {
        **METADATA,
        "transcript_language": "en",
        "transcript_text": "Hello. Bye.",
        "translation_language": "fr",
        "translation_text": "Salut. Au revoir.",
        "warnings": [],
    }
    assert transcriber.paths == [METADATA["file_path"]]
    assert translator.calls == [(["Hello.", "Bye."], "en")]


def test_download_errors_propagate_untouched():
    with pytest.raises(VideoDownloadError):
        run(downloader=FakeDownloader(error=VideoDownloadError("gone")))
    with pytest.raises(ValueError):
        run(downloader=FakeDownloader(error=ValueError("bad url")))


def test_transcription_disabled_skips_both_steps_with_warning():
    transcriber = FakeTranscriber()
    translator = FakeTranslator()

    result = run(
        transcriber=transcriber, translator=translator, transcription_enabled=False
    )

    assert result == {
        **METADATA,
        **EMPTY_TEXT_FIELDS,
        "warnings": ["Transcription is disabled."],
    }
    assert transcriber.paths == []
    assert translator.calls == []


def test_transcription_failure_keeps_download_and_warns():
    translator = FakeTranslator()

    result = run(
        transcriber=FakeTranscriber(error=TranscriptionError("no audio")),
        translator=translator,
    )

    assert result == {
        **METADATA,
        **EMPTY_TEXT_FIELDS,
        "warnings": ["Transcription failed: no audio"],
    }
    assert translator.calls == []


def test_translation_failure_keeps_transcript_and_warns():
    result = run(translator=FakeTranslator(error=TranslationError("no weights")))

    assert result["transcript_text"] == "Hello. Bye."
    assert result["translation_language"] is None
    assert result["translation_text"] is None
    assert result["warnings"] == ["Translation failed: no weights"]


def test_unsupported_language_keeps_transcript_and_warns():
    result = run(
        transcriber=FakeTranscriber(Transcript("rw", ["Muraho."])),
        translator=FakeTranslator(translation=None),
    )

    assert result["transcript_language"] == "rw"
    assert result["transcript_text"] == "Muraho."
    assert result["translation_text"] is None
    assert result["warnings"] == [
        "No translation: detected language 'rw' is not English or French."
    ]
```

- [ ] **Step 2: Run to verify failure**: `uv run pytest tests/test_video_pipeline.py -q` -> ModuleNotFoundError.

- [ ] **Step 3: Implement `app/services/video_pipeline.py`**

```python
"""Download a video, transcribe it, translate the transcript.

A download that succeeded is never discarded because a later step failed:
those steps degrade to null fields plus an entry in ``warnings``.
"""

from app.services.transcription import TranscriptionError
from app.services.translation import TranslationError

TEXT_FIELDS = (
    "transcript_language",
    "transcript_text",
    "translation_language",
    "translation_text",
)


def process_video(
    url: str,
    platform_method: str,
    downloader,
    transcriber,
    translator,
    *,
    transcription_enabled: bool = True,
) -> dict:
    result = getattr(downloader, platform_method)(url)
    result.update({field: None for field in TEXT_FIELDS})
    warnings: list[str] = []
    result["warnings"] = warnings

    if not transcription_enabled:
        warnings.append("Transcription is disabled.")
        return result

    try:
        transcript = transcriber.transcribe(result["file_path"])
    except TranscriptionError as exc:
        warnings.append(f"Transcription failed: {exc}")
        return result
    result["transcript_language"] = transcript.language
    result["transcript_text"] = transcript.text

    try:
        translation = translator.translate(transcript.segments, transcript.language)
    except TranslationError as exc:
        warnings.append(f"Translation failed: {exc}")
        return result
    if translation is None:
        warnings.append(
            f"No translation: detected language {transcript.language!r} is not English or French."
        )
        return result
    result["translation_language"] = translation.language
    result["translation_text"] = translation.text
    return result
```

- [ ] **Step 4: Run**: `uv run pytest tests/test_video_pipeline.py -q` -> all pass.

---

### Task 5: Wire the endpoints and Swagger schema

**Files:**
- Modify: `app/api/videos.py` (`_download_from`)
- Modify: `app/docs.py` (`VideoMetadata` schema)
- Modify: `tests/conftest.py` (TestConfig gets `TRANSCRIPTION_ENABLED = False`)
- Modify: `tests/test_videos_api.py`
- Modify: `tests/test_docs.py`

**Interfaces:**
- Consumes: `process_video`, `Transcriber`, `Translator`, `Config.WHISPER_MODEL`, `Config.TRANSCRIPTION_ENABLED`.

- [ ] **Step 1: Update tests**

In `tests/conftest.py` add `TRANSCRIPTION_ENABLED = False` to `TestConfig` so existing endpoint tests stay fast and offline.

In `tests/test_videos_api.py`, every `assert response.get_json() == METADATA` becomes
`assert response.get_json() == DISABLED_RESPONSE` where:

```python
DISABLED_RESPONSE = {
    **METADATA,
    "transcript_language": None,
    "transcript_text": None,
    "translation_language": None,
    "translation_text": None,
    "warnings": ["Transcription is disabled."],
}
```

Append a happy-path test that turns transcription on and fakes the two services:

```python
from app.services.transcription import Transcript
from app.services.translation import Translation


class FakeTranscriber:
    def __init__(self, model_size):
        FakeTranscriber.model_size = model_size

    def transcribe(self, path):
        return Transcript("en", ["Hello.", "Bye."])


class FakeTranslator:
    def translate(self, segments, source_language):
        return Translation("fr", "Salut. Au revoir.")


def test_post_youtube_with_transcription_returns_text_fields(
    app, client, fake_downloader, monkeypatch
):
    app.config["TRANSCRIPTION_ENABLED"] = True
    app.config["WHISPER_MODEL"] = "tiny"
    monkeypatch.setattr(videos, "Transcriber", FakeTranscriber)
    monkeypatch.setattr(videos, "Translator", FakeTranslator)

    response = client.post(
        "/api/v1/videos/youtube", json={"url": "https://youtu.be/abc123"}
    )

    assert response.status_code == 201
    body = response.get_json()
    assert body["transcript_language"] == "en"
    assert body["transcript_text"] == "Hello. Bye."
    assert body["translation_language"] == "fr"
    assert body["translation_text"] == "Salut. Au revoir."
    assert body["warnings"] == []
    assert FakeTranscriber.model_size == "tiny"
```

In `tests/test_docs.py` extend `test_openapi_spec_defines_video_metadata_schema` so the expected property set also contains `transcript_language`, `transcript_text`, `translation_language`, `translation_text`, `warnings`.

- [ ] **Step 2: Run to verify failure**: `uv run pytest tests/test_videos_api.py tests/test_docs.py -q` -> equality failures and missing schema fields.

- [ ] **Step 3: Implement**

`app/api/videos.py`:

```python
from app.services.retrieving_data import DownloadVideo, VideoDownloadError
from app.services.transcription import Transcriber
from app.services.translation import Translator
from app.services.video_pipeline import process_video


def _download_from(platform_method: str):
    ...
    downloader = DownloadVideo(current_app.config["DOWNLOAD_DIR"])
    transcriber = Transcriber(current_app.config["WHISPER_MODEL"])
    translator = Translator()
    try:
        metadata = process_video(
            url.strip(),
            platform_method,
            downloader,
            transcriber,
            translator,
            transcription_enabled=current_app.config["TRANSCRIPTION_ENABLED"],
        )
    except ValueError as exc:
        return {"error": str(exc)}, 400
    except VideoDownloadError as exc:
        return {"error": f"Download failed: {exc}"}, 502
    return metadata, 201
```

`app/docs.py` `VideoMetadata.properties` gains:

```python
"transcript_language": {"type": "string", "nullable": True, "example": "en",
    "description": "ISO 639-1 code of the spoken language detected by Whisper."},
"transcript_text": {"type": "string", "nullable": True, "example": "Magnitude is a free, open-source project..."},
"translation_language": {"type": "string", "nullable": True, "example": "fr",
    "description": "fr for English speech, en for French speech, null otherwise."},
"translation_text": {"type": "string", "nullable": True, "example": "Magnitude est un projet gratuit et open source..."},
"warnings": {"type": "array", "items": {"type": "string"},
    "description": "Non-fatal problems, e.g. transcription failed or language not supported."},
```

Also update the three endpoint docstrings' `201` description to "Video downloaded and saved; transcript and translation included when available."

- [ ] **Step 4: Run the whole suite**: `uv run pytest -q` -> all pass. Then `uv run ruff format . && uv run ruff check .`.

---

### Task 6: Documentation, env template, end-to-end run

**Files:**
- Modify: `README.md`, `.env.example`

- [ ] **Step 1: `.env.example`** add:

```
# Speech-to-text model for faster-whisper: tiny, base, small (default), medium, large-v3.
# Bigger is more accurate and slower. First use downloads the model (~500 MB for small).
# WHISPER_MODEL=small
# Set to false to skip transcription and translation (downloads only).
# TRANSCRIPTION_ENABLED=true
```

- [ ] **Step 2: README** add a "Transcription and translation" section after the endpoint docs covering: what happens on every download, the five new fields with an example, the language rule, first-run model downloads (~1.1 GB into `~/.cache/huggingface`), expected timing (15-40 s per minute of speech on Apple Silicon CPU), the two settings, and the `warnings` behaviour. Update the tech stack table and the configuration table.

- [ ] **Step 3: End-to-end** with the server running on port 5001 and `TRANSCRIPTION_ENABLED` unset:

```bash
curl -s -X POST http://127.0.0.1:5001/api/v1/videos/tiktok \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.tiktok.com/@future.with.ai98/video/7682325736807582984"}' --max-time 900
```

Expected: 201 with `transcript_language: "en"`, English transcript about Magnitude, `translation_language: "fr"`, French text, `warnings: []`. First run includes model downloads; note the time taken.

- [ ] **Step 4: Final check**: `uv run pytest -q`, `uv run ruff check .`, `uv run ruff format --check .` all clean.
