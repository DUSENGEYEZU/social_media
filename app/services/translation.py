"""English <-> French translation of transcripts with local MarianMT models."""

from dataclasses import dataclass

TARGET_LANGUAGE = {"en": "fr", "fr": "en"}
MODEL_NAMES = {
    ("en", "fr"): "Helsinki-NLP/opus-mt-en-fr",
    ("fr", "en"): "Helsinki-NLP/opus-mt-fr-en",
}
# Whisper segments are grouped into chunks before translation. Sent one by one,
# tiny segments such as a list number ("1.") make Marian hallucinate whole
# sentences; grouped into sentence-sized chunks they translate correctly and the
# translation reads better across segment boundaries. 400 characters stays far
# below the model's ~512-token input limit.
MAX_CHUNK_CHARS = 400
BATCH_SIZE = 16


class TranslationError(Exception):
    """Raised when the translation model fails."""


@dataclass(frozen=True)
class Translation:
    language: str
    text: str


_MODELS: dict[str, tuple] = {}


def _load_marian(model_name: str) -> tuple:
    """Return (tokenizer, model), loading once per name. Imports lazily: torch is heavy."""
    if model_name not in _MODELS:
        from transformers import MarianMTModel, MarianTokenizer

        tokenizer = MarianTokenizer.from_pretrained(model_name)
        model = MarianMTModel.from_pretrained(model_name)
        model.eval()
        _MODELS[model_name] = (tokenizer, model)
    return _MODELS[model_name]


def _chunk_segments(segments: list[str]) -> list[str]:
    """Join consecutive segments into chunks of at most MAX_CHUNK_CHARS."""
    chunks: list[str] = []
    current = ""
    for segment in (s.strip() for s in segments):
        if not segment:
            continue
        if current and len(current) + 1 + len(segment) > MAX_CHUNK_CHARS:
            chunks.append(current)
            current = segment
        else:
            current = f"{current} {segment}".strip()
    if current:
        chunks.append(current)
    return chunks


def _has_letters(text: str) -> bool:
    return any(char.isalpha() for char in text)


class Translator:
    """Translate English to French and French to English."""

    def target_language(self, source_language: str) -> str | None:
        return TARGET_LANGUAGE.get(source_language.lower())

    def translate(
        self, segments: list[str], source_language: str
    ) -> Translation | None:
        """Translate the segments, or return None when the language is not supported."""
        target = self.target_language(source_language)
        if target is None:
            return None
        chunks = _chunk_segments(segments)
        if not chunks:
            return Translation(language=target, text="")

        # Chunks without any letters (numbers, punctuation) are kept as they are.
        to_translate = [chunk for chunk in chunks if _has_letters(chunk)]
        translated = iter(self._translate_chunks(to_translate, source_language, target))

        pieces = [
            next(translated) if _has_letters(chunk) else chunk for chunk in chunks
        ]
        return Translation(language=target, text=" ".join(p.strip() for p in pieces))

    def _translate_chunks(
        self, chunks: list[str], source: str, target: str
    ) -> list[str]:
        if not chunks:
            return []
        model_name = MODEL_NAMES[(source.lower(), target)]
        try:
            tokenizer, model = _load_marian(model_name)
            outputs: list[str] = []
            for start in range(0, len(chunks), BATCH_SIZE):
                batch = chunks[start : start + BATCH_SIZE]
                inputs = tokenizer(
                    batch, return_tensors="pt", padding=True, truncation=True
                )
                generated = model.generate(**inputs)
                outputs.extend(
                    tokenizer.batch_decode(generated, skip_special_tokens=True)
                )
        except Exception as exc:
            raise TranslationError(f"Translation failed: {exc}") from exc
        return outputs
