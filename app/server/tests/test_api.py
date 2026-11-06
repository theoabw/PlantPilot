import shutil

import pytest
from fastapi.testclient import TestClient

from plantpilot.main import app
from test_ocr import plate_png

client = TestClient(app)


def test_health_reports_counts():
    body = client.get("/api/health").json()
    assert body["ok"] is True
    assert body["assets"] == 48
    assert body["version"] == "0.1.0"


def test_asset_endpoint_includes_neighbours():
    body = client.get("/api/assets/K-102").json()
    assert body["asset"]["tag"] == "K-102"
    assert body["neighbours"]
    assert any(n["overdue"] for n in body["neighbours"])


def test_unknown_asset_is_null_not_an_error():
    body = client.get("/api/assets/ZZ-999").json()
    assert body["asset"] is None and body["neighbours"] == []


@pytest.mark.skipif(not shutil.which("tesseract"), reason="tesseract not installed")
def test_scan_returns_the_whole_card_chain():
    files = {"frame": ("plate.png", plate_png(2), "image/png")}
    body = client.post("/api/scan", files=files, data={"symptom": "cavitation damage"}).json()
    assert body["gate"]["ok"] is True
    assert body["asset"]["tag"] == "K-102"
    assert body["action"]["part"] == "Limit switches"
    assert body["action"]["interval"] == "1 year"
