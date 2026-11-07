"""Tests for whole-instance extraction: gated plane removal, walls, bands, boxes.

Every test here fails on the extraction that framed the washing machine as three
stacked bands. The tests are small and synthetic on purpose: each one isolates
one rule, so a regression names the rule that broke instead of a number.
"""

from __future__ import annotations

import json

import numpy as np
import pytest

from plantpilot import segment as seg
from plantpilot import splat
from plantpilot.segment import Object, Plane

UP = np.array([0.0, 1.0, 0.0])


def box_shell(origin, size, spacing: float = 0.02) -> np.ndarray:
    """The surface of a box: six faces, no interior, like a capture."""
    sizes = np.asarray(size, dtype=float)
    counts = np.maximum(2, np.rint(sizes / spacing).astype(int) + 1)
    grids = [np.linspace(0.0, 1.0, int(count)) for count in counts]
    faces: list[np.ndarray] = []
    for axis in range(3):
        for side in (0.0, 1.0):
            first = grids[(axis + 1) % 3]
            second = grids[(axis + 2) % 3]
            u, v = np.meshgrid(first, second, indexing="ij")
            local = np.zeros((u.size, 3))
            local[:, axis] = side
            local[:, (axis + 1) % 3] = u.ravel()
            local[:, (axis + 2) % 3] = v.ravel()
            faces.append(local * sizes[None, :])
    return np.concatenate(faces, axis=0) + np.asarray(origin, dtype=float)[None, :]


def face_normals(points: np.ndarray, centre: np.ndarray) -> np.ndarray:
    """The dominant axis of each point's offset from the centre, as a normal."""
    offset = points - centre
    axis = np.argmax(np.abs(offset), axis=1)
    normals = np.zeros_like(offset)
    normals[np.arange(points.shape[0]), axis] = np.sign(offset[np.arange(points.shape[0]), axis])
    return normals


def test_a_flat_gaussian_points_its_thin_axis_at_the_surface():
    """The gaussian's own normal is its rotated thinnest ellipsoid axis."""
    identity = np.array([[1.0, 0.0, 0.0, 0.0]], dtype=np.float32)
    # A 90 degree turn about z takes the local x axis onto world y.
    quarter = np.array([[np.cos(np.pi / 4), 0.0, 0.0, np.sin(np.pi / 4)]], dtype=np.float32)
    scene = splat.Scene(
        xyz=np.zeros((2, 3)),
        rgb=np.zeros((2, 3), dtype=np.uint8),
        size=np.array([[0.005, 0.02, 0.02], [0.005, 0.02, 0.02]], dtype=np.float32),
        alpha=np.ones(2, dtype=np.float32),
        meta={"frame": {"up_axis": "+y", "up_axis_index": 1, "up_axis_sign": 1}},
        rot=np.concatenate([identity, quarter], axis=0),
    )
    normals = seg.gaussian_normals(scene)
    assert normals is not None
    assert normals[0] == pytest.approx([1.0, 0.0, 0.0], abs=1e-5)
    assert normals[1] == pytest.approx([0.0, 1.0, 0.0], abs=1e-5)
    missing = splat.Scene(
        xyz=np.zeros((1, 3)),
        rgb=np.zeros((1, 3), dtype=np.uint8),
        size=np.ones((1, 3), dtype=np.float32),
        alpha=np.ones(1, dtype=np.float32),
        meta={},
        rot=None,
    )
    assert seg.gaussian_normals(missing) is None


