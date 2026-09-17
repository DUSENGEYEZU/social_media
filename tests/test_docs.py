import pytest


@pytest.fixture
def spec(client):
    response = client.get("/openapi.json")
    assert response.status_code == 200
    return response.get_json()


def test_swagger_ui_is_served_at_docs(client):
    response = client.get("/docs/")

    assert response.status_code == 200
    assert b"swagger" in response.data.lower()
    assert b"<title>Social Media API</title>" in response.data


def test_openapi_spec_describes_the_api(spec):
    assert spec["openapi"].startswith("3.")
    assert spec["info"]["title"] == "Social Media API"
    assert spec["info"]["version"]


def test_openapi_spec_documents_health_endpoint(spec):
    operation = spec["paths"]["/api/v1/health"]["get"]

    assert "200" in operation["responses"]


@pytest.mark.parametrize(
    "path",
    [
        "/api/v1/videos/youtube",
        "/api/v1/videos/instagram",
        "/api/v1/videos/tiktok",
        "/api/v1/videos/facebook",
    ],
)
def test_openapi_spec_documents_each_download_endpoint(spec, path):
    operation = spec["paths"][path]["post"]

    body_schema = operation["requestBody"]["content"]["application/json"]["schema"]
    assert operation["requestBody"]["required"] is True
    assert body_schema["required"] == ["url"]
    assert body_schema["properties"]["url"]["type"] == "string"

    assert set(operation["responses"]) == {"201", "400", "502"}


def test_openapi_spec_defines_video_metadata_schema(spec):
    schema = spec["components"]["schemas"]["VideoMetadata"]

    assert set(schema["properties"]) == {
        "title",
        "video_id",
        "file_path",
        "duration_seconds",
        "file_size_bytes",
        "transcript_language",
        "transcript_text",
        "translation_language",
        "translation_text",
        "topic",
        "warnings",
    }
    assert schema["properties"]["warnings"]["type"] == "array"
