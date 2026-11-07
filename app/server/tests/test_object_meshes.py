"""Tests for the object mesh bake, without Open3D.

The script is imported by path so these tests run in the offline server
environment, where Open3D is not installed. Only the pure helpers are covered
here; the Poisson bake itself is exercised by running the script in an
environment that has Open3D.
"""

from __future__ import annotations

import builtins
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "make_object_meshes.py"

spec = importlib.util.spec_from_file_location("make_object_meshes_under_test", SCRIPT)
meshes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(meshes)

IDENTITY_AXES = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]


def anchor(anchor_id: str, centre, extents) -> dict:
    return {
        "id": anchor_id,
        "label": anchor_id,
        "class": "equipment",
        "centre": centre,
        "axes": IDENTITY_AXES,
        "extents": extents,
    }


def test_owned_gaussians_pick_the_smallest_covering_anchor():
    xyz = np.array(
        [
            [0.0, 0.0, 0.0],  # inside both boxes
            [0.9, 0.0, 0.0],  # inside the large box only
            [3.0, 0.0, 0.0],  # outside every box
        ]
    )
    big = anchor("BIG", [0.0, 0.0, 0.0], [2.0, 2.0, 2.0])  # volume 8
    small = anchor("SMALL", [0.0, 0.0, 0.0], [1.0, 1.0, 1.0])  # volume 1

    labels = meshes.owned_anchor_indices(xyz, [big, small])
    assert labels.tolist() == [1, 0, -1]

    # The same shared gaussian still goes to the small box when the artifact
    # order changes, so the join does not depend on review order.
    labels_reversed = meshes.owned_anchor_indices(xyz, [small, big])
    assert labels_reversed.tolist() == [0, 1, -1]


def test_alpha_and_mean_size_filters_drop_the_boundaries():
    alpha = np.array([0.05, 0.2, 0.2, 0.9])
    size = np.array(
        [
            [0.12, 0.12, 0.12],  # alpha exactly at the floor: dropped
            [0.12, 0.12, 0.12],  # mean size exactly at the cap: dropped
            [0.1199, 0.0, 0.0],  # just under both limits: kept
            [0.5, 0.5, 0.5],  # far over the size cap: dropped
        ]
    )
    keep = meshes.usable_gaussian_mask(alpha, size)
    assert keep.tolist() == [False, False, True, False]


def test_normals_use_the_thinnest_axis_and_point_outward():
    # Identity quaternions mean the ellipsoid axes are the world axes.
    rotation = [[1.0, 0.0, 0.0, 0.0], [1.0, 0.0, 0.0, 0.0]]
    size = np.array([[0.3, 0.2, 0.05], [0.3, 0.2, 0.05]])  # thinnest is axis 2
    points = np.array([[0.0, 0.0, 1.0], [0.0, 0.0, -1.0]])
    normals = meshes.gaussian_normals(rotation, size, points, centroid=[0.0, 0.0, 0.0])

    assert np.allclose(normals[0], [0.0, 0.0, 1.0])
    assert np.allclose(normals[1], [0.0, 0.0, -1.0])
    for normal, point in zip(normals, points):
        assert float(np.dot(normal, point)) > 0.0, "the normal must point away from the centroid"

    # A different thinnest axis gives that axis as the normal, not always z.
    thin_x = np.array([[0.05, 0.3, 0.2]])
    normal_x = meshes.gaussian_normals(
        [[1.0, 0.0, 0.0, 0.0]], thin_x, np.array([[1.0, 0.0, 0.0]]), centroid=[0.0, 0.0, 0.0]
    )
    assert np.allclose(normal_x[0], [1.0, 0.0, 0.0])


def test_crop_mask_expands_the_anchor_box_by_the_margin():
    vertices = np.array(
        [
            [0.0, 0.0, 0.0],
            [0.52, 0.0, 0.0],  # exactly at half extent 0.5 plus 0.02: kept
            [0.53, 0.0, 0.0],  # just outside the margin: cropped
            [-0.52, 0.0, 0.0],
            [0.0, 0.0, 0.6],  # outside on another axis
        ]
    )
    keep = meshes.crop_mask(vertices, [0.0, 0.0, 0.0], IDENTITY_AXES, [1.0, 1.0, 1.0], margin=0.02)
    assert keep.tolist() == [True, True, False, True, False]


def test_manifest_builder_carries_the_required_schema_and_counts():
    box = anchor("AN-abc123", [1.0, 2.0, 3.0], [1.0, 2.0, 3.0])
    record = meshes.object_record(
        box,
        "AN-abc123.ply",
        {"min": [0.0, 1.0, 2.0], "max": [2.0, 3.0, 4.0], "extent": [2.0, 2.0, 2.0]},
        12,
        8,
        100,
        True,
        usable_gaussians=80,
        downsampled_points=40,
    )
    payload = meshes.manifest_document(
        "equipment",
        "data/equipment/scene.npz",
        "data/equipment/anchors.json",
        [record],
    )
    assert payload["artifact"] == "object_meshes"
    assert payload["version"] == 1
    assert payload["capture"] == "equipment"
    assert payload["source"] == {
        "scene": "data/equipment/scene.npz",
        "anchors": "data/equipment/anchors.json",
    }
    assert payload["counts"] == {
        "objects": 1,
        "triangles": 12,
        "vertices": 8,
        "owned_gaussians": 100,
        "watertight": 1,
    }
    item = payload["objects"][0]
    required = {
        "anchor_id",
        "label",
        "class",
        "file",
        "world_bbox",
        "triangles",
        "vertices",
        "owned_gaussians",
        "anchor_box",
    }
    assert required <= set(item)
    assert item["file"] == "AN-abc123.ply"
    assert set(item["anchor_box"]) == {"centre", "axes", "extents"}
    assert set(item["world_bbox"]) == {"min", "max", "extent"}
    assert item["usable_gaussians"] == 80
    assert json.loads(json.dumps(payload)) == payload


def test_missing_open3d_exits_with_the_install_hint_and_writes_nothing(tmp_path, monkeypatch):
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "open3d" or name.startswith("open3d."):
            raise ImportError("No module named 'open3d'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    out = tmp_path / "out"
    with pytest.raises(SystemExit) as excinfo:
        meshes.main(
            [
                "--scene",
                str(tmp_path / "scene.npz"),
                "--anchors",
                str(tmp_path / "anchors.json"),
                "--out",
                str(out),
            ]
        )
    assert "uv pip install open3d" in str(excinfo.value)
    assert not out.exists(), "nothing may be written when Open3D is unavailable"


def test_capture_name_comes_from_the_scene_parent_directory(tmp_path):
    scene = tmp_path / "equipment" / "scene.npz"
    assert meshes.capture_name(scene) == "equipment"
    assert meshes.safe_file_stem("AN-abc/../x") == "AN-abc_.._x"
