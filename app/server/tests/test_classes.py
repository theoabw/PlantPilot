"""Tests for the class-refinement stage: context rules, fusion names, fallback.

The stage exists because shape alone called an office chair a valve. These tests
pin the two rules that separate the cases, and the fallback that says `object`
when neither rule can support the shape's guess.
"""

from __future__ import annotations

import copy

import pytest

from plantpilot import classes

UP = [0.0, -1.0, 0.0]
FLOOR_HEIGHT = -1.0
IDENTITY_AXES = [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]]


def payload(objects: list[dict]) -> dict:
    """A y-down capture whose floor sits at y +1.0, so y 0.9 is 0.1 m above it."""
    return {
        "artifact": "objects",
        "version": 1,
        "source": {"capture": "test.ply", "up_axis": "-y"},
        "floor": {"detected": True, "normal": [0.0, -1.0, 0.0], "height": FLOOR_HEIGHT},
        "counts": {},
        "objects": objects,
    }


def box(object_id: str, class_name: str, centre, extents, confidence: float = 0.4) -> dict:
    return {
        "id": object_id,
        "centre": list(centre),
        "axes": [list(row) for row in IDENTITY_AXES],
        "extents": list(extents),
        "points": 100,
        "class": class_name,
        "class_confidence": confidence,
        "class_reason": "shape rule",
    }


def by_id(refined: dict) -> dict[str, dict]:
    return {obj["id"]: obj for obj in refined["objects"]}


def test_a_compact_box_with_no_pipework_is_not_called_a_valve():
    # A chair seat: compact, 0.3 to 0.7 m above the floor, nothing attached.
    seat = box("OBJ-001", "valve", [0.0, 0.5, 0.0], [0.5, 0.4, 0.5])
    refined = classes.refine(payload([seat]))
    result = by_id(refined)["OBJ-001"]
    assert result["class"] == "object"
    assert "cannot be supported" in result["class_reason"]
    assert "no pipe or duct" in result["class_reason"]
    assert result["class_confidence"] <= 0.2


def test_a_valve_fitted_to_pipework_stays_a_valve():
    valve = box("OBJ-001", "valve", [0.0, 0.5, 0.0], [0.3, 0.3, 0.3])
    pipe = box("OBJ-002", "pipe", [0.45, 0.5, 0.0], [0.1, 1.0, 0.1])
    refined = classes.refine(payload([valve, pipe]))
    result = by_id(refined)["OBJ-001"]
    assert result["class"] == "valve"
    assert "fitted to OBJ-002" in result["class_reason"]
    assert result["class_confidence"] <= 0.5


def test_a_pipe_far_from_the_valve_does_not_support_the_claim():
    valve = box("OBJ-001", "valve", [0.0, 0.5, 0.0], [0.3, 0.3, 0.3])
    pipe = box("OBJ-002", "pipe", [1.6, 0.5, 0.0], [0.1, 1.0, 0.1])
    refined = classes.refine(payload([valve, pipe]))
    assert by_id(refined)["OBJ-001"]["class"] == "object"


def test_a_machine_on_the_floor_stays_a_machine():
    machine = box("OBJ-001", "machine", [0.0, 0.9, 0.0], [0.6, 0.2, 0.6])
    refined = classes.refine(payload([machine]))
    result = by_id(refined)["OBJ-001"]
    assert result["class"] == "machine"
    assert "rests on the floor" in result["class_reason"]


def test_a_machine_with_nothing_under_it_becomes_generic():
    floating = box("OBJ-001", "machine", [0.0, 0.5, 0.0], [0.6, 0.4, 0.6])
    refined = classes.refine(payload([floating]))
    result = by_id(refined)["OBJ-001"]
    assert result["class"] == "object"
    assert "nothing under it" in result["class_reason"]


def test_a_box_standing_on_another_box_is_supported():
    stand = box("OBJ-001", "pallet", [0.0, 0.92, 0.0], [0.6, 0.16, 0.6])
    machine = box("OBJ-002", "machine", [0.0, 0.70, 0.0], [0.6, 0.3, 0.6])
    refined = classes.refine(payload([stand, machine]))
    result = by_id(refined)["OBJ-002"]
    assert result["class"] == "machine"
    assert "stands on OBJ-001" in result["class_reason"]


def test_a_structural_class_is_left_alone():
    duct = box("OBJ-001", "duct", [0.0, 0.5, 0.0], [2.0, 0.4, 0.3], confidence=0.4)
    refined = classes.refine(payload([duct]))
    result = by_id(refined)["OBJ-001"]
    assert result["class"] == "duct"
    assert result["class_reason"] == "shape rule"


