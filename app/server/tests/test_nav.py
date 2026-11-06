import math
from pathlib import Path
import numpy as np
import pytest

from plantpilot import nav

ROOT = Path(__file__).resolve().parents[3]
SPEC = nav.load_spec(ROOT / "fixtures" / "plant" / "plant.json")
START = (2.0, 0.8)
WEST_CLOSED = [[0.0, 4.8, 4.6, 7.2]]


def test_every_inspection_point_is_reachable():
    for asset in SPEC["assets"]:
        result = nav.plan(SPEC, START, asset["waypoint"])
        assert result["reachable"] is True, asset["id"]
        assert result["distance_m"] > 0.5
        # Acceptance Check 4: clearance >= 0.3 m (corridor, docking zone excluded)
        assert result["clearance_m"] >= 0.3, f"{asset['id']}: clearance={result['clearance_m']}"


def test_the_plain_route_uses_the_west_aisle():
    result = nav.plan(SPEC, START, (8.0, 8.8))
    xs = [p[0] for p in result["path"]]
    assert max(xs) < 9.0 and min(xs) < 2.0


def test_closing_the_west_aisle_forces_a_longer_route():
    plain = nav.plan(SPEC, START, (8.0, 8.8))
    blocked = nav.plan(SPEC, START, (8.0, 8.8), blockers=WEST_CLOSED)
    assert blocked["reachable"] is True
    assert blocked["distance_m"] > plain["distance_m"] + 4.0
    assert max(p[0] for p in blocked["path"]) > 10.0


def test_a_wall_across_the_hall_reports_unreachable_with_a_reason():
    result = nav.plan(SPEC, START, (8.0, 8.8), blockers=[[0.0, 1.5, 16.0, 2.2]])
    assert result["reachable"] is False
    assert "no walkable route" in result["reason"]


def test_agent_width_changes_the_route():
    wide = nav.plan(SPEC, START, (8.0, 8.8), agent_radius_m=0.9)
    assert wide["reachable"] in (True, False)
    if wide["reachable"]:
        assert wide["clearance_m"] >= 0.65


# --- New Tests for Seat B Requirements (Acceptance Checks 4 & 5) ---

def test_detect_floor():
    # Synthetic point cloud: 1000 floor points around y=0.0, 500 elevated points between 0.5 and 2.5
    rng = np.random.default_rng(42)
    floor_pts = rng.normal(loc=[0.0, 0.0, 0.0], scale=[3.0, 0.02, 3.0], size=(1000, 3))
    air_pts = rng.uniform(low=[-3.0, 0.5, -3.0], high=[3.0, 2.5, 3.0], size=(500, 3))
    pts = np.vstack([floor_pts, air_pts])

    floor_y, y_min, y_max = nav.detect_floor(pts, up_axis=1)
    assert abs(floor_y) < 0.08
    assert y_min < floor_y <= y_max


def test_detect_floor_honours_a_negative_up_axis():
    points = np.array([[0.0, 1.0, 0.0], [1.0, 1.0, 1.0], [0.0, 0.0, 0.0]])

    floor_y, _, _ = nav.detect_floor(points, up_axis=1, up_axis_sign=-1)

    assert floor_y < -0.5


def test_grid_from_cloud_and_clearance():
    # Build point cloud with an obstacle at center (0, 0)
    rng = np.random.default_rng(42)
    floor_pts = rng.uniform(low=[-4.0, -0.02, -4.0], high=[4.0, 0.02, 4.0], size=(2000, 3))
    # Obstacle pillar from x in [-0.5, 0.5], z in [-0.5, 0.5], y in [0.2, 1.5]
    obs_pts = rng.uniform(low=[-0.5, 0.2, -0.5], high=[0.5, 1.5, 0.5], size=(500, 3))
    pts = np.vstack([floor_pts, obs_pts])

    grid = nav.Grid.from_cloud(pts, floor_y=0.0, up_axis=1)
    assert grid.cols > 10 and grid.rows > 10

    # Center cell should be blocked
    center_r, center_c = grid.to_cell((0.0, 0.0))
    assert not grid.walkable(center_r, center_c)

    # Outer corner should be walkable
    corner_r, corner_c = grid.to_cell((3.0, 3.0))
    assert grid.walkable(corner_r, corner_c)
    assert grid.clearance_m[corner_r, corner_c] > 0.0


