"""Tests for the asset stage that merges raw boxes and colour seeds."""

from __future__ import annotations

import json
import re

import numpy as np
import pytest

from plantpilot import assets, splat
from splat_fixture import box_shell

RED = (200, 45, 40)
BLUE = (55, 70, 170)
GREY = (120, 112, 105)


def cylinder_shell(centre, radius: float, length: float, count: int, axis: str = "y") -> np.ndarray:
    """A cylinder surface, like a seeded vessel: uniform around and along."""
    rng = np.random.default_rng(0)
    around = rng.uniform(0.0, 2.0 * np.pi, count)
    along = rng.uniform(-length / 2.0, length / 2.0, count)
    centre = np.asarray(centre, dtype=np.float64)
    points = np.empty((count, 3), dtype=np.float64)
    if axis == "y":
        points[:, 0] = centre[0] + radius * np.cos(around)
        points[:, 1] = centre[1] + along
        points[:, 2] = centre[2] + radius * np.sin(around)
    else:
        points[:, 0] = centre[0] + along
        points[:, 1] = centre[1] + radius * np.cos(around)
        points[:, 2] = centre[2] + radius * np.sin(around)
    return points


def floor() -> np.ndarray:
    """A grey floor grid at y = 0, so the scene has a room plane like a capture."""
    axis = np.arange(-2.0, 2.0, 0.1)
    first, second = np.meshgrid(axis, axis, indexing="ij")
    return np.stack([first.ravel(), np.zeros(first.size), second.ravel()], axis=1)


def scene_of(*parts: tuple[np.ndarray, tuple[int, int, int]]) -> splat.Scene:
    """One scene from (points, colour) pairs, with up = +y in the metadata."""
    points = np.concatenate([np.asarray(part, dtype=np.float64) for part, _ in parts])
    colours = np.concatenate(
        [np.tile(np.array(colour, dtype=np.uint8), (len(part), 1)) for part, colour in parts]
    )
    return splat.Scene(
        xyz=points,
        rgb=colours,
        size=np.full((points.shape[0], 3), 0.01, dtype=np.float32),
        alpha=np.full(points.shape[0], 0.9, dtype=np.float32),
        meta={
            "frame": {"up_axis": "+y", "up_axis_index": 1, "up_axis_sign": 1},
            "source": {"file": "synthetic.ply"},
        },
    )


def objects_document(*records: dict) -> dict:
    return {"artifact": "objects", "version": 1, "objects": list(records)}


def object_record(
    object_id: str,
    centre,
    extents,
    *,
    class_name: str = "motor",
    points: int = 3000,
    confidence: float = 0.3,
) -> dict:
    extents = [float(value) for value in extents]
    return {
        "id": object_id,
        "centre": [float(value) for value in centre],
        "axes": np.eye(3).tolist(),
        "extents": extents,
        "points": int(points),
        "class": class_name,
        "class_confidence": float(confidence),
        "class_reason": "machine sized body at floor level",
        "height_above_floor": 0.3,
        "volume_m3": round(float(np.prod(extents)), 3),
        "planarity": 0.1,
    }


def build(scene: splat.Scene, document: dict | None = None) -> dict:
    return assets.build_assets(
        scene, document or objects_document(), scene_path="scene.npz", objects_path="objects.json"
    )


def test_a_red_compact_cluster_is_one_pressure_vessel():
    vessel = cylinder_shell((0.5, 0.8, -1.0), radius=0.45, length=1.4, count=4000)
    payload = build(scene_of((floor(), GREY), (vessel, RED)))

    assert payload["counts"]["colour_instances"] == 1
    vessels = [asset for asset in payload["assets"] if asset["class"] == "pressure_vessel"]
    assert len(vessels) == 1
    assert vessels[0]["label"] == "red pressure vessel"
    # Tolerance 10 cm: the box centre is the centroid of a 4000 point shell with
    # symmetric 2 to 98 percentile extents, so it lands on the seeded axis to
    # well under a centimetre; 10 cm is the requested bound.
    assert np.allclose(vessels[0]["centre"], [0.5, 0.8, -1.0], atol=0.1)


def test_a_blue_compact_cluster_is_one_tank():
    tank = cylinder_shell((-0.5, 0.7, 1.0), radius=0.35, length=1.0, count=3000)
    payload = build(scene_of((floor(), GREY), (tank, BLUE)))

    assert payload["counts"]["colour_instances"] == 1
    assert payload["counts"]["assets"] == 1
    asset = payload["assets"][0]
    assert asset["class"] == "tank"
    assert asset["label"] == "blue tank"
    assert asset["verified"] is True
    assert np.allclose(asset["centre"], [-0.5, 0.7, 1.0], atol=0.1)