def test_a_fused_instance_names_the_object_it_sits_on():
    seat = box("OBJ-001", "valve", [1.0, 0.6, 0.0], [0.5, 0.4, 0.5])
    instance = {
        "id": "SBX-0005",
        "label": "office chair",
        "class": "furniture",
        "object_class": "seat",
        "centre": [1.02, 0.62, 0.03],
        "axes": [list(row) for row in IDENTITY_AXES],
        "extents": [0.6, 0.9, 0.6],
        "views": 6,
        "score": 0.95,
    }
    refined = classes.refine(payload([seat]), [instance])
    result = by_id(refined)["OBJ-001"]
    assert result["class"] == "seat"
    assert result["class_confidence"] > 0.5
    assert result["class_source"] == "multi_view_instance_fusion"
    assert "office chair" in result["class_reason"]
    assert refined["counts"]["labels_fused"] == 1


def test_an_instance_far_away_does_not_rename_an_object():
    seat = box("OBJ-001", "machine", [1.0, 0.9, 0.0], [0.5, 0.2, 0.5])
    instance = {
        "id": "SBX-0005",
        "label": "office chair",
        "class": "furniture",
        "object_class": "seat",
        "centre": [2.5, 0.62, 0.0],
        "axes": [list(row) for row in IDENTITY_AXES],
        "extents": [0.6, 0.9, 0.6],
        "views": 6,
        "score": 0.95,
    }
    refined = classes.refine(payload([seat]), [instance])
    assert by_id(refined)["OBJ-001"]["class"] == "machine"
    assert refined["counts"]["labels_fused"] == 0


def test_the_counts_agree_with_the_classes_written():
    objects = [
        box("OBJ-001", "valve", [0.0, 0.5, 0.0], [0.3, 0.3, 0.3]),
        box("OBJ-002", "pipe", [0.45, 0.5, 0.0], [0.1, 1.0, 0.1]),
        box("OBJ-003", "duct", [2.0, 0.5, 0.0], [2.0, 0.4, 0.3]),
    ]
    refined = classes.refine(payload(objects))
    histogram: dict[str, int] = {}
    for obj in refined["objects"]:
        histogram[obj["class"]] = histogram.get(obj["class"], 0) + 1
    assert refined["counts"]["objects_by_class"] == dict(sorted(histogram.items()))
    assert refined["counts"]["labels_generic"] == histogram.get("object", 0)


def test_two_runs_are_identical():
    objects = [
        box("OBJ-001", "valve", [0.0, 0.5, 0.0], [0.3, 0.3, 0.3]),
        box("OBJ-002", "machine", [1.5, 0.5, 0.0], [0.6, 0.4, 0.6]),
        box("OBJ-003", "machine", [3.0, 0.9, 0.0], [0.6, 0.2, 0.6]),
    ]
    source = payload(objects)
    first = classes.refine(copy.deepcopy(source))
    second = classes.refine(copy.deepcopy(source))
    assert first == second


def rotated_box(object_id: str, class_name: str, angle_degrees: float) -> dict:
    """A box turned about the up axis, which is the case a row read gets wrong."""
    import math

    angle = math.radians(angle_degrees)
    axes = [
        [math.cos(angle), 0.0, math.sin(angle)],
        [0.0, 1.0, 0.0],
        [-math.sin(angle), 0.0, math.cos(angle)],
    ]
    return {
        "id": object_id,
        "centre": [0.0, 0.5, 0.0],
        "axes": axes,
        "extents": [1.6, 0.9, 0.4],
        "points": 100,
        "class": class_name,
        "class_confidence": 0.4,
        "class_reason": "shape rule",
    }


def test_the_footprint_does_not_depend_on_the_order_of_the_axes():
    import numpy as np

    frame = rotated_box("OBJ-001", "machine", 37.0)
    plain = classes.footprint(frame, np.array(UP))
    for order in ([1, 2, 0], [2, 0, 1], [0, 2, 1]):
        permuted = {**frame, "axes": [frame["axes"][i] for i in order], "extents": [frame["extents"][i] for i in order]}
        moved = classes.footprint(permuted, np.array(UP))
        assert moved == class_approx(plain)


def class_approx(values):
    import pytest

    return pytest.approx(list(values), abs=1e-9)


def test_the_footprint_matches_the_projected_corners():
    import itertools

    import numpy as np

    frame = rotated_box("OBJ-001", "machine", 37.0)
    centre = np.array(frame["centre"])
    axes = np.array(frame["axes"])
    extents = np.array(frame["extents"])
    corners = np.array([
        centre + sum(sign * 0.5 * extents[index] * axes[index] for index, sign in enumerate(signs))
        for signs in itertools.product([-1, 1], repeat=3)
    ])
    reach = classes.footprint(frame, np.array(UP))
    assert reach[0] == pytest.approx(float(corners[:, 0].min()), abs=1e-9)
    assert reach[1] == pytest.approx(float(corners[:, 0].max()), abs=1e-9)
    assert reach[2] == pytest.approx(float(corners[:, 2].min()), abs=1e-9)
    assert reach[3] == pytest.approx(float(corners[:, 2].max()), abs=1e-9)
