"""The walkable map has to respect floors and walls, not gaussian counts.

The room below is sampled the way a capture samples it: a floor, thin wall
surfaces, a doorway and a pipe overhead. No cell of a wall holds the 55
gaussians the old structural layer needed, so the old grid walked straight
through the wall and out over ground it never observed.
"""

from __future__ import annotations

import numpy as np
import pytest

from plantpilot import nav

FLOOR = 0.0
ROOM_X = (0.0, 4.0)
ROOM_Z = (-1.0, 3.0)
WALL_HEIGHT = 2.0
SAMPLE_M = 0.05
DOORWAY_Z = (1.6, 2.4)


def _segments(start: float, stop: float, step: float) -> np.ndarray:
    return np.arange(start, stop + 1e-9, step)


def synthetic_room() -> np.ndarray:
    """Return (points, normals) for a floored room with two walls and a pipe.

    - The floor runs the whole room at FLOOR.
    - Wall A is the solid partition at z = 0: it separates the room into a south
      strip and the main area, and it has no opening.
    - Wall B is the partition at x = 2 with a doorway at DOORWAY_Z, so the two
      halves of the main area connect through the opening.
    - A pipe crosses the west half at 1.5 m, well above a 0.55 m robot.

    Every wall is a single surface of points 5 cm apart, which is what a capture
    gives for a thin wall: too few gaussians per cell for a count test to see.
    """
    rng = np.random.default_rng(7)
    parts: list[np.ndarray] = []
    normals: list[np.ndarray] = []

    def add(points: np.ndarray, normal: tuple[float, float, float]) -> None:
        parts.append(points)
        normals.append(np.tile(np.asarray(normal, dtype=np.float32), (len(points), 1)))

    # Floor.
    floor_x, floor_z = np.meshgrid(
        _segments(ROOM_X[0], ROOM_X[1], SAMPLE_M), _segments(ROOM_Z[0], ROOM_Z[1], SAMPLE_M)
    )
    floor = np.stack(
        [floor_x.ravel(), np.full(floor_x.size, FLOOR), floor_z.ravel()], axis=1
    )
    add(floor, (0.0, 1.0, 0.0))

    # Wall A at z = 0, solid, reaching a little past the floor on both sides so
    # there is no way round its ends.
    wall_x, wall_y = np.meshgrid(
        _segments(ROOM_X[0] - 0.2, ROOM_X[1] + 0.2, SAMPLE_M),
        _segments(0.0, WALL_HEIGHT, SAMPLE_M),
    )
    wall_a = np.stack(
        [wall_x.ravel(), wall_y.ravel(), np.full(wall_x.size, 0.0)], axis=1
    )
    add(wall_a, (0.0, 0.0, 1.0))

    # Wall B at x = 2 with the doorway cut out.
    along_z = _segments(ROOM_Z[0] + 1.0, ROOM_Z[1] - 0.2, SAMPLE_M)
    along_z = along_z[(along_z < DOORWAY_Z[0]) | (along_z > DOORWAY_Z[1])]
    wall_z, wall_ym = np.meshgrid(along_z, _segments(0.0, WALL_HEIGHT, SAMPLE_M))
    wall_b = np.stack(
        [np.full(wall_z.size, 2.0), wall_ym.ravel(), wall_z.ravel()], axis=1
    )
    add(wall_b, (1.0, 0.0, 0.0))

    # A pipe across the west half at 1.5 m: surface points and radial normals.
    pipe_x = _segments(0.2, 1.8, 0.02)
    angle = _segments(0.0, 2.0 * np.pi, 0.15)
    pipe_xx, pipe_angle = np.meshgrid(pipe_x, angle)
    radius = 0.06
    pipe = np.stack(
        [
            pipe_xx.ravel(),
            1.5 + radius * np.cos(pipe_angle.ravel()),
            1.5 + radius * np.sin(pipe_angle.ravel()),
        ],
        axis=1,
    )
    parts.append(pipe)
    normals.append(
        np.stack(
            [
                np.zeros(pipe.shape[0]),
                np.cos(pipe_angle.ravel()),
                np.sin(pipe_angle.ravel()),
            ],
            axis=1,
        ).astype(np.float32)
    )

    points = np.vstack(parts)
    points[:, 0] += rng.normal(0.0, 0.002, len(points))
    points[:, 2] += rng.normal(0.0, 0.002, len(points))
    return points, np.vstack(normals)


def room_grid(agent_radius_m: float = 0.15) -> nav.Grid:
    points, normals = synthetic_room()
    return nav.Grid.from_cloud(
        points,
        floor_y=FLOOR,
        up_axis=1,
        agent_radius_m=agent_radius_m,
        safety_margin_m=0.02,
        normals=normals,
    )


def test_a_route_through_a_wall_is_unreachable():
    """Wall A is solid, so the south strip cannot be reached from the main area."""
    grid = room_grid()

    assert grid.wall_cells > 0
    route = nav.astar(grid, (1.0, 1.0), (1.0, -0.5))

    assert route["reachable"] is False
    assert route["path"] == []


def test_the_wall_layer_follows_the_wall_across_the_room():
    """The blocked cells have to trace the partition, not a few splat clumps."""
    grid = room_grid()
    wall = grid.layers["wall"].astype(bool)

    row = int(round((0.0 - grid.z0) / nav.CELL_M))
    # The wall sits on a cell boundary and the samples are jittered, so look at
    # the three rows around it.
    covered = int(wall[row - 1 : row + 2, :].any(axis=0).sum())
    # 4.2 m of wall at 0.10 m cells: at least 30 of the 42 possible cells.
    assert covered >= 30, covered
    # and the same layer reports it in the artifact counts
    assert grid.wall_cells == int(wall.sum())