def test_a_red_run_is_pipework_not_a_vessel():
    # 2.1 m long and 0.6 m across: elongated, so the label is pipework.
    pipe = cylinder_shell((0.0, 1.2, 2.0), radius=0.3, length=2.2, count=4400, axis="x")
    payload = build(scene_of((floor(), GREY), (pipe, RED)))

    assert payload["counts"]["colour_instances"] == 1
    asset = payload["assets"][0]
    assert asset["class"] == "pipework"
    assert asset["label"] == "red pipework"


def test_fitted_box_is_right_handed_and_encloses_all_points():
    pipe = cylinder_shell((0.0, 1.2, 2.0), radius=0.3, length=2.2, count=4400, axis="x")
    centre, axes, extents = assets.fit_box(pipe)
    local = (pipe - centre) @ axes.T

    assert np.linalg.det(axes) > 0.99
    assert np.allclose(axes @ axes.T, np.eye(3), atol=1e-6)
    assert np.all(np.abs(local) <= extents / 2.0 + 1e-9)


def test_a_seeded_region_beyond_equipment_size_is_not_an_asset():
    # A red panel 3.1 m wide clears the point, span and volume gates but is
    # larger than the equipment envelope shared with the geometry gate.
    panel = box_shell((-1.6, 0.0, 0.0), (3.2, 1.6, 0.12), spacing=0.05)
    payload = build(scene_of((floor(), GREY), (panel, RED)))

    assert payload["counts"]["colour_instances"] == 0
    assert payload["counts"]["assets"] == 0


def test_overlapping_geometry_boxes_of_the_same_equipment_suppress_one():
    document = objects_document(
        object_record("OBJ-001", (0.0, 0.6, 0.0), (0.8, 0.5, 0.5)),
        object_record("OBJ-002", (0.04, 0.62, 0.02), (0.8, 0.5, 0.5)),
    )
    payload = build(scene_of((floor(), GREY)), document)

    assert payload["counts"]["colour_instances"] == 0
    assert payload["counts"]["geometry_candidates"] == 2
    assert payload["counts"]["suppressed"] == 1
    assert payload["counts"]["assets"] == 1
    assert payload["assets"][0]["source_object_ids"] == ["OBJ-001"]
    assert payload["assets"][0]["class"] == "motor"
    assert payload["assets"][0]["verified"] is False


def test_a_structural_class_is_never_an_asset():
    # A duct that would pass every size gate: only the class rule can stop it.
    document = objects_document(
        object_record("OBJ-001", (0.0, 0.6, 0.0), (1.2, 0.5, 0.4), class_name="duct")
    )
    payload = build(scene_of((floor(), GREY)), document)

    assert payload["counts"]["geometry_candidates"] == 0
    assert payload["counts"]["assets"] == 0


def write_scene(path, scene: splat.Scene):
    np.savez(
        path,
        xyz=scene.xyz,
        rgb=scene.rgb,
        size=scene.size,
        alpha=scene.alpha,
        meta=np.array(json.dumps(scene.meta)),
    )
    return path


def test_identical_input_gives_identical_ids_and_json(tmp_path):
    vessel = cylinder_shell((0.5, 0.8, -1.0), radius=0.45, length=1.4, count=4000)
    tank = cylinder_shell((-0.5, 0.7, 1.0), radius=0.35, length=1.0, count=3000)
    motor = object_record("OBJ-001", (3.0, 0.6, 3.0), (0.8, 0.5, 0.5))
    scene = scene_of((floor(), GREY), (vessel, RED), (tank, BLUE))
    scene_path = write_scene(tmp_path / "scene.npz", scene)
    objects_path = tmp_path / "objects.json"
    objects_path.write_text(json.dumps(objects_document(motor)))

    first = tmp_path / "assets_a.json"
    second = tmp_path / "assets_b.json"
    assert assets.main(["--scene", str(scene_path), "--objects", str(objects_path),
                        "--out", str(first)]) == 0
    assert assets.main(["--scene", str(scene_path), "--objects", str(objects_path),
                        "--out", str(second)]) == 0

    assert first.read_bytes() == second.read_bytes()
    document = json.loads(first.read_text())
    assert document["artifact"] == "assets"
    assert document["version"] == 1
    assert document["counts"]["assets"] == len(document["assets"])
    assert [asset["id"] for asset in document["assets"]] == [
        asset["id"] for asset in json.loads(second.read_text())["assets"]
    ]


