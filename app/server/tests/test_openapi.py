"""The published OpenAPI contract: typed, and the same one the app serves."""

import json
from pathlib import Path

from plantpilot.main import app

ROOT = Path(__file__).resolve().parents[3]
SPEC = ROOT / "docs" / "openapi.json"


def _schema() -> dict:
    return app.openapi()


def test_committed_spec_matches_the_app():
    assert SPEC.exists(), "docs/openapi.json is missing, run make openapi"
    committed = json.loads(SPEC.read_text(encoding="utf-8"))
    assert committed == _schema(), "docs/openapi.json is stale, run make openapi"


def test_every_operation_documents_its_response():
    untyped = []
    for path, operations in _schema()["paths"].items():
        for method, operation in operations.items():
            content = operation["responses"]["200"].get("content", {})
            typed = any(
                media_type == "application/octet-stream"
                or body.get("schema", {}).get("$ref")
                or body.get("schema", {}).get("properties")
                for media_type, body in content.items()
            )
            if not typed:
                untyped.append(f"{method.upper()} {path}")
    assert untyped == [], f"operations without a response schema: {untyped}"


def test_scan_response_names_the_whole_card_chain():
    schema = _schema()["components"]["schemas"]["ScanResponse"]
    assert {"gate", "plate", "asset", "sections", "action"} <= set(schema["required"])


def test_post_bodies_are_documented():
    schema = _schema()
    for path in ("/api/route", "/api/explain"):
        body = schema["paths"][path]["post"]["requestBody"]["content"]["application/json"]
        name = body["schema"]["$ref"].rsplit("/", 1)[-1]
        assert schema["components"]["schemas"][name]["properties"], f"{path} has an empty body"
