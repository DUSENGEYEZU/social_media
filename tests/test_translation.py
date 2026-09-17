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

    assert result == Translation(language="fr", text="[fr] Hello. Bye.")
    assert list(fake_marian) == ["Helsinki-NLP/opus-mt-en-fr"]


def test_translate_french_segments_to_english(fake_marian):
    result = Translator().translate(["Bonjour."], "fr")

    assert result == Translation(language="en", text="[en] Bonjour.")
    assert list(fake_marian) == ["Helsinki-NLP/opus-mt-fr-en"]


def test_translate_returns_none_for_unsupported_language(fake_marian):
    assert Translator().translate(["Muraho."], "rw") is None
    assert fake_marian == {}


def test_translate_batches_long_transcripts(fake_marian):
    # Each segment is longer than MAX_CHUNK_CHARS / 2, so no two can share a chunk.
    segments = [f"Sentence {i}. " + "word " * 50 for i in range(40)]

    Translator().translate(segments, "en")

    batches = fake_marian["Helsinki-NLP/opus-mt-en-fr"].batches
    assert [len(b) for b in batches] == [16, 16, 8]


def test_translate_groups_short_segments_into_sentence_chunks(fake_marian):
    # Whisper often emits list numbers as their own segments. Sent alone, Marian
    # hallucinates on them; grouped with their neighbours it translates correctly.
    segments = ["Top 7 repos.", "1.", "Open Viking.", "2.", "Agent Memory."]

    Translator().translate(segments, "en")

    batches = fake_marian["Helsinki-NLP/opus-mt-en-fr"].batches
    assert batches == [["Top 7 repos. 1. Open Viking. 2. Agent Memory."]]


def test_translate_splits_chunks_at_max_chunk_chars(fake_marian):
    segments = ["a" * 150, "b" * 150, "c" * 150, "d" * 150]

    Translator().translate(segments, "en")

    chunks = [
        c for batch in fake_marian["Helsinki-NLP/opus-mt-en-fr"].batches for c in batch
    ]
    assert chunks == ["a" * 150 + " " + "b" * 150, "c" * 150 + " " + "d" * 150]
    assert all(len(c) <= translation.MAX_CHUNK_CHARS for c in chunks)


def test_translate_passes_through_chunks_without_letters(fake_marian):
    result = Translator().translate(["1.", "2."], "en")

    assert result == Translation(language="fr", text="1. 2.")
    assert fake_marian == {}


def test_translate_keeps_pass_through_chunks_in_order(fake_marian):
    # A letter-free chunk in the middle stays in place around translated chunks.
    segments = ["a" * 300, "123", "b" * 300]

    result = Translator().translate(segments, "en")

    assert result.text == "[fr] " + "a" * 300 + " 123 [fr] " + "b" * 300


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
