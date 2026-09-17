"""Short English summary of a transcript ("what is this video about") with a local BART model."""

import re

# Distilled BART fine-tuned on CNN/DailyMail: two to three sentence summaries, ~1.2 GB.
MODEL_NAME = "sshleifer/distilbart-cnn-12-6"
# The model reads at most 1024 tokens. 600 words is comfortably inside that.
CHUNK_WORDS = 600
# Below this length there is nothing to condense; summarising would only invent detail.
MIN_WORDS_TO_SUMMARIZE = 30
MAX_SUMMARY_TOKENS = 90
MIN_SUMMARY_TOKENS = 20
# The CNN/DailyMail checkpoints emit a space before punctuation: "word . Next".
_SPACE_BEFORE_PUNCT = re.compile(r"\s+([.,;:!?])")


class SummarizationError(Exception):
    """Raised when the summarization model fails."""


_MODELS: dict[str, tuple] = {}


def _load_bart(model_name: str) -> tuple:
    """Return (tokenizer, model), loading once per name. Imports lazily: torch is heavy."""
    if model_name not in _MODELS:
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

        tokenizer = AutoTokenizer.from_pretrained(model_name)
        model = AutoModelForSeq2SeqLM.from_pretrained(model_name)
        model.eval()
        _MODELS[model_name] = (tokenizer, model)
    return _MODELS[model_name]


def _chunk_words(text: str, chunk_words: int) -> list[str]:
    words = text.split()
    return [
        " ".join(words[i : i + chunk_words]) for i in range(0, len(words), chunk_words)
    ]


class Summarizer:
    """Produce a short English summary of English text."""

    def summarize(self, text: str) -> str:
        words = text.split()
        if not words:
            return ""
        if len(words) <= MIN_WORDS_TO_SUMMARIZE:
            return " ".join(words)

        summaries = self._summarize_chunks(_chunk_words(text, CHUNK_WORDS))
        if len(summaries) > 1:
            # Map-reduce: summarise the partial summaries into one.
            summaries = self._summarize_chunks([" ".join(s.strip() for s in summaries)])
        return _SPACE_BEFORE_PUNCT.sub(r"\1", summaries[0]).strip()

    def _summarize_chunks(self, chunks: list[str]) -> list[str]:
        try:
            tokenizer, model = _load_bart(MODEL_NAME)
            inputs = tokenizer(
                chunks,
                return_tensors="pt",
                padding=True,
                truncation=True,
                max_length=1024,
            )
            generated = model.generate(
                **inputs,
                max_new_tokens=MAX_SUMMARY_TOKENS,
                min_new_tokens=MIN_SUMMARY_TOKENS,
                num_beams=4,
                no_repeat_ngram_size=3,
                early_stopping=True,
                forced_bos_token_id=0,
            )
            return tokenizer.batch_decode(generated, skip_special_tokens=True)
        except Exception as exc:
            raise SummarizationError(f"Summarization failed: {exc}") from exc
