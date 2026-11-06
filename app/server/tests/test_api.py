import json
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


def test_diagnosis_endpoint_reports_the_local_artifact():
    body = client.get("/api/diagnosis").json()
    if body["available"]:
        assert body["artifact"] == "diagnosis"
        assert body["target"]["tag"] == "P-005"
        assert body["citations"]
    else:
        assert "make diagnose" in body["reason"]


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


def test_the_room_endpoints_explain_a_missing_artifact(monkeypatch, tmp_path):
    from plantpilot import main

    monkeypatch.setattr(main, "OBJECTS_FILE", tmp_path / "objects.json")
    monkeypatch.setattr(main, "SPLAT_ASSET", tmp_path / "room.ply")
    objects = client.get("/api/scene/objects")
    splat = client.get("/api/splat")
    assert objects.status_code == 404 and "make objects" in objects.json()["detail"]
    assert splat.status_code == 404 and "make splat-asset" in splat.json()["detail"]


def test_the_room_endpoints_serve_the_artifacts(monkeypatch, tmp_path):
    from plantpilot import main

    payload = {"artifact": "objects", "version": 1, "source": {"points": 3, "up_axis": "+y"},
               "objects": [], "counts": {"objects": 0}}
    objects_path = tmp_path / "objects.json"
    objects_path.write_text(json.dumps(payload))
    splat_path = tmp_path / "room.ply"
    splat_path.write_bytes(b"ply\nformat binary_little_endian 1.0\nend_header\n")
    monkeypatch.setattr(main, "OBJECTS_FILE", objects_path)
    monkeypatch.setattr(main, "SPLAT_ASSET", splat_path)

    body = client.get("/api/scene/objects").json()
    assert body["artifact"] == "objects" and body["source"]["up_axis"] == "+y"

    response = client.get("/api/splat")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/octet-stream"
    assert response.content.startswith(b"ply\n")


def test_the_filters_endpoint_explains_a_missing_artifact(monkeypatch, tmp_path):
    from plantpilot import main

    monkeypatch.setattr(main, "FILTER_DIR", tmp_path / "filters")
    assert client.get("/api/scene/filters").status_code == 404
    assert "make filter-assets" in client.get("/api/scene/filters").json()["detail"]
    assert client.get("/api/filter/height").status_code == 404


def test_the_filters_endpoint_serves_metadata_and_assets(monkeypatch, tmp_path):
    from plantpilot import main

    directory = tmp_path / "filters"
    directory.mkdir()
    (directory / "filters.json").write_text(json.dumps({"artifact": "filters", "filters": ["height"]}))
    (directory / "height.ply").write_bytes(f"ply\nformat binary_little_endian 1.0\nend_header\n".encode())
    monkeypatch.setattr(main, "FILTER_DIR", directory)
    body = client.get("/api/scene/filters").json()
    assert body["artifact"] == "filters"
    response = client.get("/api/filter/height")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/octet-stream"
    assert client.get("/api/filter/nope").status_code == 404


def test_the_anchors_endpoint_explains_a_missing_artifact(monkeypatch, tmp_path):
    from plantpilot import main

    monkeypatch.setattr(main, "ANCHORS_FILE", tmp_path / "anchors.json")
    response = client.get("/api/scene/anchors")
    assert response.status_code == 404 and "make anchors" in response.json()["detail"]


def test_the_anchors_endpoint_serves_the_artifact(monkeypatch, tmp_path):
    from plantpilot import main

    payload = {
        "artifact": "anchors",
        "version": 1,
        "counts": {"anchors": 1},
        "anchors": [{"id": "AN-0001", "label": "equipment", "reviewed": True}],
    }
    path = tmp_path / "anchors.json"
    path.write_text(json.dumps(payload))
    monkeypatch.setattr(main, "ANCHORS_FILE", path)
    body = client.get("/api/scene/anchors").json()
    assert body["artifact"] == "anchors"
    assert body["anchors"][0]["reviewed"] is True


def test_the_assets_endpoint_explains_a_missing_artifact(monkeypatch, tmp_path):
    from plantpilot import main

    monkeypatch.setattr(main, "ASSETS_FILE", tmp_path / "assets.json")
    response = client.get("/api/scene/assets")
    assert response.status_code == 404 and "make assets" in response.json()["detail"]


def test_the_assets_endpoint_serves_the_artifact(monkeypatch, tmp_path):
    from plantpilot import main

    payload = {
        "artifact": "assets",
        "version": 1,
        "counts": {"assets": 1, "verified": 1},
        "assets": [{"id": "AS-0001", "class": "pump", "confidence": 0.8, "verified": True}],
    }
    path = tmp_path / "assets.json"
    path.write_text(json.dumps(payload))
    monkeypatch.setattr(main, "ASSETS_FILE", path)
    body = client.get("/api/scene/assets").json()
    assert body["artifact"] == "assets"
    assert body["assets"][0]["id"] == "AS-0001"


def test_the_route_endpoint_explains_a_missing_artifact(monkeypatch, tmp_path):
    from plantpilot import main

    monkeypatch.setattr(main, "ROUTE_ARTIFACT", tmp_path / "route.json")
    response = client.get("/api/scene/route")
    assert response.status_code == 404 and "make route" in response.json()["detail"]


def test_the_route_endpoint_serves_the_route(monkeypatch, tmp_path):
    from plantpilot import main

    path = tmp_path / "route.json"
    path.write_text(json.dumps({"reachable": True, "path": [[0, 0, 0], [1, 0, 1]], "distance_m": 1.41}))
    monkeypatch.setattr(main, "ROUTE_ARTIFACT", path)
    body = client.get("/api/scene/route").json()
    assert body["reachable"] is True and len(body["path"]) == 2
