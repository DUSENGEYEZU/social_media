---
noteId: "2f94e4f0b1da11f1bae73d2008d27e5e"
tags: []

---

# Social Media API

A RESTful API for a social media application, built with Python and Flask. Dependencies and the virtual environment are managed with [uv](https://docs.astral.sh/uv/).

## Tech stack

| Layer | Choice |
|---|---|
| Language | Python 3.13 |
| Web framework | Flask 3 |
| API style | REST, JSON, versioned under `/api/v1` |
| Package manager | uv |
| Video download | yt-dlp with ffmpeg, plus curl-cffi for browser impersonation |
| API documentation | OpenAPI 3 with Swagger UI, via flasgger |
| Speech to text | faster-whisper (local Whisper model, CPU) |
| Translation | Hugging Face transformers with Helsinki-NLP MarianMT models (local, CPU) |
| Topic summary | distilbart-cnn-12-6 summarization model (local, CPU) |
| Testing | pytest |
| Linting and formatting | ruff |

## Project structure

```
social_media/
├── app/                    # Application package
│   ├── __init__.py         # create_app() application factory
│   ├── config.py           # Configuration classes (reads from environment)
│   ├── docs.py             # Swagger UI and OpenAPI spec setup
│   ├── api/                # REST API blueprint, mounted at /api/v1
│   │   ├── __init__.py     # Defines the blueprint and imports route modules
│   │   ├── health.py       # GET /api/v1/health
│   │   └── videos.py       # POST /api/v1/videos/{youtube,instagram,tiktok}
│   └── services/           # Business logic, independent of HTTP
│       ├── retrieving_data.py  # DownloadVideo class: youtube(), instagram(), tiktok()
│       ├── transcription.py    # Transcriber: speech to text with faster-whisper
│       ├── translation.py      # Translator: English <-> French with MarianMT
│       ├── summarization.py    # Summarizer: short English topic summary with BART
│       └── video_pipeline.py   # process_video(): download -> transcribe -> translate -> summarise
├── tests/                  # pytest suite, runs offline (network calls are faked)
│   ├── conftest.py         # Shared fixtures: app, client, temporary download folder
│   ├── test_config.py
│   ├── test_docs.py
│   ├── test_retrieving_data.py
│   ├── test_summarization.py
│   ├── test_transcription.py
│   ├── test_translation.py
│   ├── test_video_pipeline.py
│   └── test_videos_api.py
├── downloaded_videos/      # Saved videos (created on first download, ignored by git)
├── .env                    # Secrets (local only, never committed)
├── .env.example            # Template for .env
├── .flaskenv               # Public Flask settings (FLASK_APP, FLASK_DEBUG)
├── .python-version         # Python version used by uv
├── pyproject.toml          # Project metadata and dependencies
├── uv.lock                 # Locked dependency versions
└── README.md
```

How the pieces fit together:

- `app/__init__.py` exposes `create_app()`. Flask calls this factory when the server starts. It loads configuration and registers the API blueprint.
- `app/config.py` holds the `Config` class. Values come from environment variables so the same code runs in development and production.
- `app/api/__init__.py` creates the `api_bp` blueprint. Every route module is imported here so its routes are attached to the blueprint.
- Each file in `app/api/` groups the routes for one resource. Add a new module there and import it in `app/api/__init__.py` to expose a new set of endpoints.
- `app/docs.py` configures flasgger. Each route documents itself with a YAML block in its docstring, after a `---` line. flasgger collects those blocks into one OpenAPI 3 spec and serves Swagger UI on top of it.
- `app/services/` holds the logic that does the real work, with no Flask imports. Routes stay thin: they validate the request, call a service, and translate the result or error into an HTTP response. `retrieving_data.py` contains the `DownloadVideo` class with one method per platform: `youtube(url)`, `instagram(url)` and `tiktok(url)`. Each validates the URL for its platform and hands off to one shared yt-dlp download, so adding a platform means adding a URL check and a two-line method.

Downloaded videos are saved in the `downloaded_videos` folder at the root of the repository. It is created on the first download and listed in `.gitignore`, so videos are never committed or pushed.

## Prerequisites

- **uv** installed. On macOS or Linux:

  ```bash
  curl -LsSf https://astral.sh/uv/install.sh | sh
  ```

  Or with Homebrew:

  ```bash
  brew install uv
  ```

- **Python 3.13** is not required in advance. If it is missing, uv downloads it automatically when you run the project.

- **ffmpeg** for merging video and audio streams into a single mp4. YouTube serves high quality video and audio separately.

  ```bash
  brew install ffmpeg
  ```

  Check with `ffmpeg -version`. Without it, downloads still work but fall back to lower quality formats that ship video and audio together.

## Installation

1. Clone the repository and enter the folder:

   ```bash
   git clone <repository-url>
   cd social_media
   ```

2. Install all dependencies. This creates the `.venv` folder and installs exactly the versions in `uv.lock`:

   ```bash
   uv sync
   ```

3. Create your local `.env` from the template:

   ```bash
   cp .env.example .env
   ```

4. Replace the placeholder secret key with a random one:

   ```bash
   echo "SECRET_KEY=$(uv run python -c 'import secrets; print(secrets.token_hex(32))')" > .env
   ```

## Running the server

Start the development server:

```bash
uv run flask run
```

Flask reads `.flaskenv` to find the app and enable debug mode, and reads `.env` for secrets. The server listens on `http://127.0.0.1:5000`.

On macOS, port 5000 is often taken by AirPlay Receiver. If you see `Address already in use`, pick another port:

```bash
uv run flask run --port 5001
```

Stop the server with `Ctrl+C`.

## Verifying it works

With the server running, call the health endpoint from another terminal:

```bash
curl http://127.0.0.1:5000/api/v1/health
```

Expected response:

```json
{"status": "ok"}
```

## Interactive API docs (Swagger)

With the server running, open the Swagger UI in your browser:

```
http://127.0.0.1:5000/docs/
```

Every endpoint is listed with its request body, response codes and example values. Click **Try it out** on an endpoint, fill in the fields, and press **Execute** to call the API directly from the page.

The raw OpenAPI 3 spec is at `http://127.0.0.1:5000/openapi.json`. You can import it into Postman, Insomnia, or a code generator.

To document a new endpoint, add a YAML block to its docstring after a `---` line. See `app/api/videos.py` for a complete example with a request body, response schemas and error codes. Shared schemas such as `VideoMetadata` and `Error` live in `app/docs.py` and are referenced with `$ref`.

## API endpoints

All endpoints are prefixed with `/api/v1`.

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Liveness check. Returns `{"status": "ok"}`. |
| POST | `/videos/youtube` | Download a YouTube video into the download folder. |
| POST | `/videos/instagram` | Download a public Instagram post, reel or IGTV video. |
| POST | `/videos/tiktok` | Download a TikTok video, including app short links. |

### POST /videos/youtube

Downloads the video at the given URL as an mp4 and saves it in the download folder. The request blocks until the download finishes, so long videos mean long requests.

Request body:

```json
{"url": "https://www.youtube.com/watch?v=jNQXAC9IVRw"}
```

Example:

```bash
curl -X POST http://127.0.0.1:5000/api/v1/videos/youtube \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.youtube.com/watch?v=jNQXAC9IVRw"}'
```

Success response, `201 Created`:

```json
{
  "title": "Me at the zoo",
  "video_id": "jNQXAC9IVRw",
  "file_path": "/path/to/social_media/downloaded_videos/Me at the zoo [jNQXAC9IVRw].mp4",
  "duration_seconds": 19,
  "file_size_bytes": 533915
}
```

Error responses, always `{"error": "<message>"}`:

| Status | When |
|---|---|
| 400 | Body is not JSON, `url` is missing, or the URL is not a YouTube link. |
| 502 | YouTube or yt-dlp failed, for example a private or removed video. |

Playlists are not downloaded. A playlist URL downloads only the single video it points at.

### POST /videos/instagram

Same request body, responses and error codes as the YouTube endpoint. Accepts public posts, reels and IGTV videos:

```
https://www.instagram.com/reel/<id>/
https://www.instagram.com/p/<id>/
https://www.instagram.com/tv/<id>/
```

Profile pages and stories are rejected with 400 because they are not single videos. Private accounts and login-only content return 502, since the API downloads without an Instagram login.

### POST /videos/tiktok

Same request body, responses and error codes as the YouTube endpoint. Accepts full video URLs and the short links the TikTok app produces when you tap Share:

```
https://www.tiktok.com/@<user>/video/<id>
https://vm.tiktok.com/<code>/
https://vt.tiktok.com/<code>/
```

Profile and hashtag pages are rejected with 400.

TikTok serves a bot-check page to plain HTTP clients. yt-dlp gets past it by impersonating a real browser, which needs its optional `curl-cffi` dependency. That dependency is declared in `pyproject.toml` as `yt-dlp[curl-cffi]`, so `uv sync` installs it and no extra step is needed. If TikTok downloads ever fail with "Unexpected response from webpage request", run `uv run yt-dlp --list-impersonate-targets` and confirm at least one target is listed.

### File names

Files are named `<title> [<id>].mp4`. The title is cut at 80 characters because Instagram and TikTok use the post caption as the title, and captions can run to hundreds of characters. The id keeps every file unique.

## Transcription and translation

Every download endpoint also transcribes the speech in the video, translates the transcript, and writes a short summary of what the video is about. All three run locally on the CPU with open models, no API keys and no data leaving your machine.

- **Speech to text** uses faster-whisper. It detects the spoken language and returns the words as text.
- **Translation** uses the Helsinki-NLP MarianMT models. English speech is translated to French, French speech to English. Any other language gets a transcript but no translation.
- **Topic summary** uses the distilbart-cnn-12-6 model. It is English-only, so it summarises the English transcript for English speech and the English translation for French speech. The topic is always in English.

The response gains six fields:

```json
{
  "title": "...",
  "video_id": "...",
  "file_path": "...",
  "duration_seconds": 31,
  "file_size_bytes": 2114716,
  "transcript_language": "en",
  "transcript_text": "Magnitude is a free, open-source project that ...",
  "translation_language": "fr",
  "translation_text": "Magnitude est un projet gratuit et open source qui ...",
  "topic": "Magnitude is a free open source project that lets you run AI coding agents offline ...",
  "warnings": []
}
```

| Field | Meaning |
|---|---|
| `transcript_language` | ISO 639-1 code of the detected spoken language, for example `en` or `fr`. |
| `transcript_text` | The transcript in that language. |
| `translation_language` | `fr` for English speech, `en` for French speech, `null` otherwise. |
| `translation_text` | The translated transcript, or `null`. |
| `topic` | Two or three English sentences saying what the video is about, or `null` when no English text exists. Very short transcripts are returned as they are. |
| `warnings` | Non-fatal problems. Empty when everything worked. |

A successful download is never turned into an error by these steps. If transcription, translation or summarisation fails, or the language is not English or French, the response is still `201` with the video metadata, the affected fields set to `null`, and the reason listed in `warnings`.

### First run and timing

The first request after installation downloads the models once, about 2.3 GB in total, into the Hugging Face cache at `~/.cache/huggingface`. Nothing is stored in the repository. Later requests reuse the cached models, and a loaded model stays in memory for the life of the server process.

Transcription is the slow step. On an Apple Silicon CPU with the default `small` model expect roughly 15 to 40 seconds for each minute of speech, plus a few seconds for translation and the summary. Requests block until everything is done, so a long video means a long request.

### Settings

| Variable | Default | Effect |
|---|---|---|
| `WHISPER_MODEL` | `small` | Whisper model size: `tiny`, `base`, `small`, `medium`, `large-v3`. Bigger is more accurate and slower. |
| `TRANSCRIPTION_ENABLED` | `true` | Set to `false` to skip transcription, translation and the summary and get fast, download-only responses. |

Set them in `.env`. Both are optional.

## Configuration

| Variable | Where | Purpose |
|---|---|---|
| `FLASK_APP` | `.flaskenv` | Module containing the app factory. Set to `app`. |
| `FLASK_DEBUG` | `.flaskenv` | `1` enables auto-reload and the debugger. Set to `0` in production. |
| `SECRET_KEY` | `.env` | Signs sessions and tokens. Must be random and kept private. |
| `DOWNLOAD_DIR` | `.env` (optional) | Absolute path where videos are saved. Defaults to the `downloaded_videos` folder inside the repository. |
| `WHISPER_MODEL` | `.env` (optional) | faster-whisper model size. Defaults to `small`. |
| `TRANSCRIPTION_ENABLED` | `.env` (optional) | `false` skips transcription and translation. Defaults to `true`. |

`.env` is listed in `.gitignore` and must never be committed. Share new variables by adding a placeholder to `.env.example`.

## Development

Add a runtime dependency:

```bash
uv add <package>
```

Add a development-only dependency:

```bash
uv add --dev <package>
```

Run the tests:

```bash
uv run pytest
```

Lint and format the code:

```bash
uv run ruff check .
uv run ruff format .
```

Run any command inside the project environment without activating it by prefixing it with `uv run`. If you prefer an activated shell:

```bash
source .venv/bin/activate
```

## Editor setup

In VS Code, open the Command Palette, choose **Python: Select Interpreter**, and pick `.venv/bin/python` inside the project. This makes imports resolve and enables debugging.
