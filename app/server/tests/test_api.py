import json

import pytest
from fastapi.testclient import TestClient

from plantpilot.main import app

client = TestClient(app)


def test_diagnosis_endpoint_reports_the_local_artifact():
    body = client.get("/api/diagnosis").json()
    if body["available"]:
        assert body["artifact"] == "diagnosis"
        assert body["target"]["tag"] == "P-005"
        assert body["citations"]
    else:
        assert "make diagnose" in body["reason"]


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


def test_the_reroute_endpoint_requires_the_pipeline(monkeypatch, tmp_path):
    from plantpilot import main

    monkeypatch.setattr(main, "SCENE_DIR", tmp_path)
    monkeypatch.setattr(main, "OBJECTS_FILE", tmp_path / "missing.json")
    monkeypatch.setattr(main, "MAPPED_FILE", tmp_path / "missing.json")
    response = client.post("/api/scene/reroute", json={"blockers": [], "start": None})
    assert response.status_code == 404
    assert "make pipeline" in response.json()["detail"]


def test_the_reroute_endpoint_passes_blockers_start_and_robot_radius(monkeypatch, tmp_path):
    from plantpilot import main

    (tmp_path / "scene.npz").write_bytes(b"stub")
    objects = tmp_path / "objects.json"
    objects.write_text("{}")
    mapping = tmp_path / "mapped.json"
    mapping.write_text("{}")
    monkeypatch.setattr(main, "SCENE_DIR", tmp_path)
    monkeypatch.setattr(main, "OBJECTS_FILE", objects)
    monkeypatch.setattr(main, "MAPPED_FILE", mapping)
    captured: dict = {}

    def fake_build_route(**kwargs):
        captured.update(kwargs)
        return {"reachable": True, "path": [], "distance_m": 2.0}

    monkeypatch.setattr(main.nav, "build_route", fake_build_route)
    body = client.post(
        "/api/scene/reroute",
        json={"blockers": [[0.0, 0.0, 1.0, 1.0]], "start": [0.5, 0.5]},
    ).json()
    assert body["reachable"] is True
    assert captured["blockers"] == [[0.0, 0.0, 1.0, 1.0]]
    assert captured["start_override"] == (0.5, 0.5)
    assert captured["agent_radius_m"] == 0.2
    assert captured["output_path"] is None


def test_the_object_splats_endpoint_explains_a_missing_artifact(monkeypatch, tmp_path):
    from plantpilot import main

    monkeypatch.setattr(main, "OBJECT_SPLAT_DIR", tmp_path / "splats")
    assert client.get("/api/scene/object-splats").status_code == 404
    assert "make object-splats" in client.get("/api/scene/object-splats").json()["detail"]
    assert client.get("/api/object-splat/AN-5dbcb330").status_code == 404


def test_the_object_splats_endpoint_serves_a_manifest_and_a_ply(monkeypatch, tmp_path):
    from plantpilot import main

    directory = tmp_path / "splats"
    directory.mkdir()
    (directory / "manifest.json").write_text(json.dumps({"artifact": "object_splats", "objects": []}))
    (directory / "AN-5dbcb330.ply").write_bytes(f"ply\nformat binary_little_endian 1.0\nend_header\n".encode())
    monkeypatch.setattr(main, "OBJECT_SPLAT_DIR", directory)
    assert client.get("/api/scene/object-splats").json()["artifact"] == "object_splats"
    response = client.get("/api/object-splat/AN-5dbcb330")
    assert response.status_code == 200
    assert response.content.startswith(b"ply")
    assert client.get("/api/object-splat/zzz").status_code == 404


def test_the_meshes_endpoint_explains_a_missing_artifact(monkeypatch, tmp_path):
    from plantpilot import main

    monkeypatch.setattr(main, "MESH_DIR", tmp_path / "meshes")
    assert client.get("/api/scene/meshes").status_code == 404
    assert "make object-meshes" in client.get("/api/scene/meshes").json()["detail"]
    assert client.get("/api/mesh/AN-5dbcb330").status_code == 404


def test_the_meshes_endpoint_serves_the_manifest_and_a_mesh(monkeypatch, tmp_path):
    from plantpilot import main

    directory = tmp_path / "meshes"
    directory.mkdir()
    (directory / "manifest.json").write_text(json.dumps({"artifact": "object_meshes", "objects": []}))
    (directory / "AN-5dbcb330.ply").write_bytes(f"ply\nformat binary_little_endian 1.0\nend_header\n".encode())
    monkeypatch.setattr(main, "MESH_DIR", directory)
    body = client.get("/api/scene/meshes").json()
    assert body["artifact"] == "object_meshes"
    response = client.get("/api/mesh/AN-5dbcb330")
    assert response.status_code == 200
    assert response.content.startswith(b"ply")
    assert client.get("/api/mesh/not-an-id").status_code == 404


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
    (directory / "filters.json").write_text(json.dumps({"artifact": "filters", "filters": {"applied": ["height", "edges"]}}))
    (directory / "height.ply").write_bytes(f"ply\nformat binary_little_endian 1.0\nend_header\n".encode())
    (directory / "edges_base.ply").write_bytes(f"ply\nformat binary_little_endian 1.0\nend_header\n".encode())
    (directory / "contours.json").write_text(json.dumps({"artifact": "contours", "count": 1, "points": [[0, 0, 0]]}))
    monkeypatch.setattr(main, "FILTER_DIR", directory)
    body = client.get("/api/scene/filters").json()
    assert body["artifact"] == "filters"
    response = client.get("/api/filter/height")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/octet-stream"
    assert client.get("/api/filter/edges_base").status_code == 200
    contours = client.get("/api/filter/contours").json()
    assert contours["artifact"] == "contours" and contours["count"] == 1
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


def test_warming_builds_the_layers_of_every_robot_height(tmp_path, monkeypatch):
    from plantpilot import main as server

    for name in ("scene.npz", "objects.json", "mapped.json"):
        (tmp_path / name).write_text("")
    monkeypatch.setattr(server, "SCENE_DIR", tmp_path)
    monkeypatch.setattr(server, "OBJECTS_FILE", tmp_path / "objects.json")
    monkeypatch.setattr(server, "MAPPED_FILE", tmp_path / "mapped.json")
    heights: list[float] = []
    monkeypatch.setattr(
        server.nav, "build_route", lambda **kwargs: heights.append(kwargs["agent_height_m"])
    )

    server.warm_route_layers()

    assert sorted(heights) == [0.55, 0.9, 0.95, 1.35]


def test_warming_does_nothing_before_the_pipeline_has_run(tmp_path, monkeypatch):
    from plantpilot import main as server

    monkeypatch.setattr(server, "SCENE_DIR", tmp_path)
    monkeypatch.setattr(server, "OBJECTS_FILE", tmp_path / "objects.json")
    monkeypatch.setattr(server, "MAPPED_FILE", tmp_path / "mapped.json")
    monkeypatch.setattr(
        server.nav, "build_route", lambda **kwargs: pytest.fail("built without artifacts")
    )

    server.warm_route_layers()
