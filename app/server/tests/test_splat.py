"""Tests for the splat ingest: schema, sanity filter, artifacts and metadata."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from plantpilot import splat
from splat_fixture import header, room, room_ply, rows_for, write_ply


def test_the_header_is_read_and_the_schema_is_named(tmp_path):
    path = room_ply(tmp_path / "room.ply")
    parsed = splat.read_header(path)
    assert parsed.format == "binary_little_endian 1.0"
    assert parsed.declared_vertices == room().shape[0] + 6
    assert set(splat.CORE_PROPERTIES).issubset(parsed.properties)
    assert parsed.stride == 4 * len(parsed.properties)


def test_the_sane_prefix_stops_at_the_first_uninitialised_row(tmp_path):
    points = room()
    path = room_ply(tmp_path / "room.ply", garbage_rows=9)
    core, counts = splat.load_sane_prefix(path)
    assert core.shape[0] == points.shape[0]
    assert counts["declared_vertices"] == points.shape[0] + 9
    assert counts["kept_vertices"] == points.shape[0]
    assert counts["first_invalid_row"] == points.shape[0]
    assert counts["dropped_vertices"] == 9
    assert np.isfinite(core).all()


def test_a_schema_without_opacity_fails_by_name(tmp_path):
    path = tmp_path / "missing.ply"
    properties = tuple(name for name in splat.CORE_PROPERTIES if name != "opacity")
    rows = np.zeros((3, len(properties)), dtype=np.float32)
    with path.open("wb") as f:
        f.write(header(3, properties))
        f.write(rows.tobytes())
    with pytest.raises(splat.SplatError, match="opacity"):
        splat.read_header(path)


def test_an_ascii_ply_fails_loudly(tmp_path):
    path = tmp_path / "ascii.ply"
    text = "\n".join([
        "ply",
        "format ascii 1.0",
        "element vertex 1",
        *[f"property float {name}" for name in splat.CORE_PROPERTIES],
        "end_header",
        "0 0 0 0 0 0 1 0 0 0 0 0 0 0",
        "",
    ])
    # Write as binary with Unix line endings so the header scanner finds
    # "end_header\n" on all platforms; text mode uses \r\n on Windows.
    path.write_bytes(text.encode("ascii"))
    with pytest.raises(splat.SplatError, match="binary_little_endian"):
        splat.read_header(path)


def test_a_truncated_file_is_refused(tmp_path):
    path = tmp_path / "short.ply"
    path.write_bytes(header(100) + rows_for(np.zeros((3, 3))).tobytes())
    with pytest.raises(splat.SplatError, match="truncated"):
        splat.read_header(path)


def test_the_up_axis_is_detected_from_the_floor_plane():
    points = room()
    axis, sign, detail = splat.detect_up_axis(points)
    assert splat.AXES[axis] == "y"
    assert sign == 1
    assert detail["confident"] is True
    assert detail["per_axis"]["y"]["slab"] == pytest.approx(0.0, abs=0.05)


def test_the_up_axis_can_be_declared(tmp_path):
    path = tmp_path / "scene.npz"
    meta = splat.ingest(room_ply(tmp_path / "room.ply"), path, up="-z", hash_source=False)
    assert meta["frame"]["up_axis"] == "-z"
    assert meta["frame"]["up_axis_source"].startswith("declared")


def test_ingest_writes_one_scene_artifact_with_its_counts(tmp_path):
    ply = room_ply(tmp_path / "room.ply")
    out = tmp_path / "scene.npz"
    meta = splat.ingest(ply, out, hash_source=False)
    assert out.exists()
    assert meta["counts"]["declared"] == meta["counts"]["sane"] + meta["counts"]["dropped"]
    assert meta["counts"]["sane"] == room().shape[0]
    assert meta["counts"]["rendered"] == meta["counts"]["sane"]
    assert meta["frame"]["up_axis"] == "+y"

    scene = splat.load_scene(out)
    assert scene.xyz.shape[0] == meta["counts"]["rendered"]
    assert scene.rgb.dtype == np.uint8
    assert np.isfinite(scene.xyz).all()
    assert 0.0 <= float(scene.alpha.min()) and float(scene.alpha.max()) <= 1.0
    assert scene.meta["artifact"] == "scene"
    assert scene.meta["version"] == splat.SCENE_VERSION
    # a splat renderer needs the orientation, not only the per-axis size
    assert scene.rot is not None and scene.rot.shape == (scene.xyz.shape[0], 4)
    assert np.abs(np.linalg.norm(scene.rot, axis=1) - 1.0).max() < 1e-5


def test_the_render_budget_decimates_deterministically(tmp_path):
    ply = room_ply(tmp_path / "room.ply")
    first = splat.ingest(ply, tmp_path / "a.npz", budget=200, hash_source=False)
    second = splat.ingest(ply, tmp_path / "b.npz", budget=200, hash_source=False)
    assert first["counts"]["rendered"] == 200
    a = np.load(tmp_path / "a.npz")["xyz"]
    b = np.load(tmp_path / "b.npz")["xyz"]
    assert np.array_equal(a, b)


def test_gaussian_derivation_follows_the_format_conventions():
    core = np.zeros((2, 15), dtype=np.float32)
    core[:, 6] = 1.0  # unit quaternion, w first
    core[0, 3:6] = np.log(0.01)
    core[0, 10:13] = 1.0
    core[0, 13] = 0.0
    core[1, 3:6] = np.log(0.02)
    core[1, 10:13] = -100.0
    core[1, 13] = 100.0
    derived = splat.derive_gaussians(core)
    assert derived["size"][0] == pytest.approx(0.01, rel=1e-5)
    assert derived["alpha"][0] == pytest.approx(0.5)
    assert derived["alpha"][1] == pytest.approx(1.0)
    assert derived["rgb"][0, 0] == int(round((0.5 + splat.SH_DC) * 255))
    assert derived["rgb"][1, 0] == 0
    assert np.allclose(np.linalg.norm(derived["rot"], axis=1), 1.0)


def test_a_scene_with_disagreeing_arrays_is_refused(tmp_path):
    bad = tmp_path / "bad.npz"
    np.savez(bad, xyz=np.zeros((3, 3)), rgb=np.zeros((2, 3), dtype=np.uint8),
             size=np.zeros((3, 3)), alpha=np.zeros(3), meta=np.array("{}"))
    with pytest.raises(splat.SplatError, match="shape"):
        splat.load_scene(bad)


def test_a_version_one_scene_without_rotation_still_loads(tmp_path):
    old = tmp_path / "old.npz"
    np.savez(old, xyz=np.zeros((3, 3)), rgb=np.zeros((3, 3), dtype=np.uint8),
             size=np.zeros((3, 3)), alpha=np.zeros(3), meta=np.array("{}"))
    scene = splat.load_scene(old)
    assert scene.rot is None


def test_a_scene_missing_an_array_is_refused(tmp_path):
    bad = tmp_path / "bad.npz"
    np.savez(bad, xyz=np.zeros((3, 3)), rgb=np.zeros((3, 3), dtype=np.uint8),
             size=np.zeros((3, 3)), meta=np.array("{}"))
    with pytest.raises(splat.SplatError, match="missing"):
        splat.load_scene(bad)


def test_the_report_prints_the_three_counts(tmp_path):
    meta = splat.ingest(room_ply(tmp_path / "room.ply"), tmp_path / "scene.npz", hash_source=False)
    report = splat.format_report(meta)
    assert "declared vertices" in report
    assert "sane prefix" in report
    assert "rendered" in report
    assert "up axis" in report
    assert "502" not in report  # no supplied-capture number leaks into a synthetic run
    payload = json.loads(json.dumps(meta))
    assert payload["frame"]["up_axis"] == "+y"


def test_the_hero_camera_stands_above_the_detected_floor(tmp_path):
    # the fixture floor is at y = 0 and the up axis is +y
    out = tmp_path / "scene.npz"
    splat.ingest(room_ply(tmp_path / "room.ply"), out, hash_source=False)
    scene = splat.load_scene(out)
    pose = splat.hero_camera_pose(scene)
    assert splat.floor_height(scene) == pytest.approx(0.0, abs=0.05)
    assert pose["eye"][1] == pytest.approx(1.45, abs=0.1)
    assert len(pose["forward"]) == 3
    assert len(pose["up"]) == 3
