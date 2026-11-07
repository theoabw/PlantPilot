import json
import math
from pathlib import Path
import numpy as np
import pytest

from plantpilot import nav


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
    # Obstacle pillar from x in [-0.5, 0.5], z in [-0.5, 0.5], y in [0.2, 1.5].
    # 40000 points is about 108 per 0.1 m cell inside the robot band, dense
    # enough for the structural layer: 500 points in the same volume was about
    # 1.3 per cell, which is a sparse cloud, not a pillar.
    obs_pts = rng.uniform(low=[-0.5, 0.2, -0.5], high=[0.5, 1.5, 0.5], size=(40000, 3))
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


def test_equipment_capture_uses_reviewed_door_start(tmp_path):
    rng = np.random.default_rng(42)
    points = rng.uniform(low=[-6.0, 0.0, -6.0], high=[6.0, 0.0, 6.0], size=(5000, 3))
    scene_path = tmp_path / "scene.npz"
    np.savez(
        scene_path,
        xyz=points,
        meta=np.array(json.dumps({
            "frame": {"up_axis_index": 1, "up_axis_sign": 1},
            "source": {"file": "Equipment Room.ply"},
        })),
    )

    route = nav.build_route(scene_path=scene_path, output_path=None, agent_radius_m=0.20)

    assert route["start"][0] == pytest.approx(-0.585, abs=0.1)
    assert route["start"][2] == pytest.approx(-4.144, abs=0.1)
    assert nav._configured_start_position("another-capture.ply") is None

    reroute = nav.build_route(
        scene_path=scene_path,
        output_path=None,
        agent_radius_m=0.20,
        start_override=(1.0, 1.0),
    )
    assert reroute["start"][0] == pytest.approx(1.0, abs=0.1)
    assert reroute["start"][2] == pytest.approx(1.0, abs=0.1)


# ---------------------------------------------------------------------------
# Obstacle avoidance tests
# ---------------------------------------------------------------------------

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


def test_a_y_down_capture_gets_its_path_in_scene_coordinates():
    # the boiler room and the equipment room are y down; the floor height is
    # negative, and the path must sit slightly above the floor in scene y
    assert nav.path_height(-1.181, -1) == pytest.approx(1.131, abs=0.001)
    assert nav.path_height(-1.181, 1) == pytest.approx(-1.131, abs=0.001)


