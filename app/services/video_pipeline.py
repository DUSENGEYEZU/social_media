"""Download a video, transcribe it, translate the transcript, summarise the topic.

A download that succeeded is never discarded because a later step failed:
those steps degrade to null fields plus an entry in ``warnings``.
"""

from app.services.summarization import SummarizationError
from app.services.transcription import TranscriptionError
from app.services.translation import TranslationError

TEXT_FIELDS = (
    "transcript_language",
    "transcript_text",
    "translation_language",
    "translation_text",
    "topic",
)


def process_video(
    url: str,
    platform_method: str,
    downloader,
    transcriber,
    translator,
    summarizer,
    *,
    transcription_enabled: bool = True,
) -> dict:
    """Run the full pipeline for one URL and return the API response body.

    ``platform_method`` names the DownloadVideo method to call ("youtube",
    "instagram", "tiktok"). Download errors propagate unchanged so the route
    can map them to 400/502; later failures become warnings.
    """
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

    translation = None
    try:
        translation = translator.translate(transcript.segments, transcript.language)
    except TranslationError as exc:
        warnings.append(f"Translation failed: {exc}")
    else:
        if translation is None:
            warnings.append(
                f"No translation: detected language {transcript.language!r} "
                "is not English or French."
            )
        else:
            result["translation_language"] = translation.language
            result["translation_text"] = translation.text

    # The summariser is English-only. English speech: use the transcript.
    # French speech: use its English translation. Anything else: no summary.
    if transcript.language == "en":
        english_text = transcript.text
    elif translation is not None and translation.language == "en":
        english_text = translation.text
    else:
        english_text = None

    if english_text is None:
        warnings.append(
            f"No summary: no English text available for language {transcript.language!r}."
        )
        return result
    try:
        result["topic"] = summarizer.summarize(english_text)
    except SummarizationError as exc:
        warnings.append(f"Summary failed: {exc}")
    return result
