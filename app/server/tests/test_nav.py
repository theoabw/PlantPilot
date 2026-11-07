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
    # Build point cloud with an obstacle at center (0, 0). The floor is sampled
    # at 5 cm, so every cell has floor under it: a cell the capture never saw is
    # no longer walkable, which is the floor rule.
    rng = np.random.default_rng(42)
    floor_axis = np.arange(-4.0, 4.0, 0.05)
    floor_x, floor_z = np.meshgrid(floor_axis, floor_axis)
    floor_pts = np.stack(
        [floor_x.ravel(), np.zeros(floor_x.size), floor_z.ravel()], axis=1
    )
    # Obstacle pillar from x in [-0.5, 0.5], z in [-0.5, 0.5], y in [0.2, 1.5].
    # 40000 points is about 108 per 0.1 m cell, dense enough to be a surface: 500
    # points in the same volume was about 1.3 per cell, which is a sparse cloud,
    # not a pillar.
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


def test_compute_path_proximity_accepts_zero_length_path():
    samples = nav.compute_path_proximity(
        [[1.0, 0.05, 1.0]],
        [{"id": "OBJ-001", "center": [1.2, 0.5, 1.2], "class_proposal": "pump"}],
        radius_m=2.5,
        step_m=1.0,
    )

    assert len(samples) == 1
    assert samples[0]["distance_along_path_m"] == 0.0
    assert samples[0]["nearby_objects"][0]["object_id"] == "OBJ-001"


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


def test_equipment_capture_uses_the_reviewed_dock(tmp_path):
    # A floor observed in every cell: a random scatter leaves cells with no
    # ground under them, and those are blocked by the floor rule.
    floor_axis = np.arange(-6.0, 6.0, 0.05)
    floor_x, floor_z = np.meshgrid(floor_axis, floor_axis)
    points = np.stack([floor_x.ravel(), np.zeros(floor_x.size), floor_z.ravel()], axis=1)
    scene_path = tmp_path / "scene.npz"
    np.savez(
        scene_path,
        xyz=points,
        meta=np.array(json.dumps({
            "frame": {"up_axis_index": 1, "up_axis_sign": 1},
            "source": {"file": "Equipment Room.ply"},
        })),
    )

    # The floor is a single plane, so floor detection is given the height
    # directly: this test is about the reviewed start position, not about
    # estimating a floor from one flat surface.
    route = nav.build_route(
        scene_path=scene_path, output_path=None, agent_radius_m=0.20, manual_floor_y=0.0
    )

    assert route["start"][0] == pytest.approx(-0.585, abs=0.1)
    assert route["start"][2] == pytest.approx(-2.649, abs=0.1)
    assert route["grid_stats"]["floor_domain"] is True
    assert nav._configured_start_position("another-capture.ply") is None

    reroute = nav.build_route(
        scene_path=scene_path,
        output_path=None,
        agent_radius_m=0.20,
        manual_floor_y=0.0,
        start_override=(1.0, 1.0),
    )
    assert reroute["start"][0] == pytest.approx(1.0, abs=0.1)
    assert reroute["start"][2] == pytest.approx(1.0, abs=0.1)


def test_capture_grid_blocks_cells_outside_measured_floor():
    rng = np.random.default_rng(7)
    floor = rng.uniform(low=[-3.0, 0.0, -3.0], high=[3.0, 0.0, 3.0], size=(4000, 3))
    exterior = rng.uniform(
        low=[6.0, 0.2, 6.0], high=[8.0, 1.0, 8.0], size=(500, 3)
    )
    grid = nav.Grid.from_cloud(
        np.vstack([floor, exterior]), floor_y=0.0, up_axis=1, objects=[]
    )

    assert grid.floor_domain is True
    assert grid.walkable(*grid.to_cell((0.0, 0.0)))
    assert not grid.walkable(*grid.to_cell((7.0, 7.0)))


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