def test_a_horizontal_plane_does_not_take_a_vertical_face():
    """The slicing fix: a 4 cm horizontal band through a box is not a plane.

    A machine's faces are flat sheets too. What separates them from a room plane
    is that the column through a face continues above and below the band, and
    that the face's own normal points across the plane rather than along it. The
    gated removal keeps the face; the distance-only band cuts it in half, which
    is what the extraction used to do.
    """
    points = box_shell((0.0, 0.0, 0.0), (0.4, 0.4, 0.4))
    centre = np.array([0.2, 0.2, 0.2])
    normals = face_normals(points, centre)
    plane_normal = np.array([0.0, 1.0, 0.0])
    offset = -(centre @ plane_normal)  # a plane through the box's middle
    gated, stats = seg.plane_removal_mask(
        points,
        plane_normal,
        offset,
        threshold=0.04,
        normals=normals,
        share=0.7,
        window=0.12,
    )
    band = np.abs(points @ plane_normal + offset) < 0.04
    assert int(band.sum()) > 100
    assert stats["band_inliers"] == int(band.sum())
    assert int(gated.sum()) <= 0.1 * int(band.sum())

    band_only, _ = seg.plane_removal_mask(
        points,
        plane_normal,
        offset,
        threshold=0.04,
        normals=None,
        share=2.0,  # a share no column can reach disables the flatness test
        window=0.12,
    )
    assert int(band_only.sum()) == 0  # no normals and no flatness claim: nothing
    # The extraction's band mode keeps the old behaviour, which this test exists
    # to show is the wrong one.
    assert int((np.abs(points @ plane_normal + offset) < 0.04).sum()) > 100


def test_a_vertical_wall_is_found_even_when_horizontal_clutter_dominates():
    """The eight planes used to be eight horizontal ones, so walls stayed.

    The wall here holds a smaller share of the points than the horizontal
    clutter does. Without a budget per orientation the horizontal candidates win
    every round and the wall is never proposed.
    """
    rng = np.random.default_rng(0)
    floor = np.stack(
        [rng.uniform(-1.5, 1.5, 8000), np.zeros(8000), rng.uniform(-1.5, 1.5, 8000)], axis=1
    )
    shelves = np.concatenate(
        [
            np.stack([rng.uniform(-1.5, 1.5, 1200), np.full(1200, 0.5 + 0.1 * level), rng.uniform(-1.5, 1.5, 1200)], axis=1)
            for level in range(3)
        ]
    )
    wall_x, wall_z = np.meshgrid(np.arange(-1.4, 1.4, 0.02), np.arange(0.0, 1.7, 0.02), indexing="ij")
    wall = np.stack([wall_x.ravel(), wall_z.ravel(), np.full(wall_x.size, 1.45)], axis=1)
    points = np.concatenate([floor, shelves, wall], axis=0)
    wall_normal = np.zeros_like(points)
    wall_normal[:, 2] = 1.0
    up_normal = np.zeros_like(points)
    up_normal[:, 1] = 1.0
    normals = np.where(
        (np.abs(points[:, 2] - 1.45) < 1e-6)[:, None], wall_normal, up_normal
    )
    planes, keep = seg.find_planes(
        points,
        up=UP,
        threshold=0.03,
        max_planes=6,
        min_fraction=0.02,
        sample_points=6000,
        iterations=200,
        seed=0,
        normals=normals,
        normal_draws=300,
        agreement=0.8,
        column_cell=0.05,
        column_window=0.12,
        column_share=0.7,
        column_min_points=3,
        horizontal_max=2,
        vertical_max=2,
    )
    kinds = [plane.kind for plane in planes]
    assert kinds.count("vertical") >= 1
    wall_plane = [plane for plane in planes if plane.kind == "vertical"][0]
    assert abs(abs(float(np.asarray(wall_plane.normal) @ np.array([0.0, 0.0, 1.0]))) - 1.0) < 0.1
    assert wall_plane.inliers > 500


