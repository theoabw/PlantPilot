"""Tests for the parts of scripts/make_vision_boxes.py that need no model.

The model run itself needs a GPU and downloaded weights, so it is not tested here.
These cover the geometry and bookkeeping around it: the ceiling it renders below, the
cache names that keep renders and outlines apart, joining outlines across views, and
picking trial views.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import numpy as np
import pytest

SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "make_vision_boxes.py"


@pytest.fixture(scope="module")
def vision():
    spec = importlib.util.spec_from_file_location("make_vision_boxes", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


UP = np.array([0.0, 0.0, 1.0])


def plane(height: float, inliers: int, horizontal: bool = True) -> dict:
    # A plane is normal . x + offset = 0, so a horizontal plane at z = h has offset -h.
    return {"horizontal": horizontal, "normal": [0.0, 0.0, 1.0], "offset": -height, "inliers": inliers}


def test_ceiling_is_the_largest_horizontal_plane_above_head_height(vision):
    payload = {"planes": {"items": [plane(0.0, 9000), plane(0.8, 5000), plane(2.0, 3000), plane(2.4, 1000)]}}
    assert vision.ceiling_height(payload, UP, 0.0) == pytest.approx(2.0)


def test_no_ceiling_when_nothing_horizontal_is_high_enough(vision):
    payload = {"planes": {"items": [plane(0.0, 9000), plane(0.8, 5000), plane(2.0, 3000, horizontal=False)]}}
    assert vision.ceiling_height(payload, UP, 0.0) is None


def test_render_cache_name_follows_the_camera(vision):
    view = {"eye": [0.0, 0.0, 1.2], "target": [1.0, 0.0, 1.2]}
    turned = {"eye": [0.0, 0.0, 1.2], "target": [0.0, 1.0, 1.2]}
    assert vision.view_key(view) == vision.view_key(dict(view))
    assert vision.view_key(view) != vision.view_key(turned)


def test_outline_cache_name_changes_with_the_outline_settings(vision, monkeypatch, tmp_path):
    view = {"eye": [0.0, 0.0, 1.2], "target": [1.0, 0.0, 1.2]}
    before = vision.lift_cache_path(tmp_path, view)
    monkeypatch.setattr(vision, "OUTLINE_ARGS", dict(vision.OUTLINE_ARGS, pred_iou_thresh=0.5))
    assert vision.lift_cache_path(tmp_path, view) != before


def test_outlines_of_one_thing_from_several_views_join(vision, monkeypatch):
    monkeypatch.setattr(vision, "MIN_VIEWS", 3)
    voxel_of = np.arange(1000)
    thing = np.arange(0, 100)
    records = [{"view": view, "points": thing} for view in range(3)]
    # The same view outlining a neighbour never joins it to the thing.
    records.append({"view": 0, "points": np.arange(100, 200)})
    # Something only one view saw is not kept.
    records.append({"view": 3, "points": np.arange(500, 600)})
    fused = vision.fuse(records, voxel_of)
    assert len(fused) == 1
    assert fused[0]["views"] == 3
    assert np.array_equal(fused[0]["points"], thing)


def test_a_gaussian_claimed_by_one_stray_outline_is_dropped(vision, monkeypatch):
    monkeypatch.setattr(vision, "MIN_VIEWS", 2)
    voxel_of = np.arange(1000)
    records = [
        {"view": 0, "points": np.arange(0, 100)},
        {"view": 1, "points": np.arange(0, 110)},
    ]
    fused = vision.fuse(records, voxel_of)
    assert len(fused) == 1
    assert np.array_equal(fused[0]["points"], np.arange(0, 100))


def test_trial_views_look_at_the_focus_from_different_eyes_first(vision):
    level = [0, 1]
    focus = np.array([0.0, 0.0])
    views = [
        # Straight at the focus.
        {"eye": [-2.0, 0.0, 1.2], "target": [-1.0, 0.0, 1.2]},
        # The same eye, 5 degrees off: better aimed than the other eye, but a repeat.
        {"eye": [-2.0, 0.0, 1.2], "target": [-1.0, 0.0875, 1.2]},
        # Another eye, 15 degrees off.
        {"eye": [2.0, 0.0, 1.2], "target": [1.0, 0.268, 1.2]},
        # Looking away from the focus, and too far from it.
        {"eye": [-2.0, 0.0, 1.2], "target": [-2.0, 1.0, 1.2]},
        {"eye": [9.0, 0.0, 1.2], "target": [8.0, 0.0, 1.2]},
    ]
    chosen = vision.pick_trial(views, 2, focus, level)
    assert chosen == [views[0], views[2]]
    every = vision.pick_trial(views, 10, focus, level)
    assert every == [views[0], views[2], views[1]]
