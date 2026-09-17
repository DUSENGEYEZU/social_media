import pytest

from app.services import summarization
from app.services.summarization import SummarizationError, Summarizer


class FakeTokenizer:
    def __call__(self, texts, **kwargs):
        return {"texts": list(texts)}

    def batch_decode(self, outputs, skip_special_tokens=True):
        return list(outputs)


class FakeModel:
    def __init__(self):
        self.calls: list[list[str]] = []
        self.generate_kwargs: dict = {}

    def generate(self, texts, **kwargs):
        self.calls.append(texts)
        self.generate_kwargs = kwargs
        return [f"SUMMARY<{' '.join(t.split()[:3])}>" for t in texts]


@pytest.fixture
def fake_bart(monkeypatch):
    model = FakeModel()
    loaded = []

    def _load(model_name):
        loaded.append(model_name)
        return FakeTokenizer(), model

    monkeypatch.setattr(summarization, "_load_bart", _load)
    model.loaded = loaded
    return model


def test_summarize_empty_text_returns_empty_string(fake_bart):
    assert Summarizer().summarize("   ") == ""
    assert fake_bart.calls == []


def test_summarize_returns_very_short_text_unchanged(fake_bart):
    # A handful of words cannot be summarised further; the model would only pad
    # them out with invented content.
    text = "Run AI agents offline and free."

    assert Summarizer().summarize(text) == text
    assert fake_bart.calls == []


def test_summarize_medium_text_in_one_pass(fake_bart):
    text = " ".join(f"word{i}" for i in range(200))

    result = Summarizer().summarize(text)

    assert result == "SUMMARY<word0 word1 word2>"
    assert len(fake_bart.calls) == 1
    assert fake_bart.calls[0] == [text]
    assert fake_bart.loaded == [summarization.MODEL_NAME]
    # BART CNN checkpoints expect the decoder to start from BOS (transformers warns otherwise).
    assert fake_bart.generate_kwargs["forced_bos_token_id"] == 0


def test_summarize_long_text_chunks_then_reduces(fake_bart):
    words = [f"w{i}" for i in range(1500)]
    text = " ".join(words)

    result = Summarizer().summarize(text)

    first_pass, reduce_pass = fake_bart.calls
    # 1500 words in chunks of CHUNK_WORDS, every chunk within the limit.
    assert len(first_pass) == 3
    assert all(len(chunk.split()) <= summarization.CHUNK_WORDS for chunk in first_pass)
    assert first_pass[0].split()[0] == "w0"
    assert first_pass[-1].split()[-1] == "w1499"
    # The partial summaries are joined and summarised once more.
    assert reduce_pass == [
        "SUMMARY<w0 w1 w2> SUMMARY<w600 w601 w602> SUMMARY<w1200 w1201 w1202>"
    ]
    assert result == "SUMMARY<SUMMARY<w0 w1 w2>>"


def test_summarize_wraps_model_errors(monkeypatch):
    def _explode(model_name):
        raise RuntimeError("no weights")

    monkeypatch.setattr(summarization, "_load_bart", _explode)

    with pytest.raises(SummarizationError, match="no weights"):
        Summarizer().summarize(" ".join(["word"] * 100))


def test_summarize_removes_spaces_before_punctuation(monkeypatch):
    # distilbart-cnn emits "word . Next word ," style spacing.
    class SpacedModel(FakeModel):
        def generate(self, texts, **kwargs):
            return ["Magnitude is free . You never pay , ever . Really ?"]

    monkeypatch.setattr(
        summarization, "_load_bart", lambda name: (FakeTokenizer(), SpacedModel())
    )

    result = Summarizer().summarize(" ".join(["word"] * 100))

    assert result == "Magnitude is free. You never pay, ever. Really?"
