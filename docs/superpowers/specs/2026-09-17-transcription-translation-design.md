---
noteId: "67cc67d0b26b11f18d914dfa2d9ccc1b"
tags: []

---

# Transcription and translation of downloaded videos

Date: 2026-09-17. Status: approved by Longin, implementation in progress.

## Goal

Every video downloaded through the API (YouTube, Instagram, TikTok) is transcribed,
and the transcript is translated between English and French. Both texts are returned
in the same response as the existing video metadata. Everything runs locally with
Python packages; no external API keys.

## Engines

| Step | Package | Model | Notes |
|---|---|---|---|
| Speech to text | `faster-whisper` | `small` by default (`WHISPER_MODEL`) | Reads mp4 directly, detects language, returns timed segments |
| Translation | `transformers` + `torch` + `sentencepiece` + `sacremoses` | `Helsinki-NLP/opus-mt-en-fr`, `Helsinki-NLP/opus-mt-fr-en` | MarianMT, CPU inference |

Models download once into the Hugging Face cache (`~/.cache/huggingface`) and are
loaded lazily on first use, then kept in memory for the life of the process.

## Response shape

Existing fields are unchanged. New fields on every successful download:

```json
{
  "transcript_language": "en",
  "transcript_text": "...",
  "translation_language": "fr",
  "translation_text": "...",
  "warnings": []
}
```

## Language rule

- `en` -> translate to `fr`
- `fr` -> translate to `en`
- anything else -> `translation_language` and `translation_text` are `null`, plus a
  warning naming the detected language.

## Long inputs and short segments

Marian models accept roughly 512 tokens. Whisper segments are joined into chunks of
at most 400 characters (`MAX_CHUNK_CHARS`) before translation, then translated in
batches of 16 and joined with spaces. Chunking matters for quality as well as size:
sent alone, tiny segments such as a list number ("1.") make Marian hallucinate whole
sentences (observed on the Instagram test reel). Chunks that contain no letters are
passed through untranslated. The transcript text is the segments joined with spaces.

## Components

- `app/services/transcription.py`: `Transcriber(model_size)` with
  `transcribe(path) -> Transcript(language, segments, text)`. Raises
  `TranscriptionError`. Module-level cache of loaded `WhisperModel` per size.
- `app/services/translation.py`: `Translator` with
  `translate(segments, source_language) -> Translation(language, text) | None`.
  Returns `None` for unsupported languages. Raises `TranslationError` on model
  failure. Module-level cache of loaded Marian models per direction.
- `app/services/video_pipeline.py`: `process_video(downloader, platform_method, url,
  transcriber, translator, transcription_enabled) -> dict`. Runs download, then
  transcription, then translation; assembles the response; never discards a
  successful download because a later step failed.
- `app/api/videos.py`: shared handler calls `process_video` instead of the
  downloader directly. Routes unchanged.
- `app/config.py`: `WHISPER_MODEL` (default `small`), `TRANSCRIPTION_ENABLED`
  (default `true`; accepts `true/false/1/0/yes/no`).
- `app/docs.py`: `VideoMetadata` schema gains the new fields.

## Failure handling

| Failure | HTTP | Response |
|---|---|---|
| Download fails | 502 | `{"error": ...}` as today |
| Transcription fails | 201 | metadata; transcript and translation fields `null`; warning |
| Translation fails | 201 | metadata and transcript; translation fields `null`; warning |
| Unsupported language | 201 | metadata and transcript; translation fields `null`; warning |
| `TRANSCRIPTION_ENABLED=false` | 201 | metadata; transcript and translation fields `null`; warning "transcription disabled" |

## Testing

- Unit tests fake `WhisperModel` and the Marian model/tokenizer. No model downloads
  in the test suite.
- Cover: language routing (en, fr, other), segment batching and joining, each
  failure row above, config parsing, response shape, Swagger schema fields.
- Existing 72 tests must keep passing.
- Manual end-to-end: run the pipeline against the English TikTok video already in
  `downloaded_videos/` and inspect the French translation.

## Out of scope

Background jobs, Whisper's translate-to-English for other languages, subtitle
files, speaker labels, GPU acceleration.

## Addendum (2026-09-17): topic summary

Approved as a follow-up the same day. A sixth field, `topic`, holds a short English
summary of what the video is about.

- Engine: `sshleifer/distilbart-cnn-12-6` via `transformers` (`AutoModelForSeq2SeqLM`),
  CPU, loaded once. About 1.2 GB.
- Component: `app/services/summarization.py`, `Summarizer.summarize(text) -> str`,
  raises `SummarizationError`. Text with 30 words or fewer is returned unchanged.
  Longer text is split into 600-word chunks, each summarised, and the partial
  summaries summarised once more (map-reduce).
- Input: the English transcript for English speech, the English translation for
  French speech. Other languages: `topic` is null plus a warning
  "No summary: no English text available for language '<xx>'."
- Failure: `topic` null plus warning "Summary failed: ...". Download, transcript and
  translation are kept.
- Pipeline signature gains a `summarizer` argument after `translator`.