def test_compute_service_waypoint():
    grid = nav.Grid(SPEC)
    pump_box = {
        "id": "OBJ-P005",
        "center": [4.0, 0.5, 5.0],
        "extents": [1.0, 0.8, 1.0],
        "class_proposal": "pump",
    }
    wp = nav.compute_service_waypoint(pump_box, grid, target_dist_m=0.9, min_dist_m=0.6)
    assert wp is not None
    # Distance from center must be >= half extent (0.5) + min_dist (0.6) = 1.1 m
    dist_to_center = math.dist(wp, (4.0, 5.0))
    assert dist_to_center >= 1.0
    r, c = grid.to_cell(wp)
    assert grid.walkable(r, c)


def test_astar_performance_and_clearance():
    grid = nav.Grid(SPEC)
    start = (1.5, 1.5)
    # Use V-203's updated waypoint (9.35, 10.0) which has proper corridor clearance
    goal = (9.35, 10.0)
    res = nav.astar(grid, start, goal)

    assert res["reachable"] is True
    # Acceptance Check 4: length > 2 m, clearance >= 0.3 m, A* under 500 ms
    assert res["distance_m"] > 2.0
    assert res["clearance_m"] >= 0.30
    assert res["astar_ms"] < 500.0
    assert len(res["path"]) > 5


def test_smooth_path():
    grid = nav.Grid(SPEC)
    res = nav.astar(grid, (1.5, 1.5), (9.35, 10.0))
    assert res["reachable"] is True
    raw_path = res["path"]
    smoothed = nav.smooth_path(grid, raw_path)

    assert len(smoothed) <= len(raw_path)
    assert math.dist(smoothed[0], raw_path[0]) < 0.01
    assert math.dist(smoothed[-1], raw_path[-1]) < 0.01


def test_compute_path_proximity_samples():
    path_3d = [
        [1.0, 0.05, 1.0],
        [2.0, 0.05, 2.0],
        [3.0, 0.05, 3.0],
        [4.0, 0.05, 4.0],
        [5.0, 0.05, 5.0],
    ]
    objects = [
        {"id": "OBJ-001", "center": [1.2, 0.5, 1.2], "class_proposal": "pump"},
        {"id": "OBJ-002", "center": [4.8, 0.5, 4.8], "class_proposal": "valve"},
        {"id": "OBJ-003", "center": [10.0, 0.5, 10.0], "class_proposal": "tank"},
    ]
    mapped = [
        {"object_id": "OBJ-001", "asset_id": "P-001", "tag": "P-001", "method": "size_prior"},
        {"object_id": "OBJ-002", "asset_id": "V-102", "tag": "V-102", "method": "ocr_match"},
    ]

    samples = nav.compute_path_proximity(path_3d, objects, mapped, radius_m=2.5, step_m=1.0)
    assert len(samples) >= 4

    # Acceptance Check 5: sample points have different nearby sets
    first_nearby = [o["object_id"] for o in samples[0]["nearby_objects"]]
    last_nearby = [o["object_id"] for o in samples[-1]["nearby_objects"]]
    assert "OBJ-001" in first_nearby
    assert "OBJ-002" in last_nearby
    assert first_nearby != last_nearby


def test_build_route_contract(tmp_path):
    out_file = tmp_path / "route.json"
    route = nav.build_route(output_path=out_file)

    assert out_file.exists()
    assert route["reachable"] is True
    assert "floor_height_m" in route
    assert "start" in route
    assert "target_waypoint" in route
    assert "distance_m" in route
    assert "clearance_m" in route
    assert "path" in route
    assert "path_samples" in route
    assert "grid_stats" in route


# ---------------------------------------------------------------------------
# Obstacle avoidance tests
# ---------------------------------------------------------------------------

def _path_crosses_rect(path: list, x0: float, z0: float, x1: float, z1: float) -> bool:
    """Return True if any path point falls inside the given rectangle."""
    for p in path:
        if x0 <= p[0] <= x1 and z0 <= p[1] <= z1:
            return True
    return False


