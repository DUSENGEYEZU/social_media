"""OpenAPI documentation served with Swagger UI.

Each route documents itself with a YAML block in its docstring, after a
``---`` line. flasgger collects those blocks into one OpenAPI 3 spec.

- Swagger UI:   /docs/
- Raw spec:     /openapi.json
"""

from flasgger import Swagger
from flask import Flask

API_VERSION = "0.1.0"

SWAGGER_CONFIG = {
    "headers": [],
    "openapi": "3.0.3",
    "specs": [
        {
            "endpoint": "openapi",
            "route": "/openapi.json",
            "rule_filter": lambda rule: True,
            "model_filter": lambda tag: True,
        }
    ],
    "static_url_path": "/flasgger_static",
    "swagger_ui": True,
    "specs_route": "/docs/",
    "title": "Social Media API",
}

SWAGGER_TEMPLATE = {
    "info": {
        "title": "Social Media API",
        "description": (
            "RESTful API for a social media application. "
            "All endpoints live under `/api/v1`."
        ),
        "version": API_VERSION,
    },
    "tags": [
        {"name": "Health", "description": "Service status"},
        {
            "name": "Videos",
            "description": "Download videos from social media platforms",
        },
    ],
    "components": {
        "schemas": {
            "VideoMetadata": {
                "type": "object",
                "properties": {
                    "title": {"type": "string", "example": "Me at the zoo"},
                    "video_id": {"type": "string", "example": "jNQXAC9IVRw"},
                    "file_path": {
                        "type": "string",
                        "example": "/downloads/Me at the zoo [jNQXAC9IVRw].mp4",
                    },
                    "duration_seconds": {
                        "type": "integer",
                        "nullable": True,
                        "example": 19,
                    },
                    "file_size_bytes": {
                        "type": "integer",
                        "nullable": True,
                        "example": 533915,
                    },
                    "transcript_language": {
                        "type": "string",
                        "nullable": True,
                        "example": "en",
                        "description": "ISO 639-1 code of the spoken language detected by Whisper.",
                    },
                    "transcript_text": {
                        "type": "string",
                        "nullable": True,
                        "example": "Magnitude is a free, open-source project that ...",
                    },
                    "translation_language": {
                        "type": "string",
                        "nullable": True,
                        "example": "fr",
                        "description": "fr for English speech, en for French speech, null otherwise.",
                    },
                    "translation_text": {
                        "type": "string",
                        "nullable": True,
                        "example": "Magnitude est un projet gratuit et open source qui ...",
                    },
                    "topic": {
                        "type": "string",
                        "nullable": True,
                        "example": "The video presents Magnitude, a free open-source tool ...",
                        "description": (
                            "Short English summary of what the video is about, built from "
                            "the English transcript or translation. Null when neither exists."
                        ),
                    },
                    "warnings": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Non-fatal problems, for example transcription failed or the "
                            "language is not English or French. Empty when everything worked."
                        ),
                    },
                },
            },
            "Error": {
                "type": "object",
                "properties": {
                    "error": {"type": "string", "example": "Not a YouTube URL"},
                },
            },
        }
    },
}


def init_docs(app: Flask) -> Swagger:
    """Attach Swagger UI and the OpenAPI spec routes to the app."""
    return Swagger(app, config=SWAGGER_CONFIG, template=SWAGGER_TEMPLATE)
