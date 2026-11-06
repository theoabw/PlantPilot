"""Tests for the debug renderer that checks the artifacts without a browser."""

from __future__ import annotations

import json

import numpy as np
import pytest
from PIL import Image

from plantpilot import render, splat
from splat_fixture import room_ply


@pytest.fixture(scope="module")
def scene(tmp_path_factory):
    root = tmp_path_factory.mktemp("render")
    ply = room_ply(root / "room.ply")
    out = root / "scene.npz"
    splat.ingest(ply, out, hash_source=False)
    return splat.load_scene(out)


def test_the_camera_puts_its_target_at_the_image_centre():
    camera = render.Camera.look_at(
        eye=(3.0, 2.0, 3.0), target=(0.0, 0.0, 0.0), up_vector=(0.0, 1.0, 0.0), width=400, height=300
    )
    proj = camera.project(np.array([[0.0, 0.0, 0.0]]), np.zeros((1, 3)))
    assert proj["px"][0] == pytest.approx(200.0, abs=0.5)
    assert proj["py"][0] == pytest.approx(150.0, abs=0.5)
    assert bool(proj["visible"][0]) is True


def test_the_top_view_keeps_the_horizontal_axes_apart(scene):
    camera = render.top_down_camera(scene, 400, 300)
    points = np.array([[0.0, 0.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]])
    proj = camera.project(points, np.zeros((3, 3)))
    moves_x = abs(float(proj["px"][1] - proj["px"][0]))
    moves_z = abs(float(proj["py"][2] - proj["py"][0]))
    assert moves_x > 1.0
    assert moves_z > 1.0


def test_a_camera_whose_up_vector_points_along_the_view_is_refused():
    with pytest.raises(ValueError):
        render.Camera.look_at(
            eye=(0.0, 0.0, 0.0), target=(0.0, 0.0, -1.0), up_vector=(0.0, 0.0, 1.0), width=100, height=100
        )


def test_box_corners_follow_the_documented_convention():
    corners = render.box_corners([1.0, 2.0, 3.0], np.eye(3), [0.2, 0.4, 0.6])
    assert corners.shape == (8, 3)
    assert np.allclose(corners.mean(axis=0), [1.0, 2.0, 3.0])
    assert np.allclose(corners.max(axis=0) - corners.min(axis=0), [0.2, 0.4, 0.6])


def test_rendering_writes_a_png_with_the_points(scene, tmp_path):
    out = render.render_scene(scene, tmp_path / "points.png", width=320, height=200)
    image = np.asarray(Image.open(out).convert("RGB"))
    assert image.shape == (200, 320, 3)
    assert int(image.max()) > 0
    assert int((image.sum(axis=2) > 0).sum()) > 100


def test_rendering_draws_the_boxes_in_their_class_colour(scene, tmp_path):
    box = {
        "id": "OBJ-001",
        "class": "pump",
        "centre": [0.3, 0.22, -0.1],
        "axes": np.eye(3).tolist(),
        "extents": [0.4, 0.4, 0.4],
    }
    out = render.render_scene(scene, tmp_path / "boxes.png", objects=[box], width=400, height=300)
    image = np.asarray(Image.open(out).convert("RGB")).astype(int)
    target = np.array(render.CLASS_COLOURS["pump"], dtype=int)
    assert (np.abs(image - target).sum(axis=2) < 30).any()


def test_the_faulty_object_is_drawn_in_the_fault_colour(scene, tmp_path):
    box = {
        "id": "OBJ-007",
        "class": "valve",
        "centre": [0.3, 0.22, -0.1],
        "axes": np.eye(3).tolist(),
        "extents": [0.4, 0.4, 0.4],
    }
    out = render.render_scene(scene, tmp_path / "fault.png", objects=[box], fault_id="OBJ-007",
                              width=400, height=300)
    image = np.asarray(Image.open(out).convert("RGB")).astype(int)
    target = np.array(render.FAULT_COLOUR, dtype=int)
    assert (np.abs(image - target).sum(axis=2) < 30).any()


def test_the_cli_writes_the_png_it_reports(scene, tmp_path, capsys):
    scene_path = tmp_path / "scene.npz"
    np.savez(
        scene_path,
        xyz=scene.xyz,
        rgb=scene.rgb,
        size=scene.size,
        alpha=scene.alpha,
        meta=np.array(json.dumps(scene.meta)),
    )
    code = render.main(["--scene", str(scene_path), "--out", str(tmp_path / "out.png"),
                        "--width", "160", "--height", "120"])
    assert code == 0
    printed = capsys.readouterr().out
    assert "view of" in printed
    assert "out.png" in printed
    assert (tmp_path / "out.png").exists()