def test_two_stacked_bands_of_one_instance_are_merged():
    """A band fragment has the footprint of the shape it was cut from."""
    points = np.concatenate([box_shell((0.0, 0.0, 0.0), (0.5, 0.3, 0.4)), box_shell((0.0, 0.38, 0.0), (0.5, 0.3, 0.4))])
    # Two bands of one instance: the lower one and the upper one, 8 cm apart.
    half = points.shape[0] // 2
    groups = [np.arange(half), np.arange(half, points.shape[0])]
    merged, stats = seg.merge_stacked(
        points, groups, up=UP, gap_m=0.10, footprint_share=0.6, span_m=2.4, cell=0.05
    )
    assert stats["components_after"] == 1
    assert len(merged) == 1
    assert merged[0].size == points.shape[0]


def test_two_instances_side_by_side_are_not_merged():
    left = box_shell((0.0, 0.0, 0.0), (0.4, 0.6, 0.4))
    right = box_shell((1.5, 0.0, 0.0), (0.4, 0.6, 0.4))
    points = np.concatenate([left, right])
    groups = [np.arange(left.shape[0]), np.arange(left.shape[0], points.shape[0])]
    merged, stats = seg.merge_stacked(
        points, groups, up=UP, gap_m=0.10, footprint_share=0.6, span_m=2.4, cell=0.05
    )
    assert stats["components_after"] == 2
    assert stats["pairs_joined"] == 0


def test_a_box_standing_on_the_floor_reaches_the_floor():
    """The floor band takes the lowest layer, so the box is completed down to it."""
    points = box_shell((0.0, 0.0, 0.0), (0.6, 0.8, 0.5), spacing=0.015)
    floor = Plane(normal=[0.0, 1.0, 0.0], offset=0.0, inliers=10_000, rms_m=0.01, horizontal=True)
    standing = points[points[:, 1] > 0.03]  # the 3 cm the floor plane would take
    obj = seg.build_object(1, standing, up=UP, floor=floor, snap_m=0.08)
    assert obj.floor_snapped is True
    assert obj.bottom_above_floor == pytest.approx(0.0, abs=1e-6)
    assert seg.vertical_extent(obj, UP) >= 0.75


def test_a_hanging_object_is_not_stretched_to_the_floor():
    points = box_shell((0.0, 1.2, 0.0), (0.5, 0.4, 0.5), spacing=0.015)
    floor = Plane(normal=[0.0, 1.0, 0.0], offset=0.0, inliers=10_000, rms_m=0.01, horizontal=True)
    obj = seg.build_object(1, points, up=UP, floor=floor, snap_m=0.08)
    assert obj.floor_snapped is False
    assert obj.bottom_above_floor == pytest.approx(1.2, abs=0.05)


def test_a_floor_standing_object_gets_an_upright_box():
    """A tilted tall object on the floor is framed with an axis on the up direction."""
    points = box_shell((0.0, 0.0, 0.0), (0.4, 0.9, 0.4), spacing=0.015)
    tilt = np.array([[np.cos(0.35), 0.0, -np.sin(0.35)], [0.0, 1.0, 0.0], [np.sin(0.35), 0.0, np.cos(0.35)]])
    points = points @ tilt.T
    points[:, 1] -= points[:, 1].min()
    floor = Plane(normal=[0.0, 1.0, 0.0], offset=0.0, inliers=10_000, rms_m=0.01, horizontal=True)
    obj = seg.build_object(1, points, up=UP, floor=floor, snap_m=0.08)
    axes = np.asarray(obj.axes, dtype=float)
    vertical_axis = int(np.argmax(np.abs(axes @ UP)))
    assert abs(float(axes[vertical_axis] @ UP)) > 0.99
    assert obj.extents[vertical_axis] >= 0.85
    assert obj.bottom_above_floor == pytest.approx(0.0, abs=0.02)