def test_a_route_under_a_pipe_at_eye_height_is_reachable():
    """The pipe at 1.5 m is above a 0.55 m robot: it must not block the aisle."""
    grid = room_grid()
    pipe_cell = grid.to_cell((1.0, 1.5))

    assert grid.layers["wall"][pipe_cell] == 0
    route = nav.astar(grid, (0.8, 0.6), (0.8, 2.6))

    assert route["reachable"] is True
    assert route["distance_m"] >= 2.0


def test_the_doorway_stays_open():
    """Wall B blocks the two halves of the main area except at the doorway."""
    grid = room_grid()
    straight = nav.astar(grid, (1.0, 1.0), (3.0, 1.0))

    assert straight["reachable"] is True
    # the doorway is at z = 1.6 to 2.4, so the route has to go north first
    assert straight["distance_m"] > 2.5
    assert max(point[1] for point in straight["path"]) > DOORWAY_Z[0]


def test_a_cell_the_capture_never_saw_is_not_walkable():
    """Ground outside the observed floor is blocked, not free space to drive in."""
    grid = room_grid()
    # x = -0.3 is in the padded ring beyond the floor, which starts at x = 0
    row, column = grid.to_cell((-0.3, 1.0))

    assert grid.layers["floor_absent"][row, column] == 1
    assert not grid.walkable(row, column)
    assert grid.walkable(*grid.to_cell((1.0, 1.0)))


def test_a_low_parapet_is_a_machine_not_a_wall():
    """The wall layer measures how far a surface runs up the room.

    A 0.4 m parapet is not a wall, so the wall layer leaves it alone and the
    extraction's box is what stops the robot there. That division is why the
    object layer stays in the union and why the wall rule never replaced it.
    """
    points, normals = synthetic_room()
    # Strip the room's walls and keep a 0.4 m high parapet at z = 0.
    keep = ~(
        (np.abs(points[:, 2] - 0.0) < 0.02)
        | (np.abs(points[:, 0] - 2.0) < 0.02)
    )
    points = points[keep]
    normals = normals[keep]
    parapet_x, parapet_y = np.meshgrid(
        _segments(0.0, 2.0, SAMPLE_M), _segments(0.0, 0.4, SAMPLE_M)
    )
    parapet = np.stack(
        [parapet_x.ravel(), parapet_y.ravel(), np.full(parapet_x.size, 0.0)], axis=1
    )
    points = np.vstack([points, parapet])
    normals = np.vstack(
        [normals, np.tile(np.array([0.0, 0.0, 1.0], dtype=np.float32), (len(parapet), 1))]
    )

    grid = nav.Grid.from_cloud(
        points,
        floor_y=FLOOR,
        up_axis=1,
        agent_radius_m=0.15,
        safety_margin_m=0.02,
        normals=normals,
    )

    assert grid.wall_cells == 0
    # With the parapet boxed, the object layer blocks it.
    box = {
        "centre": [1.0, 0.2, 0.0],
        "axes": [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
        "extents": [2.0, 0.4, 0.2],
    }
    boxed = nav.Grid.from_cloud(
        points,
        floor_y=FLOOR,
        up_axis=1,
        agent_radius_m=0.15,
        safety_margin_m=0.02,
        objects=[box],
        normals=normals,
    )
    assert boxed.object_cells > 0
    assert not boxed.walkable(*boxed.to_cell((0.5, 0.0)))


def test_surface_normals_come_from_the_thinnest_axis():
    """A quaternion and three sizes describe the surface a splat lies on."""
    # A gaussian flat in its local y axis, rotated a quarter turn about z, so
    # its thin axis points along scene x.
    angle = np.pi / 2.0
    rotation = np.array([[np.cos(angle / 2), 0.0, 0.0, np.sin(angle / 2)]])
    size = np.array([[0.05, 0.001, 0.05]])
    normal = nav.surface_normals(rotation, size)

    assert normal.shape == (1, 3)
    assert np.allclose(np.abs(normal[0]), [1.0, 0.0, 0.0], atol=1e-6)


def test_surface_normals_reject_a_length_mismatch():
    with pytest.raises(ValueError, match="disagree"):
        nav.surface_normals(np.zeros((2, 4)), np.zeros((3, 3)))


def test_a_non_finite_gaussian_drops_its_normal_with_it():
    """The normals are one per point of the cloud as given, before the filter.

    A cloud with a NaN gaussian still has one normal for it, so the length check
    must run against the whole cloud and the filter mask then drops the point and
    its normal together. Validating against the filtered count raises instead.
    """
    points, normals = synthetic_room()
    points = np.vstack([points, [[np.nan, np.nan, np.nan]]])
    normals = np.vstack([normals, np.array([[0.0, 1.0, 0.0]], dtype=np.float32)])

    grid = nav.Grid.from_cloud(
        points,
        floor_y=FLOOR,
        up_axis=1,
        agent_radius_m=0.15,
        safety_margin_m=0.02,
        normals=normals,
    )

    assert grid.wall_cells > 0
    assert grid.walkable(*grid.to_cell((1.0, 1.0)))


def test_prefiltered_normals_are_refused_with_a_clear_error():
    points, normals = synthetic_room()
    points = np.vstack([points, [[np.nan, np.nan, np.nan]]])
    normals = np.vstack([normals, np.array([[0.0, 1.0, 0.0]], dtype=np.float32)])

    with pytest.raises(ValueError, match="one normal per point"):
        nav.Grid.from_cloud(points, floor_y=FLOOR, up_axis=1, normals=normals[:-1])
