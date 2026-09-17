import pytest

from app.services.retrieving_data import VideoDownloadError
from app.services.summarization import SummarizationError
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
    "topic": None,
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


class FakeSummarizer:
    def __init__(self, topic="Video about agents.", error=None):
        self.topic = topic
        self.error = error
        self.texts = []

    def summarize(self, text):
        self.texts.append(text)
        if self.error:
            raise self.error
        return self.topic


def run(downloader=None, transcriber=None, translator=None, summarizer=None, **kwargs):
    return process_video(
        "https://youtu.be/abc123",
        "youtube",
        downloader or FakeDownloader(),
        transcriber or FakeTranscriber(Transcript("en", ["Hello.", "Bye."])),
        translator or FakeTranslator(Translation("fr", "Salut. Au revoir.")),
        summarizer or FakeSummarizer(),
        **kwargs,
    )


def test_full_pipeline_returns_metadata_transcript_translation_and_topic():
    transcriber = FakeTranscriber(Transcript("en", ["Hello.", "Bye."]))
    translator = FakeTranslator(Translation("fr", "Salut. Au revoir."))
    summarizer = FakeSummarizer("Video about agents.")

    result = run(transcriber=transcriber, translator=translator, summarizer=summarizer)

    assert result == {
        **METADATA,
        "transcript_language": "en",
        "transcript_text": "Hello. Bye.",
        "translation_language": "fr",
        "translation_text": "Salut. Au revoir.",
        "topic": "Video about agents.",
        "warnings": [],
    }
    assert transcriber.paths == [METADATA["file_path"]]
    assert translator.calls == [(["Hello.", "Bye."], "en")]
    # English speech: the summary is built from the English transcript.
    assert summarizer.texts == ["Hello. Bye."]


def test_download_errors_propagate_untouched():
    with pytest.raises(VideoDownloadError):
        run(downloader=FakeDownloader(error=VideoDownloadError("gone")))
    with pytest.raises(ValueError):
        run(downloader=FakeDownloader(error=ValueError("bad url")))


def test_transcription_disabled_skips_every_text_step_with_warning():
    transcriber = FakeTranscriber()
    translator = FakeTranslator()
    summarizer = FakeSummarizer()

    result = run(
        transcriber=transcriber,
        translator=translator,
        summarizer=summarizer,
        transcription_enabled=False,
    )

    assert result == {
        **METADATA,
        **EMPTY_TEXT_FIELDS,
        "warnings": ["Transcription is disabled."],
    }
    assert transcriber.paths == []
    assert translator.calls == []
    assert summarizer.texts == []


def test_transcription_failure_keeps_download_and_warns():
    translator = FakeTranslator()
    summarizer = FakeSummarizer()

    result = run(
        transcriber=FakeTranscriber(error=TranscriptionError("no audio")),
        translator=translator,
        summarizer=summarizer,
    )

    assert result == {
        **METADATA,
        **EMPTY_TEXT_FIELDS,
        "warnings": ["Transcription failed: no audio"],
    }
    assert translator.calls == []
    assert summarizer.texts == []


def test_translation_failure_keeps_transcript_and_topic_and_warns():
    result = run(translator=FakeTranslator(error=TranslationError("no weights")))

    assert result["transcript_text"] == "Hello. Bye."
    assert result["translation_language"] is None
    assert result["translation_text"] is None
    # The English transcript is still there, so the topic is still produced.
    assert result["topic"] == "Video about agents."
    assert result["warnings"] == ["Translation failed: no weights"]


def test_unsupported_language_keeps_transcript_and_warns():
    result = run(
        transcriber=FakeTranscriber(Transcript("rw", ["Muraho."])),
        translator=FakeTranslator(translation=None),
    )

    assert result["transcript_language"] == "rw"
    assert result["transcript_text"] == "Muraho."
    assert result["translation_text"] is None
    assert result["topic"] is None
    assert result["warnings"] == [
        "No translation: detected language 'rw' is not English or French.",
        "No summary: no English text available for language 'rw'.",
    ]


def test_french_speech_is_summarised_from_its_english_translation():
    summarizer = FakeSummarizer("A video about greetings.")

    result = run(
        transcriber=FakeTranscriber(Transcript("fr", ["Bonjour.", "Au revoir."])),
        translator=FakeTranslator(Translation("en", "Hello. Goodbye.")),
        summarizer=summarizer,
    )

    assert result["topic"] == "A video about greetings."
    assert summarizer.texts == ["Hello. Goodbye."]
    assert result["warnings"] == []


def test_french_speech_without_translation_has_no_summary():
    summarizer = FakeSummarizer()

    result = run(
        transcriber=FakeTranscriber(Transcript("fr", ["Bonjour."])),
        translator=FakeTranslator(error=TranslationError("no weights")),
        summarizer=summarizer,
    )

    assert result["topic"] is None
    assert summarizer.texts == []
    assert result["warnings"] == [
        "Translation failed: no weights",
        "No summary: no English text available for language 'fr'.",
    ]


def test_summary_failure_keeps_everything_else_and_warns():
    result = run(summarizer=FakeSummarizer(error=SummarizationError("no weights")))

    assert result["transcript_text"] == "Hello. Bye."
    assert result["translation_text"] == "Salut. Au revoir."
    assert result["topic"] is None
    assert result["warnings"] == ["Summary failed: no weights"]