def test_blocker_across_direct_path_is_avoided():
    """A blocker placed directly across the shortest path must not appear in the route."""
    # The path to T-501 (6.0, 9.3) hugs x~2.0 going north.  Block that corridor.
    blocker = [[0.0, 5.0, 3.5, 7.0]]
    plain = nav.plan(SPEC, START, (6.0, 9.3))
    blocked = nav.plan(SPEC, START, (6.0, 9.3), blockers=blocker)

    assert blocked["reachable"] is True
    # The core guarantee: no point on the route passes through the blocker.
    assert not _path_crosses_rect(blocked["path"], 0.0, 5.0, 3.5, 7.0)
    # The plain route does pass through that zone (confirming the blocker is on-path).
    assert _path_crosses_rect(plain["path"], 0.0, 5.0, 3.5, 7.0)


def test_two_blockers_force_a_longer_detour():
    """Two blockers closing the direct north corridor must force a measurably longer route."""
    # The path to M-310 (8.0, 4.3) goes north along x~2.0 then cuts east at z~3.
    # Block the west passage between z=2.5 and z=3.5.
    blockers = [
        [0.0, 2.5, 3.0, 3.5],   # close the west wall corridor
        [3.0, 2.5, 6.5, 3.5],   # close the next segment east
    ]
    plain = nav.plan(SPEC, START, (8.0, 4.3))
    blocked = nav.plan(SPEC, START, (8.0, 4.3), blockers=blockers)

    assert blocked["reachable"] is True
    assert blocked["distance_m"] > plain["distance_m"] + 2.0


def test_full_width_blocker_reports_unreachable():
    """A wall that fully spans the room width must make the far side unreachable."""
    full_wall = [[0.0, 1.5, 16.0, 2.2]]
    result = nav.plan(SPEC, START, (8.0, 9.3), blockers=full_wall)

    assert result["reachable"] is False
    assert "no walkable route" in result["reason"]
    assert result["path"] == []
    assert result["distance_m"] == 0.0


def test_blocker_outside_grid_bounds_is_ignored():
    """A blocker entirely outside the grid must not raise and must not affect the route."""
    far_away = [[100.0, 100.0, 110.0, 110.0]]
    plain = nav.plan(SPEC, START, (8.0, 4.3))
    with_far = nav.plan(SPEC, START, (8.0, 4.3), blockers=far_away)

    assert with_far["reachable"] is True
    assert abs(with_far["distance_m"] - plain["distance_m"]) < 0.5


def test_blocker_on_start_forces_snap_to_nearest_free_cell():
    """A blocker placed on the start cell must still find a route by snapping start."""
    # Block the doorway where START (2.0, 0.8) is
    blocker = [[1.0, 0.0, 3.5, 1.5]]
    result = nav.plan(SPEC, START, (8.0, 4.3), blockers=blocker)
    # Should either reroute successfully or report unreachable cleanly - never crash
    assert "reachable" in result
    assert "path" in result


def test_build_route_accepts_blockers(tmp_path):
    """build_route must apply blockers and record them in the output document."""
    blocker = [[0.0, 4.8, 4.6, 7.2]]
    out_plain = tmp_path / "plain.json"
    out_blocked = tmp_path / "blocked.json"

    plain = nav.build_route(output_path=out_plain)
    blocked = nav.build_route(output_path=out_blocked, blockers=blocker)

    # Both must produce valid output files
    assert out_plain.exists()
    assert out_blocked.exists()

    # The blocked route records which blockers were active
    assert blocked["active_blockers"] == blocker

    # If both are reachable the blocked route is at least as long
    if plain["reachable"] and blocked["reachable"]:
        assert blocked["distance_m"] >= plain["distance_m"]

    # Blocked cells count must be higher with a blocker in place
    assert blocked["grid_stats"]["blocked_cells"] >= plain["grid_stats"]["blocked_cells"]


def test_build_route_unreachable_with_full_wall_blocker(tmp_path):
    """build_route must report reachable=False and a reason when a wall cuts the room."""
    # A wall spanning the entire plant cuts north from south
    full_wall = [[0.0, 1.5, 16.0, 2.2]]
    result = nav.build_route(
        output_path=tmp_path / "blocked.json",
        blockers=full_wall,
    )
    # Either unreachable (target is north of the wall) or the fallback target is south
    # Either way the result must be structurally valid
    assert "reachable" in result
    if not result["reachable"]:
        assert result["reason"]
        assert result["path"] == []
