"""Tests for the extraction stage: planes, components, boxes, classes."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

from plantpilot import segment as seg
from plantpilot import splat
from plantpilot.segment import Object, Plane, classify, scale_check, vertical_extent
from splat_fixture import room, room_ply

UP = np.array([0.0, 1.0, 0.0])

FAST = {
    "plane_iterations": 200,
    "plane_sample": 4000,
    # The fixture's floor is about a third of its points, and a box face is a
    # few percent: this threshold removes the floor and leaves the boxes whole.
    "plane_min_fraction": 0.05,
    "min_points": 20,
    "split_points": 50_000,
    "split_target": 8_000,
    "max_objects": 40,
}


@pytest.fixture(scope="module")
def scene(tmp_path_factory):
    root = tmp_path_factory.mktemp("scene")
    ply = room_ply(root / "room.ply")
    out = root / "scene.npz"
    splat.ingest(ply, out, hash_source=False)
    return splat.load_scene(out)


def test_voxel_indices_quantise_and_stay_consistent():
    points = np.array([[0.0, 0.0, 0.0], [0.001, 0.0, 0.0], [0.5, 1.0, 2.0]])
    keys, inverse, dims = seg.voxel_indices(points, 0.1)
    assert keys.shape[0] == 2
    assert inverse.shape[0] == 3
    assert int(dims[0]) == 6 and int(dims[1]) == 11 and int(dims[2]) == 21
    assert len(np.unique(keys)) == 2  # the first two points share a voxel


def test_two_separate_blocks_are_two_components():
    vox = np.array(
        [[i, j, k] for i in range(3) for j in range(3) for k in range(3)]
        + [[i + 8, j, k] for i in range(3) for j in range(3) for k in range(3)],
        dtype=np.int64,
    )
    dims = vox.max(axis=0) + 1
    keys = np.unique((vox[:, 0] * dims[1] + vox[:, 1]) * dims[2] + vox[:, 2])
    labels = seg.label_components(keys, dims)
    assert int(labels.max()) + 1 == 2


def test_a_chain_of_voxels_is_one_component():
    vox = np.array([[i, 0, 0] for i in range(20)], dtype=np.int64)
    dims = vox.max(axis=0) + 1
    keys = np.unique((vox[:, 0] * dims[1] + vox[:, 1]) * dims[2] + vox[:, 2])
    labels = seg.label_components(keys, dims)
    assert int(labels.max()) + 1 == 1


def test_a_long_pipe_is_cut_into_pieces_when_it_is_too_long():
    axis = np.arange(-1.0, 1.0, 0.01)
    points = np.stack([axis, np.full(axis.size, 0.5), np.zeros(axis.size)], axis=1)
    pieces = seg.split_component(points, target=500, max_points=10_000, max_extent=0.6)
    assert len(pieces) >= 3
    assert sum(piece.size for piece in pieces) == points.shape[0]
    rebuilt = np.concatenate([points[piece] for piece in pieces])
    assert rebuilt.shape[0] == points.shape[0]


def test_the_floor_is_found_and_removed(scene):
    planes, keep = seg.find_planes(
        scene.xyz.astype(np.float64),
        up=UP,
        threshold=0.025,
        max_planes=6,
        min_fraction=0.02,
        sample_points=4000,
        iterations=120,
        seed=0,
    )
    floor = seg.floor_plane(planes, UP)
    assert floor is not None
    assert floor.inliers > 100
    height = seg.height_above_plane(np.zeros((1, 3)), floor, UP)[0]
    assert height == pytest.approx(0.0, abs=0.03)
    assert 0 < int((~keep).sum()) < scene.xyz.shape[0]


def test_extraction_frames_the_blocks_with_boxes_that_contain_them(scene, tmp_path):
    payload = seg.segment(scene, tmp_path / "objects.json", params=FAST)
    objects = payload["objects"]
    assert len(objects) >= 3
    assert payload["floor"]["detected"] is True
    assert payload["floor"]["height"] == pytest.approx(0.0, abs=0.03)
    assert payload["counts"]["largest_object_share"] < 0.4

    expected = np.array([0.30, 0.22, -0.10])  # centre of the first block
    centres = np.array([obj["centre"] for obj in objects])
    nearest = objects[int(np.argmin(np.linalg.norm(centres - expected, axis=1)))]
    assert np.linalg.norm(np.array(nearest["centre"]) - expected) < 0.12
    # the block is 0.4 m on a side; the plane band eats the layer of its bottom
    # face that lies inside the floor plane, so the box is a little shorter
    assert all(0.30 <= float(extent) <= 0.50 for extent in nearest["extents"])
    assert nearest["class"] in {"pump", "motor", "valve", "drum", "machine", "cabinet", "unknown"}
    assert 0.0 < nearest["class_confidence"] <= 1.0
    assert nearest["class_reason"]


def test_an_object_holds_only_its_own_points(scene, tmp_path):
    payload = seg.segment(scene, tmp_path / "objects.json", params=FAST)
    objects = {obj["id"]: obj for obj in payload["objects"]}
    assert len(objects) == payload["counts"]["objects"]
    total = sum(obj["points"] for obj in objects.values())
    assert total <= payload["source"]["points"]
    for obj in objects.values():
        assert all(extent > 0 for extent in obj["extents"])
        assert len(obj["axes"]) == 3 and len(obj["axes"][0]) == 3


def test_extraction_is_deterministic(scene, tmp_path):
    first = seg.segment(scene, tmp_path / "a.json", params=FAST)
    second = seg.segment(scene, tmp_path / "b.json", params=FAST)
    assert json.dumps(first["objects"], sort_keys=True) == json.dumps(second["objects"], sort_keys=True)
    assert first["counts"] == second["counts"]


def test_the_voxel_follows_the_measured_point_spacing(scene, tmp_path):
    payload = seg.segment(scene, tmp_path / "objects.json", params=FAST)
    parameters = payload["parameters"]
    spacing = parameters["spacing"]
    assert spacing["spacing_m"] is not None
    assert spacing["floor_points"] > 100
    assert parameters["voxel_m_effective"] >= parameters["voxel_m"]
    assert parameters["voxel_m_effective"] == pytest.approx(
        max(parameters["voxel_m"], seg.VOXEL_PER_SPACING * spacing["spacing_m"]), rel=1e-3
    )


def test_point_spacing_is_measured_from_a_flat_surface():
    up = UP
    cells = np.arange(0.0, 2.0, 0.05)
    gx, gz = np.meshgrid(cells, cells, indexing="ij")
    points = np.stack([gx.ravel(), np.zeros(gx.size), gz.ravel()], axis=1)
    plane = Plane(normal=[0.0, 1.0, 0.0], offset=0.0, inliers=points.shape[0], rms_m=0.0, horizontal=True)
    result = seg.estimate_spacing(points, [plane], up, threshold=0.025)
    assert result["spacing_m"] == pytest.approx(0.05, rel=0.1)
    assert result["floor_area_m2"] > 3.0


def test_a_capture_without_a_floor_keeps_the_requested_voxel():
    points = np.random.default_rng(3).uniform(-1.0, 1.0, size=(500, 3))
    result = seg.estimate_spacing(points, [], UP, threshold=0.025)
    assert result["spacing_m"] is None
    assert "floor" in result["method"]


def test_the_artifact_carries_the_contract(scene, tmp_path):
    out = tmp_path / "objects.json"
    seg.segment(scene, out, params=FAST)
    payload = json.loads(out.read_text())
    for key in ("artifact", "version", "source", "parameters", "planes", "floor", "counts", "objects", "scale_check"):
        assert key in payload
    assert payload["artifact"] == "objects"
    assert payload["source"]["up_axis"] == "+y"
    assert payload["parameters"]["voxel_m_effective"] > 0
    assert payload["planes"]["removed"] >= 1
    assert "class" in payload["objects"][0]
    assert "method" not in payload["objects"][0]  # mapping is the next stage, not this one
    assert payload["camera"] is not None
    assert {"eye", "target", "up"} <= set(payload["camera"])


def test_the_report_prints_the_extraction_numbers(scene, tmp_path):
    payload = seg.segment(scene, tmp_path / "objects.json", params=FAST)
    report = seg.format_report(payload)
    for phrase in ("objects framed", "largest object", "classes", "extraction"):
        assert phrase in report


def _box(extents, axes=None, centre=(0.0, 0.0, 0.0), conf=0.5) -> Object:
    axes = np.eye(3) if axes is None else np.asarray(axes, dtype=float)
    return Object(
        id="OBJ-000",
        centre=list(centre),
        axes=[[float(v) for v in row] for row in axes],
        extents=[float(v) for v in extents],
        points=1000,
        class_="door",
        class_confidence=conf,
        class_reason="test",
        height_above_floor=0.0,
        volume_m3=float(np.prod(extents)),
        planarity=0.1,
    )


def test_a_two_metre_door_passes_the_scale_check():
    door = _box((0.9, 2.0, 0.1))
    check = scale_check([door], UP)
    assert check["performed"] is True
    assert check["median_door_height"] == pytest.approx(2.0, abs=0.1)
    assert check["units_are_metres"] is True


def test_no_door_means_the_scale_check_is_not_claimed():
    check = scale_check([], UP)
    assert check["performed"] is False
    assert "units" in check["reason"]


def test_a_door_that_is_not_two_metres_blocks_the_metre_claim():
    door = _box((0.9, 1.2, 0.1))
    check = scale_check([door], UP)
    assert check["performed"] is True
    assert check["units_are_metres"] is False


def test_vertical_extent_follows_the_up_axis():
    # a box whose long axis is the up axis, with a rotation into the scene frame
    door = _box((0.9, 0.95, 2.0))
    assert vertical_extent(door, UP) == pytest.approx(0.95)
    turned = _box((0.9, 2.0, 0.95))
    assert vertical_extent(turned, UP) == pytest.approx(2.0)


@pytest.mark.parametrize(
    "extents, expected",
    [
        ((2.5, 0.10, 0.10), "pipe"),
        ((1.4, 0.9, 0.9), "motor"),
        ((0.3, 0.25, 0.2), "pump"),
    ],
)
def test_classify_names_the_shape_it_sees(extents, expected):
    name, confidence, reason = classify(np.array(extents, dtype=float), np.eye(3), UP, 0.1)
    assert name == expected
    assert 0.0 < confidence <= 1.0
    assert reason