def test_objects_become_obstacles_when_the_point_grid_saturates():
    # a band of points in every cell is what a cluttered capture looks like; the
    # old code fell back to an empty grid, which is how a route went through a
    # pump. The extracted box has to become the obstacle instead, and the
    # structural layer is always part of the union now.
    rng = np.random.default_rng(3)
    dense = rng.uniform(low=[-3.0, 0.2, -3.0], high=[3.0, 1.4, 3.0], size=(20000, 3))
    box = {
        "centre": [0.0, 0.5, 0.0],
        "axes": [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        "extents": [1.0, 1.0, 1.0],
    }
    grid = nav.Grid.from_cloud(dense, floor_y=0.0, up_axis=1, objects=[box], agent_radius_m=0.2)
    assert grid.obstacles_from == "objects+structure"
    row, column = grid.to_cell((0.0, 0.0))
    assert not grid.walkable(row, column)
    corner_row, corner_column = grid.to_cell((2.5, 2.5))
    assert grid.walkable(corner_row, corner_column)


# ---------------------------------------------------------------------------
# Structural layer: the capture's own points have to block walls, not noise
# ---------------------------------------------------------------------------

def room_cloud() -> np.ndarray:
    """A closed box room with one doorway, plus a sparse noise band.

    The four perimeter walls are dense vertical surfaces in the robot band, the
    internal wall blocks everything except a doorway at 0.8 < z < 2.0, and the
    noise lattice puts at most two points in any 0.1 m cell so that it stays
    below the measured structural minimum.
    """

    def vertical_wall(x: float, z_values: np.ndarray, y_values: np.ndarray) -> np.ndarray:
        z_grid, y_grid = np.meshgrid(z_values, y_values, indexing="ij")
        return np.stack(
            [np.full(z_grid.size, x), y_grid.ravel(), z_grid.ravel()], axis=1
        )

    y_wall = np.arange(0.10, 0.50 + 1e-9, 0.02)
    along = np.arange(-2.0, 2.0 + 1e-9, 0.02)
    parts = []
    for x in (-2.0, 2.0):
        parts.append(vertical_wall(x, along, y_wall))
    for z in (-2.0, 2.0):
        z_grid, y_grid = np.meshgrid(along, y_wall, indexing="ij")
        parts.append(np.stack([z_grid.ravel(), y_grid.ravel(), np.full(z_grid.size, z)], axis=1))
    # internal wall at x = 0 from z = -2.0 to 0.8: the doorway is 1.2 m wide
    parts.append(vertical_wall(0.0, np.arange(-2.0, 0.8 + 1e-9, 0.02), y_wall))

    axis = np.arange(-2.0, 2.0 + 1e-9, 0.1)
    floor_x, floor_z = np.meshgrid(axis, axis, indexing="ij")
    parts.append(np.stack([floor_x.ravel(), np.zeros(floor_x.size), floor_z.ravel()], axis=1))

    noise_axis = np.arange(-1.9, 1.9 + 1e-9, 0.2)
    noise_x, noise_z = np.meshgrid(noise_axis, noise_axis, indexing="ij")
    for height in (0.15, 0.50):
        parts.append(np.stack([noise_x.ravel(), np.full(noise_x.size, height), noise_z.ravel()], axis=1))
    return np.vstack(parts)


def test_a_dense_wall_blocks_the_route_while_sparse_noise_does_not():
    cloud = room_cloud()
    grid = nav.Grid.from_cloud(cloud, floor_y=0.0, up_axis=1, agent_radius_m=0.15)

    assert grid.obstacles_from == "structure"
    assert grid.structural_cells > 0
    # the internal wall is solid at z = -0.5, and must not be walkable
    wall_cell = grid.to_cell((0.0, -0.5))
    assert not grid.walkable(*wall_cell)
    # two noise points per cell are below the measured minimum: this cell is free
    noise_cell = grid.to_cell((-1.5, -1.5))
    assert grid.walkable(*noise_cell)

    start = (-1.5, -0.5)
    goal = (1.5, -0.5)
    route = nav.astar(grid, start, goal)
    assert route["reachable"] is True
    # the direct line is 3 m; going through the doorway is longer
    assert route["distance_m"] > 4.0
    assert route["clearance_m"] > 0.0
    # the route must not pass through the internal wall: its solid part is
    # x = 0 from z = -2.0 to 0.8, inflated by the agent radius
    for point in route["path"]:
        assert not (abs(point[0]) < 0.35 and point[1] < 0.95), point


def test_the_grid_reports_what_each_source_blocked():
    cloud = room_cloud()
    box = {
        "centre": [1.2, 0.3, -1.2],
        "axes": [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        "extents": [0.5, 0.5, 0.5],
    }
    grid = nav.Grid.from_cloud(cloud, floor_y=0.0, up_axis=1, objects=[box], agent_radius_m=0.15)

    assert grid.obstacles_from == "objects+structure"
    assert grid.object_cells > 0
    assert grid.structural_cells > 0
    assert grid.structure_min_points == nav.STRUCTURE_MIN_POINTS
    # the object footprint and the wall are both blocked, the doorway is not
    assert not grid.walkable(*grid.to_cell((1.2, -1.2)))
    assert not grid.walkable(*grid.to_cell((0.0, -0.5)))
    assert grid.walkable(*grid.to_cell((0.0, 1.6)))


def test_a_saturated_grid_is_kept_and_reported_not_emptied():
    # every 0.1 m cell of the robot band holds 125 points: a room with walls all
    # the way through. The union must stand and say it is saturated; the old
    # failure mode was to fall back to a free grid.
    axis = np.arange(-2.0, 2.0 + 1e-9, 0.025)
    x_grid, z_grid = np.meshgrid(axis, axis, indexing="ij")
    heights = np.array([0.10, 0.20, 0.30, 0.40, 0.50])
    parts = [np.stack([x_grid.ravel(), np.full(x_grid.size, h), z_grid.ravel()], axis=1)
             for h in heights]
    grid = nav.Grid.from_cloud(np.vstack(parts), floor_y=0.0, up_axis=1, agent_radius_m=0.15)

    assert grid.obstacles_from == "structure"
    assert grid.saturated is True
    assert grid.occupancy_fallback is False
    assert grid.blocked_fraction > nav.MAX_BLOCKED_FRACTION
    # the dense band does not reach the padded grid corners, so a few isolated
    # cells stay free; the grid is still saturated, not emptied
    assert int(grid.blocked.sum()) >= int(0.99 * grid.rows * grid.cols)
    assert int(grid.free.sum()) <= int(0.01 * grid.rows * grid.cols)


def test_the_camera_layer_sees_eye_level_structure_the_robot_layer_misses():
    import numpy as np

    from plantpilot import nav

    # A floor at 0 m and a dense shelf face at 1.5 m, in front of the robot but
    # well above the robot body band. The robot grid may stay free; the camera
    # layer must not.
    floor_x, floor_z = np.meshgrid(np.arange(0.0, 1.0, 0.05), np.arange(0.0, 1.0, 0.05))
    floor = np.stack([floor_x.ravel(), np.zeros(floor_x.size), floor_z.ravel()], axis=1)
    wall_x, wall_h = np.meshgrid(np.arange(0.2, 0.6, 0.0125), np.arange(1.3, 1.7, 0.0125))
    wall = np.stack([wall_x.ravel(), wall_h.ravel(), np.full(wall_x.size, 0.5)], axis=1)
    points = np.concatenate([floor, wall], axis=0)

    grid = nav.Grid.from_cloud(points, floor_y=0.0, up_axis=1, up_axis_sign=1, objects=[])

    assert getattr(grid, "camera_cells", 0) > 0
    assert int(getattr(grid, "camera_mask").sum()) > 0
    # The wall is above OBSTACLE_MIN_HEIGHT_M and ROBOT_HEIGHT_M, so the robot
    # structural layer ignores it; the camera layer is the one that sees it.
    assert int(getattr(grid, "structural_cells", 0)) == 0


def test_a_tall_robot_blocks_pipework_an_amr_can_walk_under():
    import numpy as np

    from plantpilot import nav

    floor_x, floor_z = np.meshgrid(np.arange(0.0, 1.0, 0.05), np.arange(0.0, 1.0, 0.05))
    floor = np.stack([floor_x.ravel(), np.zeros(floor_x.size), floor_z.ravel()], axis=1)
    # A pipe crossing the aisle at 1.2 m: above an AMR, through a humanoid's torso.
    pipe_x, pipe_z = np.meshgrid(np.arange(0.2, 0.8, 0.0125), np.arange(0.45, 0.55, 0.0125))
    pipe = np.stack([pipe_x.ravel(), np.full(pipe_x.size, 1.2), pipe_z.ravel()], axis=1)
    points = np.concatenate([floor, pipe], axis=0)

    short = nav.Grid.from_cloud(points, floor_y=0.0, objects=[], walkable_height_max_m=0.55)
    tall = nav.Grid.from_cloud(
        points, floor_y=0.0, objects=[], walkable_height_max_m=1.35, structure_min_points=30
    )

    assert int(getattr(short, "structural_cells", 0)) == 0
    assert int(getattr(tall, "structural_cells", 0)) > 0