def test_every_asset_carries_the_documented_fields():
    vessel = cylinder_shell((0.5, 0.8, -1.0), radius=0.45, length=1.4, count=4000)
    tank = cylinder_shell((-0.5, 0.7, 1.0), radius=0.35, length=1.0, count=3000)
    motor = object_record("OBJ-001", (3.0, 0.6, 3.0), (0.8, 0.5, 0.5))
    payload = build(scene_of((floor(), GREY), (vessel, RED), (tank, BLUE)),
                    objects_document(motor))

    assert payload["counts"]["assets"] == 3
    assert payload["counts"]["verified"] == 2
    for asset in payload["assets"]:
        assert re.fullmatch(r"AS-[0-9a-f]{8}", asset["id"])
        assert isinstance(asset["class"], str) and asset["class"]
        assert isinstance(asset["label"], str) and asset["label"]
        assert 0.0 <= asset["confidence"] <= 1.0
        assert isinstance(asset["verified"], bool)
        assert len(asset["centre"]) == 3
        assert np.asarray(asset["axes"]).shape == (3, 3)
        assert len(asset["extents"]) == 3
        assert asset["points"] > 0
        assert len(asset["mean_rgb"]) == 3
        assert all(0 <= value <= 255 for value in asset["mean_rgb"])
        assert isinstance(asset["source_object_ids"], list)
        assert asset["method"] in {"colour_instance", "geometry_box"}
        assert isinstance(asset["reason"], str) and asset["reason"]
    assert payload["counts"]["verified"] == sum(1 for asset in payload["assets"]
                                               if asset["verified"])


def test_the_red_mask_needs_a_relative_margin_as_well_as_an_absolute_one():
    # The warm highlight is bright and warm (r - max(g, b) = 35) but its margin
    # is only 14 percent of the red channel, so a beige wall is not red paint.
    # The vessel red is 78 percent and seeds. A dark red point must not pass the
    # blue test through a uint8 wrap either.
    rgb = np.array(
        [[255, 220, 180], [200, 45, 40], [200, 45, 60], [55, 70, 170]], dtype=np.uint8
    )
    masks = assets.seed_masks(rgb)
    assert not bool(masks["red"][0])
    assert bool(masks["red"][1])
    assert not bool(masks["blue"][1])
    assert not bool(masks["blue"][2])
    assert bool(masks["blue"][3])
    assert not bool(masks["red"][3])


def test_geometry_confidence_comes_from_support_and_decides_verified():
    document = objects_document(
        # compact machine with enough points: verified, base 0.45 plus 0.20 size
        # (5000 of 12000), 0.15 compact and 0.05 equipment.
        object_record("OBJ-001", (-3.0, 0.6, 0.0), (0.8, 0.6, 0.5), class_name="machine",
                      points=5000),
        # compact valve: the valve class gets no equipment term and never verifies.
        object_record("OBJ-002", (-1.0, 0.6, 0.0), (0.8, 0.6, 0.5), class_name="valve",
                      points=6000),
        # long machine (5.3 times its shortest side): no compact term.
        object_record("OBJ-003", (1.0, 0.6, 0.0), (1.6, 0.3, 0.3), class_name="machine",
                      points=6000),
        # compact machine with too few points to be verified.
        object_record("OBJ-004", (3.0, 0.6, 0.0), (0.8, 0.6, 0.5), class_name="machine",
                      points=1000),
    )
    payload = build(scene_of((floor(), GREY)), document)
    by_source = {asset["source_object_ids"][0]: asset for asset in payload["assets"]}

    assert payload["counts"]["assets"] == 4
    assert payload["counts"]["verified"] == 1
    assert by_source["OBJ-001"]["confidence"] == pytest.approx(0.733, abs=1e-3)
    assert by_source["OBJ-001"]["verified"] is True
    assert by_source["OBJ-002"]["confidence"] == pytest.approx(0.700, abs=1e-3)
    assert by_source["OBJ-002"]["verified"] is False
    assert by_source["OBJ-003"]["confidence"] == pytest.approx(0.600, abs=1e-3)
    assert by_source["OBJ-003"]["verified"] is False
    assert by_source["OBJ-004"]["confidence"] == pytest.approx(0.667, abs=1e-3)
    assert by_source["OBJ-004"]["verified"] is False