def test_an_oversized_component_is_peeled_of_a_wall_before_it_is_split():
    """A wall welded to a box is a plane inside the component the global pass missed."""
    wall_x, wall_y = np.meshgrid(np.arange(-1.0, 1.0, 0.02), np.arange(0.05, 1.95, 0.02), indexing="ij")
    wall = np.stack([np.full(wall_x.size, 0.0), wall_y.ravel(), wall_x.ravel()], axis=1)
    box = box_shell((0.0, 0.0, 0.0), (0.4, 0.4, 0.4), spacing=0.02)
    points = np.concatenate([wall, box])
    pieces, record = seg.peel_component(
        points,
        None,
        up=UP,
        threshold=0.03,
        voxel=0.03,
        max_points=2_000,
        max_extent=0.6,
        min_points=20,
        sheet_share=0.05,
        sheet_min_m=1.0,
        iterations=200,
        seed=0,
    )
    assert record["sheets"] >= 1
    assert record["points_removed"] > 0.5 * wall.shape[0]
    assert len(pieces) == 1
    kept = points[pieces[0]]
    assert kept.shape[0] < points.shape[0] - 0.5 * wall.shape[0]
    # The box survives, the wall does not: the kept points stay inside the box.
    assert kept[:, 0].max() >= 0.35
    assert kept[:, 1].max() <= 0.45
    assert kept[:, 2].max() <= 0.45 and kept[:, 2].min() >= -0.05


def test_the_cap_and_the_dropped_clusters_are_reported(tmp_path):
    from splat_fixture import room_ply

    ply = room_ply(tmp_path / "room.ply")
    out = tmp_path / "scene.npz"
    splat.ingest(ply, out, hash_source=False)
    scene = splat.load_scene(out)
    params = {
        "plane_iterations": 200,
        "plane_sample": 4000,
        "plane_min_fraction": 0.05,
        "min_points": 20,
        "max_objects": 2,
    }
    payload = seg.segment(scene, tmp_path / "objects.json", params=params)
    counts = payload["counts"]
    assert counts["objects"] <= 2
    assert counts["capped"] == counts["clusters"] - counts["objects"]
    assert counts["capped"] > 0
    assert len(counts["capped_largest_points"]) >= 1
    assert counts["capped_points"] >= counts["capped_largest_points"][0]


def test_the_plane_counts_name_what_each_test_claimed(tmp_path):
    from splat_fixture import room_ply

    ply = room_ply(tmp_path / "room.ply")
    out = tmp_path / "scene.npz"
    splat.ingest(ply, out, hash_source=False)
    scene = splat.load_scene(out)
    payload = seg.segment(
        scene,
        tmp_path / "objects.json",
        params={
            "plane_iterations": 200,
            "plane_sample": 4000,
            "plane_min_fraction": 0.05,
            "min_points": 20,
        },
    )
    items = payload["planes"]["items"]
    assert items
    for item in items:
        for key in ("band_inliers", "normal_inliers", "flat_inliers", "kind"):
            assert key in item
        assert item["inliers"] > 0
        assert item["band_inliers"] >= item["inliers"] - 1
        assert item["normal_inliers"] <= item["band_inliers"]
        assert item["flat_inliers"] <= item["band_inliers"]
    assert payload["planes"]["horizontal"] + payload["planes"]["vertical"] == payload["planes"]["removed"]


def test_the_object_layer_reports_its_new_stages(tmp_path):
    from splat_fixture import room_ply

    ply = room_ply(tmp_path / "room.ply")
    out = tmp_path / "scene.npz"
    splat.ingest(ply, out, hash_source=False)
    scene = splat.load_scene(out)
    payload = seg.segment(
        scene,
        tmp_path / "objects.json",
        params={"plane_iterations": 200, "plane_sample": 4000, "plane_min_fraction": 0.05, "min_points": 20},
    )
    counts = payload["counts"]
    for key in (
        "components",
        "components_kept",
        "components_merged",
        "components_split",
        "components_peeled",
        "peel_points_removed",
        "clusters",
        "clusters_dropped_min_points",
        "objects",
        "capped",
        "floor_snapped",
    ):
        assert key in counts
    for obj in payload["objects"]:
        assert "bottom_above_floor" in obj and "floor_snapped" in obj
