"""Tests for the derived information channel bake.

These pin the conventions the viewer depends on: the normal read from a
rotation and its sizes, the smoothing and shading terms, the inferno height
ramp, the depth-discontinuity contour selection and its two families, the
adjacency-checked anchor palette, the pastel overlay, and the smallest-box
assignment.
"""

from __future__ import annotations

import colorsys
import importlib.util
from pathlib import Path

import numpy as np

from plantpilot import splat, splat_render

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


def _box(identifier, extents, klass="valve", label=None, confidence=0.5):
    return {
        "id": identifier,
        "centre": [0.0, 0.0, 0.0],
        "axes": [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        "extents": list(extents),
        "class": klass,
        "label": label or klass,
        "confidence": confidence,
        "points": 10,
    }


def test_normal_of_a_known_rotation_and_size():
    identity = _scene([[0.0, 0.0, 0.0]], size=[[0.10, 0.05, 0.02]], rot=[[1.0, 0.0, 0.0, 0.0]])
    assert np.allclose(filter_assets.gaussian_normals(identity)[0], [0.0, 0.0, 1.0])
    # 0.5 + 0.5 n, so a +z normal is half red, half green, full blue.
    assert filter_assets.normal_colours(identity)[0].tolist() == [128, 128, 255]

    # A quarter turn about +y maps the local +z axis to world +x.
    rotation = np.sqrt(0.5)
    turned = _scene([[0.0, 0.0, 0.0]], size=[[0.10, 0.05, 0.02]], rot=[[rotation, 0.0, rotation, 0.0]])
    assert np.allclose(filter_assets.gaussian_normals(turned)[0], [1.0, 0.0, 0.0], atol=1e-6)
    assert filter_assets.normal_colours(turned)[0].tolist() == [255, 128, 128]


def test_normals_fall_back_to_the_up_axis_without_rotation():
    scene = _scene([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0]], up_axis=1, up_sign=-1)
    assert np.allclose(filter_assets.gaussian_normals(scene), np.tile([0.0, -1.0, 0.0], (2, 1)))
    assert filter_assets.normal_colours(scene).tolist() == [[128, 0, 128], [128, 0, 128]]


def test_voxel_smoothing_makes_neighbouring_normals_agree():
    rotation = np.sqrt(0.5)
    scene = _scene(
        [[0.0, 0.0, 0.0], [0.01, 0.0, 0.0]],
        rot=[[1.0, 0.0, 0.0, 0.0], [rotation, 0.0, rotation, 0.0]],
    )
    raw = filter_assets.gaussian_normals(scene)
    smoothed = filter_assets.smoothed_normals(scene)
    assert np.allclose(np.linalg.norm(smoothed, axis=1), 1.0)
    assert float(smoothed[0] @ smoothed[1]) > float(raw[0] @ raw[1]) + 0.4


def test_height_uses_inferno_with_a_neutral_floor_band():
    # Up axis +y, so scene height is world y; the floor is the 1st percentile.
    heights = np.array([-1.0, -1.0, -1.0, 0.0, 1.0])
    scene = _scene(np.stack([np.zeros(5), heights, np.zeros(5)], axis=1))
    colours = filter_assets.height_colours(scene).astype(int)
    neutral = colours[0]
    assert int(neutral.max() - neutral.min()) <= 3
    assert int(colours[4][0]) > int(colours[4][2]) + 30


def test_depth_rasteriser_keeps_the_nearest_gaussian():
    camera = splat_render.Camera.look_at((0, 0, 0), (0, 0, 1), (0, 1, 0), 64, 48)
    depth, owner = filter_assets.rasterise_centres(np.array([[0, 0, 2.0], [0, 0, 1.0]]), camera)
    assert np.isclose(depth[24, 32], 1.0)
    assert int(owner[24, 32]) == 1


def test_depth_edges_find_a_step_and_stay_sparse():
    depth = np.full((48, 64), 3.0)
    depth[:, :32] = 1.0
    edges = filter_assets.depth_edges(depth)
    assert edges.any()
    assert bool(edges[:, 28:36].any())
    assert int(edges.sum()) < 0.3 * edges.size


def _contour_fixture():
    xyz = np.zeros((1000, 3))
    xyz[:, 0] = np.arange(1000) * 0.1
    depth_votes = np.zeros(1000, dtype=np.int64)
    depth_votes[[0, 1, 2]] = (5, 3, 1)
    boundary_votes = np.zeros(1000, dtype=np.int64)
    boundary_votes[10] = 2
    labels = np.full(1000, -1, dtype=np.int32)
    labels[0] = 0
    labels[10] = 0
    entries = [{"colour": [235, 72, 60], "pastel": [234, 136, 129]}]
    scene = _scene(xyz)
    return scene, depth_votes, boundary_votes, labels, entries


