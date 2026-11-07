"""Tests for the object audit: columns, floating fragments and coverage.

The audit is the check on whether a box is a whole object or a band cut out of
one, so the test fixes the two shapes it has to separate: a machine resting on a
stand must read as supported, and a band of a taller object with nothing under
it must read as floating.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "object_audit.py"


def load_audit():
    spec = importlib.util.spec_from_file_location("object_audit", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def box(object_id: str, class_name: str, centre, extents):
    return {
        "id": object_id,
        "class": class_name,
        "centre": list(centre),
        "axes": [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        "extents": list(extents),
    }


def payload(objects, planes=None):
    """A capture frame with up on -y and the floor at scene y +1.0.

    A point on the floor is at y 1.0, so a point at y 0.65 is 0.35 m above it.
    """
    return {
        "artifact": "objects",
        "source": {"capture": "test.ply", "up_axis": "-y"},
        "floor": {"detected": True, "normal": [0.0, -1.0, 0.0], "height": -1.0},
        "planes": planes or [],
        "counts": {"clusters": len(objects), "capped": 0},
        "objects": objects,
    }


def test_a_box_is_measured_in_metres_above_the_floor():
    audit = load_audit()
    up = np.array([0.0, -1.0, 0.0])
    low, high = audit.box_vertical_span(box("OBJ-001", "machine", [0.0, 0.65, 0.0], [0.4, 0.5, 0.4]), up, -1.0)
    assert low == pytest.approx(0.10, abs=1e-9)
    assert high == pytest.approx(0.60, abs=1e-9)


def test_a_machine_standing_on_a_stand_is_not_floating():
    audit = load_audit()
    up = np.array([0.0, -1.0, 0.0])
    stand = box("OBJ-001", "pallet", [0.0, 0.90, 0.0], [0.6, 0.2, 0.6])
    machine = box("OBJ-002", "machine", [0.0, 0.65, 0.0], [0.6, 0.5, 0.6])
    floating = audit.floating_objects([stand, machine], up, -1.0)
    assert floating == []


def test_a_band_with_nothing_under_it_is_floating():
    audit = load_audit()
    up = np.array([0.0, -1.0, 0.0])
    band = box("OBJ-001", "machine", [0.0, 0.40, 0.0], [0.6, 0.2, 0.6])
    floating = audit.floating_objects([band], up, -1.0)
    assert [row["id"] for row in floating] == ["OBJ-001"]


def test_the_column_counts_every_box_stacked_over_an_anchor():
    audit = load_audit()
    up = np.array([0.0, -1.0, 0.0])
    stand = box("OBJ-001", "pallet", [0.0, 0.90, 0.0], [0.6, 0.2, 0.6])
    machine = box("OBJ-002", "machine", [0.0, 0.65, 0.0], [0.6, 0.5, 0.6])
    # A box on the other side of the room must not join the column.
    elsewhere = box("OBJ-003", "valve", [2.0, 0.65, 0.0], [0.6, 0.5, 0.6])
    anchor = box("AN-1", "machine", [0.0, 0.55, 0.0], [0.6, 0.6, 0.6])
    column = audit.column_boxes(anchor, [stand, machine, elsewhere], up, -1.0)
    # ordered from the floor up: the stand first, then the machine on it
    assert [row["id"] for row in column] == ["OBJ-001", "OBJ-002"]
    assert column[1]["class"] == "machine"


def test_the_audit_reports_a_gap_the_fixture_can_be_checked_against():
    audit = load_audit()
    stand = box("OBJ-001", "pallet", [0.0, 0.90, 0.0], [0.6, 0.2, 0.6])
    machine = box("OBJ-002", "machine", [0.0, 0.65, 0.0], [0.6, 0.5, 0.6])
    anchor = box("AN-1", "machine", [0.0, 0.55, 0.0], [0.6, 0.6, 0.6])
    anchor["sam3"] = {"extent_ratio": [1.0, 1.4, 1.7]}
    result = audit.audit(payload([stand, machine]), [anchor], None)
    row = result["anchors"][0]
    assert row["column_objects"] == 2
    assert row["tallest_height"] == pytest.approx(0.50, abs=1e-9)
    assert row["tallest_low"] == pytest.approx(0.10, abs=1e-9)
    assert row["sam3_extent_ratio"] == [1.0, 1.4, 1.7]
    assert row["span_is_one_box"] is False


def test_coverage_counts_how_many_boxes_a_point_falls_inside():
    audit = load_audit()
    first = box("OBJ-001", "machine", [0.0, 0.65, 0.0], [0.4, 0.5, 0.4])
    second = box("OBJ-002", "machine", [0.0, 0.65, 0.0], [0.4, 0.5, 0.4])
    points = np.array([[0.0, 0.65, 0.0], [2.0, 0.65, 0.0]], dtype=np.float64)
    counted = audit.coverage(points, [first, second])
    assert counted["points"] == 2
    assert counted["inside_two"] == 1
    assert counted["inside_none"] == 1


def test_the_summary_and_the_artifact_agree(tmp_path):
    audit = load_audit()
    objects_path = tmp_path / "objects.json"
    anchors_path = tmp_path / "anchors.json"
    objects_path.write_text(json.dumps(payload([box("OBJ-001", "machine", [0.0, 0.40, 0.0], [0.6, 0.2, 0.6])])))
    anchors_path.write_text(json.dumps({"anchors": [box("AN-1", "machine", [0.0, 0.40, 0.0], [0.6, 0.2, 0.6])]}))
    out = tmp_path / "audit.json"
    audit.main(["--objects", str(objects_path), "--anchors", str(anchors_path), "--out", str(out)])
    written = json.loads(out.read_text())
    assert written["artifact"] == "object-audit"
    assert written["objects"] == 1
    assert len(written["floating"]) == 1
    table = audit.summary(written)
    assert "AN-1" in table
    assert "floating" in table.lower()


def test_the_audit_footprint_is_the_projected_corner_box():
    import itertools
    import math

    audit = load_audit()
    up = np.array([0.0, -1.0, 0.0])
    angle = math.radians(37.0)
    axes = [[math.cos(angle), 0.0, math.sin(angle)], [0.0, 1.0, 0.0], [-math.sin(angle), 0.0, math.cos(angle)]]
    extents = [1.6, 0.9, 0.4]
    frame = {"id": "OBJ-001", "class": "machine", "centre": [0.0, 0.5, 0.0], "axes": axes, "extents": extents}
    centre = np.array(frame["centre"])
    matrix = np.array(axes)
    lengths = np.array(extents)
    corners = np.array([
        centre + sum(sign * 0.5 * lengths[index] * matrix[index] for index, sign in enumerate(signs))
        for signs in itertools.product([-1, 1], repeat=3)
    ])
    x0, x1, z0, z1 = audit.box_footprint(frame, up)
    assert x0 == pytest.approx(float(corners[:, 0].min()), abs=1e-9)
    assert x1 == pytest.approx(float(corners[:, 0].max()), abs=1e-9)
    assert z0 == pytest.approx(float(corners[:, 2].min()), abs=1e-9)
    assert z1 == pytest.approx(float(corners[:, 2].max()), abs=1e-9)


def test_the_audit_footprint_ignores_the_order_of_the_axes():
    import math

    audit = load_audit()
    up = np.array([0.0, -1.0, 0.0])
    angle = math.radians(37.0)
    axes = [[math.cos(angle), 0.0, math.sin(angle)], [0.0, 1.0, 0.0], [-math.sin(angle), 0.0, math.cos(angle)]]
    frame = {"id": "OBJ-001", "class": "machine", "centre": [0.0, 0.5, 0.0], "axes": axes, "extents": [1.6, 0.9, 0.4]}
    plain = audit.box_footprint(frame, up)
    for order in ([1, 2, 0], [2, 0, 1], [0, 2, 1]):
        permuted = {**frame, "axes": [axes[i] for i in order], "extents": [frame["extents"][i] for i in order]}
        moved = audit.box_footprint(permuted, up)
        assert moved == pytest.approx(list(plain), abs=1e-9)
