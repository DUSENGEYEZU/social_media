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
| Video download | yt-dlp with ffmpeg |
| Testing | pytest |
| Linting and formatting | ruff |

## Project structure

```
social_media/
├── app/                    # Application package
│   ├── __init__.py         # create_app() application factory
│   ├── config.py           # Configuration classes (reads from environment)
│   ├── api/                # REST API blueprint, mounted at /api/v1
│   │   ├── __init__.py     # Defines the blueprint and imports route modules
│   │   ├── health.py       # GET /api/v1/health
│   │   └── videos.py       # POST /api/v1/videos/youtube
│   └── services/           # Business logic, independent of HTTP
│       └── retrieving_data.py  # DownloadVideo class (YouTube today, more platforms later)
├── tests/                  # pytest suite, runs offline (network calls are faked)
│   ├── conftest.py         # Shared fixtures: app, client, temporary download folder
│   ├── test_config.py
│   ├── test_retrieving_data.py
│   └── test_videos_api.py
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
- `app/services/` holds the logic that does the real work, with no Flask imports. Routes stay thin: they validate the request, call a service, and translate the result or error into an HTTP response. `retrieving_data.py` contains the `DownloadVideo` class. It has one method per platform, starting with `youtube(url)`.

Downloaded videos are saved outside the repository, by default in a `downloaded_youtube_videos` folder next to it:

```
social_media_project/
├── social_media/                 # this repository
└── downloaded_youtube_videos/    # created on first download
```

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

## API endpoints

All endpoints are prefixed with `/api/v1`.

| Method | Path | Description |
|---|---|---|
| GET | `/health` | Liveness check. Returns `{"status": "ok"}`. |
| POST | `/videos/youtube` | Download a YouTube video into the download folder. |

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
  "file_path": "/path/to/downloaded_youtube_videos/Me at the zoo [jNQXAC9IVRw].mp4",
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

## Configuration

| Variable | Where | Purpose |
|---|---|---|
| `FLASK_APP` | `.flaskenv` | Module containing the app factory. Set to `app`. |
| `FLASK_DEBUG` | `.flaskenv` | `1` enables auto-reload and the debugger. Set to `0` in production. |
| `SECRET_KEY` | `.env` | Signs sessions and tokens. Must be random and kept private. |
| `DOWNLOAD_DIR` | `.env` (optional) | Absolute path where videos are saved. Defaults to `../downloaded_youtube_videos` relative to the repository. |

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
