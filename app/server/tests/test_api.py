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


def test_plant_endpoint_lists_assets_and_a_start():
    body = client.get("/api/plant").json()
    assert len(body["assets"]) == 10
    assert body["start"] == [2.0, 0.8]
    assert any(a["id"] == "P-204" for a in body["assets"])


def test_route_to_an_asset_by_id():
    body = client.post("/api/route", json={"to": "V-203"}).json()
    assert body["reachable"] is True
    assert body["distance_m"] > 5
    assert body["path"]


def test_route_with_the_west_aisle_closed_is_longer():
    # T-501 is a large tank whose shortest path runs via the west aisle.
    # Blocking the west aisle forces a long detour via the east aisle (>12 m longer).
    plain = client.post("/api/route", json={"to": "T-501"}).json()
    blocked = client.post("/api/route", json={"to": "T-501", "blockers": [[0.0, 4.8, 4.6, 7.2]]}).json()
    assert blocked["reachable"] is True
    assert blocked["distance_m"] > plain["distance_m"] + 4


def test_unknown_asset_is_a_reason_not_a_crash():
    body = client.post("/api/route", json={"to": "ZZ-999"}).json()
    assert body["reachable"] is False and "unknown asset" in body["reason"]


def test_explain_returns_the_work_order_and_a_reason():
    body = client.post("/api/explain", json={"asset_id": "P-204"}).json()
    assert body["asset"]["id"] == "P-204"
    assert body["request"]["symptom"] == "cavitation damage"
    assert body["request"]["interval"] == "1 year"
    assert body["action"]["part"] == "Limit switches"
    assert "sections" in body


def test_explain_unknown_asset_is_a_reason_not_a_crash():
    body = client.post("/api/explain", json={"asset_id": "ZZ-999"}).json()
    assert body["asset"] is None and "unknown asset" in body["reason"]