def test_contour_selection_keeps_families_and_colours():
    scene, depth_votes, boundary_votes, labels, entries = _contour_fixture()
    saved = (filter_assets.CONTOUR_TOP_FRACTION, filter_assets.CONTOUR_INSTANCE_MAX)
    filter_assets.CONTOUR_TOP_FRACTION, filter_assets.CONTOUR_INSTANCE_MAX = 1.0, 100_000
    try:
        points, scores, colours, stats = filter_assets.contour_payload(
            scene, depth_votes, boundary_votes, labels, entries,
        )
    finally:
        filter_assets.CONTOUR_TOP_FRACTION, filter_assets.CONTOUR_INSTANCE_MAX = saved
    assert stats["depth_edges"] == 2
    assert stats["instance_boundaries"] == 1
    assert stats["count"] == points.shape[0] == colours.shape[0] == 3
    assert stats["depth_votes_histogram"][5] > 0
    assert colours[0].tolist() == [235, 72, 60]      # index 0, anchor owned
    assert colours[1].tolist() == [170, 200, 210]    # index 1, unowned cyan-grey
    assert colours[2].tolist() == [235, 72, 60]      # index 10, anchor owned
    assert np.allclose(scores, [1.0, 0.6, 1.0])


def test_instance_boundary_owners_take_anchor_sides_only():
    owner = np.array([[0, 1, 2]])
    labels = np.array([0, 1, -1])
    chosen = filter_assets.instance_boundary_owners(owner, labels)
    assert sorted(chosen.tolist()) == [0, 1, 1]


def test_semantics_prefers_the_smaller_containing_anchor():
    large = _box("AN-large", [2.0, 2.0, 2.0], klass="machine")
    small = _box("AN-small", [1.0, 1.0, 1.0], klass="valve")
    labels, entries, shading = filter_assets.semantic_assignment(np.zeros((1, 3)), [large, small], "anchor")
    assert entries[int(labels[0])]["id"] == "AN-small"
    assert 0.85 <= float(shading[0]) <= 1.10
    assert [entry["id"] for entry in entries] == ["AN-small"]


def test_palette_is_deterministic_high_separation_and_hue_matched():
    first = filter_assets.select_anchor_palette(7)
    again = filter_assets.select_anchor_palette(7)
    assert [list(colour) for colour in first] == [list(colour) for colour in again]
    for index, colour in enumerate(first):
        for other in first[index + 1:]:
            assert filter_assets.colours_are_distinct(colour, other)
        pastel = filter_assets.pastel_colour(colour)
        base_hue = colorsys.rgb_to_hsv(*(np.asarray(colour) / 255.0))[0]
        pastel_hue = colorsys.rgb_to_hsv(*(pastel / 255.0))[0]
        assert abs(base_hue - pastel_hue) < 0.01
        assert colorsys.rgb_to_hsv(*(pastel / 255.0))[1] < 0.6


def test_semantics_dims_only_the_room_and_keeps_geometry():
    scene = _scene([[0.0, 0.0, 0.0], [5.0, 5.0, 5.0]], rgb=[[200, 100, 50], [10, 20, 30]])
    anchor = _box("AN-1", [1.0, 1.0, 1.0], klass="motor")
    labels, entries, shading = filter_assets.semantic_assignment(scene.xyz, [anchor], "anchor")
    geometry = filter_assets.geometry_rows(scene)
    rows = filter_assets.colour_rows(geometry, filter_assets.semantic_colours(labels, entries, shading),
                                     opacity_scale=filter_assets.semantic_opacity_scale(labels))
    alpha = 1.0 / (1.0 + np.exp(-rows[:, 13].astype(np.float64)))
    assert np.isclose(alpha[0], scene.alpha[0], atol=1e-5)
    assert np.isclose(alpha[1], scene.alpha[1] * filter_assets.SEMANTICS_ROOM_OPACITY_SCALE, atol=1e-5)
    assert np.array_equal(rows[:, :10], geometry[:, :10])


def test_pastel_overlay_rows_are_the_anchor_subset_with_dimmed_opacity():
    scene = _scene([[0.0, 0.0, 0.0], [5.0, 5.0, 5.0]], rgb=[[200, 100, 50], [10, 20, 30]])
    anchor = _box("AN-1", [1.0, 1.0, 1.0], klass="motor")
    labels, entries, _ = filter_assets.semantic_assignment(scene.xyz, [anchor], "anchor")
    colours, mask, pastels = filter_assets.anchors_overlay_colours(scene, labels, entries)
    geometry = filter_assets.geometry_rows(scene)
    rows = filter_assets.anchors_overlay_rows(geometry, scene, labels, entries, colours, mask)
    assert rows.shape == (1, 14) and int(mask.sum()) == 1
    assert np.array_equal(rows[:, :10], geometry[[0]][:, :10])
    expected = (0.55 * pastels[0] + 0.45 * np.array([200.0, 100.0, 50.0])) / 255.0
    decoded = 0.5 + filter_assets.SH_DC * rows[0, 10:13].astype(np.float64)
    assert np.allclose(decoded, expected, atol=1e-4)
    alpha = 1.0 / (1.0 + np.exp(-rows[0, 13]))
    assert np.isclose(alpha, 0.5 * filter_assets.OVERLAY_OPACITY_SCALE, atol=1e-5)


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
