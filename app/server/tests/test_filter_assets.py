"""Tests for the derived information channel bake.

The bake is scratch tooling, so these tests pin the conventions that the viewer
depends on: how a gaussian normal is read from a rotation and its sizes, that a
palette is deterministic, that flat surfaces score zero on the edge channel, and
that a gaussian is owned by the smallest covering box.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np

from plantpilot import splat

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "make_filter_assets.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("make_filter_assets", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


filter_assets = _load_script()


def _scene(xyz, size=None, rot=None, rgb=None, up_axis=1, up_sign=1) -> splat.Scene:
    xyz = np.asarray(xyz, dtype=np.float64)
    count = xyz.shape[0]
    size = np.full((count, 3), 0.05) if size is None else np.asarray(size, dtype=np.float64)
    rgb = np.full((count, 3), 128, dtype=np.uint8) if rgb is None else np.asarray(rgb, dtype=np.uint8)
    meta = {
        "frame": {"up_axis_index": up_axis, "up_axis_sign": up_sign},
        "source": {"file": "test.ply"},
    }
    return splat.Scene(
        xyz=xyz,
        rgb=rgb,
        size=size,
        alpha=np.full(count, 0.5, dtype=np.float32),
        meta=meta,
        rot=None if rot is None else np.asarray(rot, dtype=np.float32),
    )


def _box(identifier, extents, klass="valve", label=None, confidence=0.5, source_extra=None):
    record = {
        "id": identifier,
        "centre": [0.0, 0.0, 0.0],
        "axes": [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        "extents": list(extents),
        "class": klass,
        "label": label or klass,
        "confidence": confidence,
    }
    if source_extra:
        record.update(source_extra)
    return record


def test_normal_of_a_known_rotation_and_size():
    identity = _scene([[0.0, 0.0, 0.0]], size=[[0.10, 0.05, 0.02]], rot=[[1.0, 0.0, 0.0, 0.0]])
    normal = filter_assets.gaussian_normals(identity)[0]
    assert np.allclose(normal, [0.0, 0.0, 1.0])
    # 0.5 + 0.5 n, so a +z normal is half red, half green, full blue.
    assert filter_assets.normal_colours(identity)[0].tolist() == [128, 128, 255]

    # A quarter turn about +y maps the local +z axis to world +x.
    rotation = np.sqrt(0.5)
    turned = _scene([[0.0, 0.0, 0.0]], size=[[0.10, 0.05, 0.02]], rot=[[rotation, 0.0, rotation, 0.0]])
    assert np.allclose(filter_assets.gaussian_normals(turned)[0], [1.0, 0.0, 0.0], atol=1e-6)
    assert filter_assets.normal_colours(turned)[0].tolist() == [255, 128, 128]


def test_normals_fall_back_to_the_up_axis_without_rotation():
    scene = _scene([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]], up_axis=1, up_sign=-1)
    normals = filter_assets.gaussian_normals(scene)
    assert np.allclose(normals, np.tile([0.0, -1.0, 0.0], (2, 1)))
    assert filter_assets.normal_colours(scene).tolist() == [[128, 0, 128], [128, 0, 128]]


def test_palette_determinism():
    assert filter_assets.id_colour("AS-1eb05582") == filter_assets.id_colour("AS-1eb05582")
    assert filter_assets.id_colour("AS-1eb05582") != filter_assets.id_colour("OBJ-001")
    for identifier in ("AS-small", "AS-large", "OBJ-113"):
        colour = filter_assets.id_colour(identifier)
        assert len(colour) == 3
        assert all(0 <= channel <= 255 for channel in colour)

    endpoints = filter_assets.ramp(np.array([0.0, 1.0]), filter_assets.HEIGHT_PALETTE)
    assert endpoints[0].tolist() == [255, 150, 64]
    assert endpoints[1].tolist() == [90, 140, 230]

    scene = _scene(np.array([[0.0, -1.0, 0.0], [0.0, 0.0, 0.0], [0.0, 1.0, 0.0]]))
    colours = filter_assets.height_colours(scene)
    assert colours.shape == (3, 3) and colours.dtype == np.uint8


def test_edge_score_is_zero_when_normals_agree_in_a_voxel():
    xyz = np.array([
        [0.010, 0.010, 0.010],
        [0.020, 0.020, 0.020],
        [0.030, 0.010, 0.020],
    ])
    normals = np.tile([0.0, 0.0, 1.0], (3, 1))
    scores = filter_assets.edge_scores(xyz, normals, voxel=0.08)
    assert np.allclose(scores, 0.0, atol=1e-12)
    assert filter_assets.edge_colours(scores).max() <= 12

    # One flipped normal splits the voxel mean, so the disagreeing gaussian
    # glows and the two that still agree stay dark.
    crease = np.array([[0.0, 0.0, 1.0], [0.0, 0.0, -1.0]])
    crease_scores = filter_assets.edge_scores(np.array([[0.0, 0.0, 0.0], [0.02, 0.0, 0.0]]), crease)
    assert np.allclose(crease_scores, 1.0, atol=1e-12)


def test_semantics_prefers_the_smaller_containing_box():
    large = _box("AS-large", [2.0, 2.0, 2.0], klass="machine")
    small = _box("AS-small", [1.0, 1.0, 1.0], klass="valve")
    labels, entries = filter_assets.semantic_assignment(np.zeros((1, 3)), [large, small], [])
    assert labels.tolist() == [0]
    assert entries[int(labels[0])]["id"] == "AS-small"
    assert [entry["id"] for entry in entries] == ["AS-small"]

    outside, outside_entries = filter_assets.semantic_assignment(
        np.array([[9.0, 9.0, 9.0]]), [large, small], []
    )
    assert outside.tolist() == [-1]
    assert outside_entries == []


def test_assets_win_an_overlap_with_raw_object_boxes():
    asset = _box("AS-1eb05582", [2.0, 2.0, 2.0], klass="machine", label="motor")
    raw = _box("OBJ-001", [0.5, 0.5, 0.5], klass="valve")
    labels, entries = filter_assets.semantic_assignment(np.zeros((1, 3)), [asset], [raw])
    assert entries[int(labels[0])]["source"] == "asset"
    assert entries[int(labels[0])]["id"] == "AS-1eb05582"


def test_the_ply_keeps_the_scene_geometry_and_opacity():
    scene = _scene(
        np.array([[0.0, 0.0, 0.0], [1.0, 2.0, 3.0], [0.5, 0.5, 0.5]]),
        size=[[0.01, 0.02, 0.03], [0.04, 0.05, 0.06], [0.07, 0.08, 0.09]],
        rot=np.tile([1.0, 0.0, 0.0, 0.0], (3, 1)),
    )
    geometry = filter_assets.geometry_rows(scene)
    rows_height = filter_assets.colour_rows(geometry, filter_assets.height_colours(scene))
    rows_normals = filter_assets.colour_rows(geometry, filter_assets.normal_colours(scene))
    assert rows_height.shape == (3, len(splat.CORE_PROPERTIES))
    assert np.array_equal(rows_height[:, :10], rows_normals[:, :10])
    assert np.array_equal(rows_height[:, 13], rows_normals[:, 13])
    assert not np.array_equal(rows_height[:, 10:13], rows_normals[:, 10:13])

    # The viewer applies exp(scale) and sigmoid(opacity), so the round trip has
    # to give back the scene's own silhouettes.
    assert np.allclose(np.exp(rows_height[:, 3:6]), scene.size, atol=1e-6)
    assert np.allclose(1.0 / (1.0 + np.exp(-rows_height[:, 13])), scene.alpha, atol=1e-5)


def test_the_ply_is_readable_and_deterministic(tmp_path):
    scene = _scene(np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]]))
    rows = filter_assets.colour_rows(filter_assets.geometry_rows(scene), filter_assets.height_colours(scene))
    first = filter_assets.write_ply(rows, tmp_path / "height.ply", "filter variant height for test")
    again = filter_assets.write_ply(rows, tmp_path / "height_again.ply", "filter variant height for test")
    assert first["bytes"] == again["bytes"]
    assert (tmp_path / "height.ply").read_bytes() == (tmp_path / "height_again.ply").read_bytes()

    header = splat.read_header(tmp_path / "height.ply")
    assert header.declared_vertices == 2
    assert set(splat.CORE_PROPERTIES).issubset(header.properties)