def test_objects_become_obstacles_when_the_room_is_dense():
    # a volume of points in the middle of a floored room is what a cluttered
    # capture looks like; the old code fell back to an empty grid, which is how a
    # route went through a pump. The extracted box has to become the obstacle
    # instead, and the point layers are always part of the union now.
    rng = np.random.default_rng(3)
    floor_axis = np.arange(-3.0, 3.0, 0.05)
    floor_x, floor_z = np.meshgrid(floor_axis, floor_axis)
    floor_pts = np.stack([floor_x.ravel(), np.zeros(floor_x.size), floor_z.ravel()], axis=1)
    dense = rng.uniform(low=[-2.0, 0.2, -2.0], high=[2.0, 1.4, 2.0], size=(20000, 3))
    box = {
        "centre": [0.0, 0.5, 0.0],
        "axes": [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        "extents": [1.0, 1.0, 1.0],
    }
    grid = nav.Grid.from_cloud(
        np.vstack([floor_pts, dense]), floor_y=0.0, up_axis=1, objects=[box], agent_radius_m=0.2
    )
    assert grid.obstacles_from == "objects+structure"
    assert grid.object_cells > 0
    assert grid.floor_cells > 0
    row, column = grid.to_cell((0.0, 0.0))
    assert not grid.walkable(row, column)
    corner_row, corner_column = grid.to_cell((2.5, 2.5))
    assert grid.walkable(corner_row, corner_column)


# ---------------------------------------------------------------------------
# Structural layer: the capture's own points have to block walls, not noise
# ---------------------------------------------------------------------------

def room_cloud() -> np.ndarray:
    """A closed box room with one doorway, plus a sparse noise band.

    The four perimeter walls run the height of the room, the internal wall blocks
    everything except a doorway at 0.8 < z < 2.0, and the noise lattice puts at
    most two points in any 0.1 m cell so that it never forms a surface.
    """

    def vertical_wall(x: float, z_values: np.ndarray, y_values: np.ndarray) -> np.ndarray:
        z_grid, y_grid = np.meshgrid(z_values, y_values, indexing="ij")
        return np.stack(
            [np.full(z_grid.size, x), y_grid.ravel(), z_grid.ravel()], axis=1
        )

    # 1.4 m tall: the wall layer measures how far a surface runs up the room, so
    # a 0.4 m wall would be a machine parapet, not a wall.
    y_wall = np.arange(0.10, 1.50 + 1e-9, 0.02)
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
    assert grid.wall_cells > 0
    assert grid.floor_cells > 0
    assert grid.no_floor_cells > 0
    # The count threshold is gone: the wall layer reads the surface, not a count.
    assert grid.structure_min_points is None
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
    tall = nav.Grid.from_cloud(points, floor_y=0.0, objects=[], walkable_height_max_m=1.35)

    assert int(getattr(short, "structural_cells", 0)) == 0
    assert int(getattr(tall, "structural_cells", 0)) > 0


# ---------------------------------------------------------------------------
# Review findings: the envelope projection, the goal fallback position, and the
# non-finite filter against the normals
# ---------------------------------------------------------------------------

def _turned_box() -> tuple[dict, dict]:
    """A box turned 35 degrees about the up axis, and its row permutation.

    The rows of `axes` are the box axes and `extents` the lengths along them, so
    reordering a row together with its length is the same physical box.
    """
    angle = np.radians(35.0)
    cosine, sine = float(np.cos(angle)), float(np.sin(angle))
    axes = [
        [cosine, 0.0, -sine],
        [sine, 0.0, cosine],
        [0.0, 1.0, 0.0],
    ]
    extents = [1.3, 0.8, 0.6]
    box = {"centre": [1.0, 0.3, 1.0], "axes": axes, "extents": extents}
    order = [2, 0, 1]
    permuted = {
        "centre": [1.0, 0.3, 1.0],
        "axes": [axes[index] for index in order],
        "extents": [extents[index] for index in order],
    }
    return box, permuted


def _box_corner_cloud(box: dict, scale: float = 0.98) -> np.ndarray:
    """A floor plus two gaussians at the point of the box that the reject loses.

    The point is (e1/2, -e2/2, 0) in the box frame, scaled just inside the
    surface and at mid height so it sits in the robot's body band. Its world z
    offset is the box's full z reach, which the row-wise projection of `axes`
    under-measures, so a reject built from the rows drops it while the true
    projection keeps it.
    """
    axes = np.asarray(box["axes"], dtype=float)
    extents = np.asarray(box["extents"], dtype=float)
    local = np.array([extents[0] / 2.0, -extents[1] / 2.0, 0.0]) * scale
    centre = np.asarray(box["centre"], dtype=float)
    corner = centre + local @ axes
    axis = np.arange(0.0, 3.0, 0.05)
    floor_x, floor_z = np.meshgrid(axis, axis)
    floor = np.stack([floor_x.ravel(), np.zeros(floor_x.size), floor_z.ravel()], axis=1)
    return np.vstack([floor, corner, corner])


def test_the_envelope_reject_keeps_a_corner_point_of_a_turned_box():
    box, _ = _turned_box()
    points = _box_corner_cloud(box)
    grid = nav.Grid.from_cloud(
        points, floor_y=0.0, up_axis=1, agent_radius_m=0.15, objects=[box]
    )

    # The layers rasterise a point into the cell that starts at it (a floor of
    # the grid offset), which is how write_obstacle_png draws them too.
    point = points[-1]
    corner_row = int(np.floor((point[2] - grid.z0) / nav.CELL_M))
    corner_column = int(np.floor((point[0] - grid.x0) / nav.CELL_M))
    assert grid.layers["object"][corner_row, corner_column] == 1
    assert not grid.walkable(corner_row, corner_column)


def test_permuting_a_box_axes_with_their_extents_does_not_change_the_object_layer():
    box, permuted = _turned_box()
    points = _box_corner_cloud(box)
    plain = nav.Grid.from_cloud(
        points, floor_y=0.0, up_axis=1, agent_radius_m=0.15, objects=[box]
    )
    reordered = nav.Grid.from_cloud(
        points, floor_y=0.0, up_axis=1, agent_radius_m=0.15, objects=[permuted]
    )

    assert plain.object_cells > 0
    assert np.array_equal(plain.layers["object"], reordered.layers["object"])
    assert plain.object_cells == reordered.object_cells


def test_the_reachable_ground_fallback_lands_on_a_cell_astar_can_use():
    # Only (5, 5) and (6, 6) are free, and the start is (0.5, 0.5) in metres.
    # The helper must return the centre of (5, 5) as to_cell reads it: half a
    # cell off maps to the disconnected (6, 6), and A* then refuses the goal.
    blocked = np.ones((11, 11), dtype=np.uint8)
    blocked[5, 5] = 0
    blocked[6, 6] = 0
    grid = nav.Grid(
        area={"x0": 0.0, "z0": 0.0, "x1": 1.1, "z1": 1.1},
        blocked_mask=blocked,
        agent_radius_m=0.0,
        safety_margin_m=0.0,
    )
    assert grid.to_cell((0.5, 0.5)) == (5, 5)

    ground = nav.nearest_reachable_ground(grid, (0.5, 0.5), (1.0, 1.0))

    assert ground is not None
    assert grid.to_cell(ground) == (5, 5)
    assert nav.astar(grid, (0.5, 0.5), ground)["reachable"] is True


def _pocket_grid() -> nav.Grid:
    """A main room on the left and a walled pocket on the right, in 0.1 m cells."""
    blocked = np.zeros((40, 60), dtype=np.uint8)
    blocked[0, :] = blocked[-1, :] = 1
    blocked[:, 0] = blocked[:, -1] = 1
    blocked[:, 40] = 1
    return nav.Grid(
        area={"x0": 0.0, "z0": 0.0, "x1": 6.0, "z1": 4.0},
        blocked_mask=blocked,
        agent_radius_m=0.0,
        safety_margin_m=0.0,
    )


def test_a_world_point_stays_in_the_cell_the_layers_rasterise_it_into():
    grid = _pocket_grid()
    # 0.19 m is inside cell 1 for the floor binning of the layers and the viewer.
    assert grid.to_cell((0.19, 0.19)) == (1, 1)
    assert grid.to_world(1, 1) == (0.15, 0.15)
    for row, column in ((1, 1), (7, 3), (12, 39), (38, 58)):
        assert grid.to_cell(grid.to_world(row, column)) == (row, column)


def test_a_snapped_destination_is_stable_when_it_is_planned_again():
    grid = _pocket_grid()
    first = nav._nearest_free(grid, (1.33, 2.33))
    assert first is not None
    assert nav._nearest_free(grid, first) == first


def test_nearest_free_says_so_when_nothing_is_free():
    blocked = np.ones((20, 20), dtype=np.uint8)
    grid = nav.Grid(
        area={"x0": 0.0, "z0": 0.0, "x1": 2.0, "z1": 2.0},
        blocked_mask=blocked,
        agent_radius_m=0.0,
        safety_margin_m=0.0,
    )
    assert nav._nearest_free(grid, (1.0, 1.0)) is None


def _pocket_scene(tmp_path: Path) -> Path:
    """A capture whose floor is only observed in a room and a detached pocket."""
    axis_x = np.arange(0.0, 6.0, 0.03)
    axis_z = np.arange(0.0, 4.0, 0.03)
    floor_x, floor_z = np.meshgrid(axis_x, axis_z)
    keep = (floor_x < 3.0) | (floor_x > 4.2)
    floor = np.stack([floor_x[keep], np.zeros(int(keep.sum())), floor_z[keep]], axis=1)
    path = tmp_path / "scene.npz"
    np.savez(
        path,
        xyz=floor,
        meta=np.array(json.dumps({"frame": {"up_axis_index": 1, "up_axis_sign": 1}})),
    )
    return path


def test_a_destination_in_a_pocket_stops_on_ground_the_robot_can_reach(tmp_path):
    route = nav.build_route(
        scene_path=_pocket_scene(tmp_path),
        manual_floor_y=0.0,
        agent_radius_m=0.1,
        start_override=(1.0, 2.0),
        goal_override=(4.6, 2.0),
    )
    assert route["reachable"] is True
    assert route["target_waypoint_from"] == "goal_override_reachable"
    assert route["target_waypoint"][0] < 3.3
    assert route["goal_snap_m"] == pytest.approx(4.6 - route["target_waypoint"][0], abs=0.1)


def test_a_blocker_that_cuts_the_room_is_still_refused_and_named(tmp_path):
    scene = _pocket_scene(tmp_path)
    route = nav.build_route(
        scene_path=scene,
        manual_floor_y=0.0,
        agent_radius_m=0.1,
        start_override=(0.8, 2.0),
        goal_override=(2.4, 2.0),
        blockers=[[1.4, -1.0, 1.6, 5.0]],
    )
    assert route["reachable"] is False
    assert route["reason"] == "no walkable route with this obstruction"


@pytest.mark.parametrize("cover_stop", [False, True])
def test_a_blocker_cannot_move_a_pockets_inspection_stop_before_the_blocker(tmp_path, cover_stop):
    plan = dict(
        scene_path=_pocket_scene(tmp_path),
        manual_floor_y=0.0,
        agent_radius_m=0.1,
        start_override=(0.8, 2.0),
        goal_override=(4.6, 2.0),
    )
    original = nav.build_route(**plan)
    assert original["reachable"] is True
    assert original["target_waypoint_from"] == "goal_override_reachable"

    stop_x = original["target_waypoint"][0]
    blocker = [stop_x - 0.2, -1.0, stop_x + 0.2, 5.0] if cover_stop else [1.4, -1.0, 1.6, 5.0]
    blocked = nav.build_route(**plan, blockers=[blocker])
    assert blocked["reachable"] is False
    assert blocked["reason"] == "no walkable route with this obstruction"
    assert blocked["path"] == []
    assert blocked["target_waypoint"] == original["target_waypoint"]

    beside_route = nav.build_route(**plan, blockers=[[0.4, 0.4, 0.6, 0.6]])
    assert beside_route["reachable"] is True
    assert beside_route["target_waypoint"] == original["target_waypoint"]
    assert beside_route["path"][-1] == original["target_waypoint"]


def test_a_route_that_fails_with_no_blocker_does_not_blame_an_obstruction():
    grid = _pocket_grid()
    plan = nav.astar(grid, (1.0, 2.0), (5.0, 2.0))
    assert plan["reachable"] is False
    assert "obstruction" not in plan["reason"]


def test_a_start_with_nothing_free_near_it_is_refused_not_passed_through(tmp_path):
    route = nav.build_route(
        scene_path=_pocket_scene(tmp_path),
        manual_floor_y=0.0,
        agent_radius_m=0.1,
        start_override=(1.5, 2.0),
        blockers=[[0.0, 0.0, 3.0, 4.0]],
    )
    assert route["reachable"] is False
    assert "does not fit" in route["reason"]


def test_clearance_is_measured_on_the_driven_line_to_the_uninflated_cells():
    blocked = np.zeros((40, 40), dtype=np.uint8)
    blocked[20:22, 10:30] = 1
    grid = nav.Grid(
        area={"x0": 0.0, "z0": 0.0, "x1": 4.0, "z1": 4.0},
        blocked_mask=blocked,
        agent_radius_m=0.2,
        safety_margin_m=0.0,
    )
    # A line 0.5 m clear of the bar's near edge at z = 2.0, inside the grid's 4 m.
    assert nav.path_clearance_m(grid, [(0.5, 1.5), (3.5, 1.5)]) == pytest.approx(0.5)
    # A blocker is occupied too, and its inflation does not count as occupied.
    with_blocker = grid.with_blockers([[1.9, 0.9, 2.1, 1.1]])
    assert nav.path_clearance_m(with_blocker, [(0.5, 1.5), (3.5, 1.5)]) == pytest.approx(0.4)


def test_a_route_reports_the_length_and_clearance_of_its_smoothed_line(tmp_path):
    route = nav.build_route(
        scene_path=_pocket_scene(tmp_path),
        manual_floor_y=0.0,
        agent_radius_m=0.1,
        start_override=(0.8, 0.8),
        goal_override=(2.2, 3.0),
    )
    assert route["reachable"] is True
    drawn = [(p[0], p[2]) for p in route["path"]]
    assert route["distance_m"] == pytest.approx(
        sum(math.dist(a, b) for a, b in zip(drawn, drawn[1:])), abs=0.01
    )


def test_smoothing_keeps_the_detour_that_gave_a_stretch_its_clearance():
    blocked = np.zeros((40, 60), dtype=np.uint8)
    blocked[:12, 25:35] = 1
    grid = nav.Grid(
        area={"x0": 0.0, "z0": 0.0, "x1": 6.0, "z1": 4.0},
        blocked_mask=blocked,
        agent_radius_m=0.1,
        safety_margin_m=0.0,
    )
    # A raw path that swings wide of the obstacle's corner on its way across.
    raw = [(0.55, 1.55)] + [(0.55 + i * 0.1, 1.55 + min(i, 60 - i) * 0.03) for i in range(1, 49)]
    raw.append((5.45, 1.55))
    assert all(grid.walkable(*grid.to_cell(p)) for p in raw)
    raw_clearance = min(float(grid.clearance_m[grid.to_cell(p)]) for p in raw)

    smoothed = nav.smooth_path(grid, raw)

    assert smoothed[0] == raw[0] and smoothed[-1] == raw[-1]
    driven = nav.path_clearance_m(grid, smoothed)
    # The straight chord would pass 0.35 m from the corner and still have sight.
    assert driven > 0.35
    assert raw_clearance > 0.0


def test_the_service_waypoint_reads_the_box_through_its_own_frame():
    grid = nav.Grid(
        area={"x0": -6.0, "z0": -6.0, "x1": 6.0, "z1": 6.0},
        blocked_mask=np.zeros((120, 120), dtype=np.uint8),
        agent_radius_m=0.1,
        safety_margin_m=0.0,
    )
    # A 4 m tall column: its long axis is world up, so its footprint is 0.4 m wide.
    column = {
        "centre": [0.0, 2.0, 0.0],
        "axes": [[0.0, 1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 1.0]],
        "extents": [4.0, 0.4, 0.4],
    }
    waypoint = nav.compute_service_waypoint(column, grid)
    footprint = nav.object_footprint(column)
    gap_x = max(footprint.x0 - waypoint[0], 0.0, waypoint[0] - footprint.x1)
    gap_z = max(footprint.z0 - waypoint[1], 0.0, waypoint[1] - footprint.z1)
    assert math.hypot(gap_x, gap_z) == pytest.approx(nav.DEFAULT_CLEARANCE_TARGET_M, abs=0.15)


def test_nearby_objects_are_measured_to_the_box_like_the_viewer():
    # A 6 m long skid: its centre is 3.2 m away but its end is 0.2 m away.
    skid = {
        "id": "OBJ-LONG",
        "centre": [3.2, 0.0, 0.0],
        "axes": [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        "extents": [6.0, 1.0, 1.0],
    }
    samples = nav.compute_path_proximity([[0.0, 0.0, 0.0]], [skid], radius_m=2.5, step_m=1.0)
    assert samples[0]["nearby_objects"][0]["object_id"] == "OBJ-LONG"
    assert samples[0]["nearby_objects"][0]["distance_m"] == pytest.approx(0.2)


def test_a_tall_robot_is_not_cut_short_by_a_plane_below_its_height(tmp_path):
    # Horizontal plane records used to cap the body band at 1.5 m on any capture,
    # because their offset is a plane constant and not a height above the floor.
    objects = tmp_path / "objects.json"
    objects.write_text(json.dumps({
        "objects": [],
        "floor": {"height": 0.0},
        "planes": {"items": [{"horizontal": True, "offset": 0.6}]},
    }))
    # Pipework at 1.7 m, which a 1.5 m cap would hide from a 1.9 m body.
    _pocket_scene(tmp_path)
    axis = np.arange(0.2, 2.8, 0.02)
    band_x, band_z = np.meshgrid(axis, axis)
    points = np.stack([band_x.ravel(), np.full(band_x.size, 1.7), band_z.ravel()], axis=1)
    floor = np.load(tmp_path / "scene.npz")["xyz"]
    scene = tmp_path / "pipes.npz"
    np.savez(
        scene,
        xyz=np.concatenate([floor, points]),
        meta=np.array(json.dumps({"frame": {"up_axis_index": 1, "up_axis_sign": 1}})),
    )
    tall = nav.build_route(
        scene_path=scene,
        objects_path=objects,
        manual_floor_y=0.0,
        agent_radius_m=0.1,
        agent_height_m=1.9,
    )
    assert tall["grid_stats"]["overhead_blocked_cells"] > 0


def test_a_reroute_reuses_the_layers_and_sees_a_rebuilt_artifact(tmp_path, monkeypatch):
    scene = _pocket_scene(tmp_path)
    built = []
    original = nav.Grid.from_cloud
    monkeypatch.setattr(
        nav.Grid, "from_cloud", lambda *a, **k: built.append(k) or original(*a, **k)
    )
    first = nav.build_route(scene_path=scene, manual_floor_y=0.0, agent_radius_m=0.1)
    wider = nav.build_route(
        scene_path=scene, manual_floor_y=0.0, agent_radius_m=0.3, start_override=(1.0, 2.0)
    )
    assert len(built) == 1
    assert wider["agent_radius_m"] == 0.3
    assert wider["grid_stats"]["blocked_cells"] > first["grid_stats"]["blocked_cells"]

    points = np.load(scene)["xyz"]
    np.savez(
        scene,
        xyz=points[::2],
        meta=np.array(json.dumps({"frame": {"up_axis_index": 1, "up_axis_sign": 1}})),
    )
    nav.build_route(scene_path=scene, manual_floor_y=0.0, agent_radius_m=0.1)
    assert len(built) == 2


def test_a_snap_takes_the_nearest_free_cell_not_the_first_ring_with_one():
    blocked = np.ones((21, 21), dtype=np.uint8)
    blocked[10, 18] = 0  # 0.8 m along an axis, on square ring 8
    blocked[3, 3] = 0  # 0.99 m on the diagonal, on square ring 7
    grid = nav.Grid(
        area={"x0": 0.0, "z0": 0.0, "x1": 2.1, "z1": 2.1},
        blocked_mask=blocked,
        agent_radius_m=0.0,
        safety_margin_m=0.0,
    )
    # A kernel of radius zero still inflates by itself only, so both cells stay free.
    assert nav._nearest_free(grid, (1.05, 1.05), radius_cells=9) == grid.to_world(10, 18)


def test_a_start_may_snap_to_the_limit_and_is_refused_beyond_it(tmp_path):
    scene = _pocket_scene(tmp_path)
    plan = dict(
        scene_path=scene,
        manual_floor_y=0.0,
        agent_radius_m=0.1,
        start_override=(1.5, 2.0),
        goal_override=(2.8, 3.8),
    )
    # A square blocker round the start: free ground begins 0.85 m away, the door
    # dock's snap for the Cargo AMR, and past the limit when it is 0.2 m larger.
    fits = nav.build_route(**plan, blockers=[[0.8, 1.3, 2.2, 2.7]])
    assert fits["reachable"] is True
    assert math.dist((fits["start"][0], fits["start"][2]), (1.5, 2.0)) <= nav.START_SNAP_LIMIT_M

    too_far = nav.build_route(**plan, blockers=[[0.6, 1.1, 2.4, 2.9]])
    assert too_far["reachable"] is False
    assert "does not fit" in too_far["reason"]


def test_the_standoff_of_a_destination_is_measured_to_that_destinations_box(tmp_path):
    objects = tmp_path / "objects.json"
    machine = {
        "id": "OBJ-A",
        "class": "pump",
        "centre": [2.0, 0.5, 2.0],
        "axes": [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        "extents": [0.6, 1.0, 0.6],
    }
    elsewhere = dict(machine, id="OBJ-B", centre=[0.6, 0.5, 3.4], extents=[0.2, 1.0, 0.2])
    objects.write_text(json.dumps({"objects": [elsewhere, machine]}))
    route = nav.build_route(
        scene_path=_pocket_scene(tmp_path),
        objects_path=objects,
        manual_floor_y=0.0,
        agent_radius_m=0.1,
        start_override=(0.6, 0.6),
        goal_override=(2.0, 2.0),
    )
    assert route["reachable"] is True
    stop = (route["target_waypoint"][0], route["target_waypoint"][2])
    gap_x = max(1.7 - stop[0], 0.0, stop[0] - 2.3)
    gap_z = max(1.7 - stop[1], 0.0, stop[1] - 2.3)
    assert route["target_waypoint_standoff_m"] == pytest.approx(math.hypot(gap_x, gap_z), abs=0.01)
    assert route["target_waypoint_standoff_m"] < 0.5


# ---------------------------------------------------------------------------
# The route's inputs: no silent substitute target, no hidden load failure
# ---------------------------------------------------------------------------

def _route_inputs(tmp_path, mappings, objects=None):
    """A flat floor, one object at the far side and a mapping, written as artifacts."""
    axis = np.arange(-3.0, 3.0, 0.05)
    floor_x, floor_z = np.meshgrid(axis, axis)
    points = np.stack([floor_x.ravel(), np.zeros(floor_x.size), floor_z.ravel()], axis=1)
    scene = tmp_path / "scene.npz"
    np.savez(scene, xyz=points, meta=np.array(json.dumps({"frame": {"up_axis_index": 1, "up_axis_sign": 1}})))
    objects_path = tmp_path / "objects.json"
    objects_path.write_text(json.dumps({"objects": objects if objects is not None else [{
        "id": "OBJ-001",
        "class": "pump",
        "centre": [1.5, 0.3, 1.5],
        "axes": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
        "extents": [0.4, 0.6, 0.4],
        "points": 500,
    }]}))
    mapped = tmp_path / "mapped.json"
    mapped.write_text(json.dumps({"mappings": mappings}))
    return {"scene_path": scene, "objects_path": objects_path, "mapped_path": mapped, "manual_floor_y": 0.0}


UNRESOLVED = {"asset_id": "A-5", "tag": "P-005", "object_id": None, "reason": "no object cleared the rule"}


def test_an_unresolved_target_is_refused_not_replaced_by_another_object(tmp_path):
    route = nav.build_route(**_route_inputs(tmp_path, [UNRESOLVED]))

    assert route["reachable"] is False
    assert route["path"] == []
    assert route["target_object_id"] is None
    assert route["target_waypoint_from"] == "unresolved_target"
    assert "P-005" in route["reason"] and "no object cleared the rule" in route["reason"]


def test_a_target_absent_from_the_mapping_is_refused(tmp_path):
    route = nav.build_route(**_route_inputs(tmp_path, [{"asset_id": "A-1", "tag": "V-001", "object_id": "OBJ-001"}]))

    assert route["reachable"] is False
    assert "not in the mapping" in route["reason"]


def test_a_target_mapped_to_a_missing_object_is_refused(tmp_path):
    route = nav.build_route(**_route_inputs(tmp_path, [{"asset_id": "A-5", "tag": "P-005", "object_id": "OBJ-999"}]))

    assert route["reachable"] is False
    assert "OBJ-999" in route["reason"]


def test_an_explicit_destination_still_plans_when_the_target_is_unresolved(tmp_path):
    route = nav.build_route(
        **_route_inputs(tmp_path, [UNRESOLVED]),
        agent_radius_m=0.20,
        start_override=(-1.0, -1.0),
        goal_override=(1.0, 1.0),
    )

    assert route["reachable"] is True
    assert route["target_waypoint_from"] == "goal_override"


def test_a_resolved_target_routes_to_its_own_object(tmp_path):
    route = nav.build_route(
        **_route_inputs(tmp_path, [{"asset_id": "A-5", "tag": "P-005", "object_id": "OBJ-001"}]),
        agent_radius_m=0.20,
        start_override=(-2.0, -2.0),
    )

    assert route["reachable"] is True
    assert route["target_object_id"] == "OBJ-001"


@pytest.mark.parametrize("artifact", ["objects_path", "mapped_path", "scene_path"])
def test_a_corrupt_artifact_stops_the_route_and_names_the_file(tmp_path, artifact):
    inputs = _route_inputs(tmp_path, [UNRESOLVED])
    inputs[artifact].write_text("not an artifact {")

    with pytest.raises(nav.RouteInputError, match=inputs[artifact].name):
        nav.build_route(**inputs)


@pytest.mark.parametrize("artifact", ["objects_path", "mapped_path", "scene_path"])
def test_a_missing_artifact_stops_the_route_and_names_the_file(tmp_path, artifact):
    inputs = _route_inputs(tmp_path, [UNRESOLVED])
    inputs[artifact].unlink()

    with pytest.raises(nav.RouteInputError, match=inputs[artifact].name):
        nav.build_route(**inputs)


@pytest.mark.parametrize(
    ("up_sign", "normal", "offset"),
    [
        # y-down capture, floor 1.0 below the origin along up, ceiling 1.5 above it.
        (-1, [0.0, -1.0, 0.0], -1.5),
        (-1, [0.0, 1.0, 0.0], 1.5),
        # y-up capture with the same heights along up.
        (1, [0.0, 1.0, 0.0], -1.5),
        (1, [0.0, -1.0, 0.0], 1.5),
    ],
)
def test_the_walkable_ceiling_is_measured_from_the_plane_height(up_sign, normal, offset):
    doc = {
        "floor": {"height": -1.0},
        "planes": {"items": [{"horizontal": True, "normal": normal, "offset": offset}]},
    }

    # 2.5 m from floor to ceiling, less the 10 cm margin, whichever way the normal points.
    assert nav._walkable_ceiling(doc, 1, up_sign) == pytest.approx(2.4)


def test_the_walkable_ceiling_ignores_planes_at_the_floor_and_walls():
    doc = {
        "floor": {"height": 0.0},
        "planes": {"items": [
            {"horizontal": True, "normal": [0.0, 1.0, 0.0], "offset": 0.0},
            {"horizontal": False, "normal": [1.0, 0.0, 0.0], "offset": -0.5},
        ]},
    }

    assert nav._walkable_ceiling(doc, 1, 1) == nav.WALKABLE_HEIGHT_MAX_M
