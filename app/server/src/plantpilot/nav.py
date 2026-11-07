"""Floor, occupancy grid, A* pathfinding and proximity queries for PlantPilot.

Builds an occupancy grid from a capture's point cloud, inflates obstacles by
the agent radius, computes collision-free A* routes to the mapped target and
evaluates dynamic proximity along the path.

A grid built from a capture has four independent obstacle layers, because the
extracted boxes alone cannot be trusted to enclose a room: the extraction caps
objects at 150 and removes dominant planes, so a route could avoid every
retained box while walking through a wall the extraction omitted.

- The object layer blocks the footprint of every extracted box that reaches
  into the robot's body height, keeping the long-standing rules that a box
  larger than half the room is skipped and that the footprints are inflated once.
- The floor layer blocks every cell where the capture never saw floor, meaning
  no gaussian within FLOOR_TOLERANCE_M of the floor plane. Ground that was not
  observed is not ground to walk on. On a truncated capture this is what stops
  the planner leaving the room; where a capture sees floor nearly everywhere,
  as the complete one does, the object and overhead layers hold the perimeter.
- The vertical-surface layer blocks a cell when a wall crosses the robot's path.
  Each gaussian's own ellipsoid gives its surface normal: the thinnest `size`
  axis, rotated by the `rot` quaternion into the scene frame. A cell blocks when
  its near-vertical gaussians run at least WALL_SPAN_M up the wall band, from
  within WALL_FLOOR_REACH_M of the floor, with no vertical gap over
  WALL_MAX_GAP_M. The band reaches WALL_CEILING_M rather than the robot's height,
  because across a 0.55 m body a wall and a machine face are the same surface;
  the extraction already covers machine bodies with boxes. The older rule counted
  gaussians per cell, and a wall is a thin surface that never reaches a dense
  count in one 0.10 m cell, so the perimeter and the space behind it stayed
  walkable.
- The overhead layer blocks a cell when a near-horizontal surface patch lies
  inside the body band above OVERHEAD_MIN_HEIGHT_M, the line under which debris,
  pallet lips and cable runs are rideable. This is what makes a tall robot plan
  around pipework that a low robot drives under.

The blocked layer is closed by one cell before the single inflation pass, so a
one-cell pinhole between two surfaces cannot be slipped through. The union is
what the route sees. It is never replaced by an empty or points-only grid when
it looks crowded: a room with a wall must never become a free room, so a blocked
fraction above MAX_BLOCKED_FRACTION is reported as `saturated` and kept as it is.
"""

from __future__ import annotations

import heapq
import json
import math
import time
import zipfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import cv2
import numpy as np

CELL_M = 0.10
DEFAULT_AGENT_RADIUS_M = 0.35
SAFETY_MARGIN_M = 0.10
WALKABLE_HEIGHT_MIN_M = 0.10
WALKABLE_HEIGHT_MAX_M = 2.00
# The route is for a mobile robot, not a person: its body is what collides with
# equipment. A supplied capture is cluttered enough that the walkable band fills
# with pipes and cables, so obstacles come from the extracted boxes when they
# exist, and an object only blocks when it reaches into the robot's body height.
ROBOT_HEIGHT_M = 0.55
OBSTACLE_MIN_HEIGHT_M = 0.08
# The follow camera sits around 1.5 m above the floor, so it needs its own
# obstacle band: robot leg height says nothing about the pipework at eye level.
CAMERA_BAND_MIN_M = 1.15
CAMERA_BAND_MAX_M = 1.85
CAMERA_STRUCTURE_MIN_POINTS = 50
LARGE_FOOTPRINT_SHARE = 0.5
# A merged envelope is not one object. Objects arrive as oriented boxes, and the
# extraction now merges neighbouring instances into one box, so a box can cover a
# whole corner of the room. The wall, floor and overhead layers already guard the
# room's surfaces, so a footprint too big to be a single machine is left to them
# and counted off the object layer instead of blocking the aisle with the gap
# inside the merged shape.
OBJECT_MAX_FOOTPRINT_M2 = 2.5
OBJECT_MAX_SIDE_M = 2.2
# An envelope bounds an object, it does not fill it. The extraction merges
# neighbouring instances, so a box can span two machines and the gap between
# them, and blocking the whole rectangle walls off the gap. Inside a plausible
# envelope a cell blocks where the capture's own points are, plus whatever those
# points enclose: a machine's surface gives tens of gaussians per cell and rings
# its own interior, while the open gap of a merged pair reaches the envelope's
# edge and stays walkable. OBJECT_MIN_POINTS_PER_CELL keeps one stray splat from
# becoming an obstacle, and the closing pass fills a one-cell pinhole in a ring.
OBJECT_MIN_POINTS_PER_CELL = 2
# The floor layer: a cell is walkable ground only when the capture saw floor in
# it. The floor plane is fitted to 1.6 cm rms in both supplied captures, so a
# gaussian within 8 cm of it is floor, and 8 cm is also below the lowest height a
# robot body is modelled from (OBSTACLE_MIN_HEIGHT_M), so the two rules agree.
FLOOR_TOLERANCE_M = 0.08
# A gap in floor evidence up to this many cells is still floor: a capture samples
# the slab at its own spacing, and one missing point is not a hole in the room.
FLOOR_CLOSE_CELLS = 2
# The vertical-surface layer reads a gaussian's shape instead of counting its
# neighbours: `size` is in metres along the ellipsoid axes, and the thinnest of
# the three is the surface the splat lies on, so its direction is the normal.
# A surface counts as vertical when its normal is within 0.4 of horizontal. A
# wall is then recognised by how far it runs, not by how dense it is, and a wall
# never needs to be dense in one cell, which is the case the old count rule
# missed: the perimeter stayed walkable because thin surfaces never reached 55
# gaussians in a 0.10 m cell.
WALL_NORMAL_UP_DOT = 0.40
# The wall band runs from the body floor line up to WALL_CEILING_M rather than to
# the robot's own height: across 0.55 m a machine face and a wall look the same,
# so a span test in that band cannot tell them apart. The room's working height
# separates them: a wall runs from the floor to where the room ends, and a
# machine's face stops at the machine. Measured on both captures, the surfaces
# between 1.2 and 2.0 m of vertical run are the room's perimeter and its full
# height partitions, and the machine faces drop out and stay with the object
# layer, which is where the extraction already covers them.
WALL_CEILING_M = 2.00
WALL_SPAN_M = 1.20
WALL_FLOOR_REACH_M = 0.35
WALLS_FROM = (
    "near-vertical gaussian surface in the wall band: |normal.up| < 0.40, vertical "
    "span >= 1.20 m up to 2.00 m, no vertical gap over 0.20 m, starting within 0.35 m "
    "of the floor"
)
# The overhead layer catches the structure a vertical-surface test cannot: a
# surface a tall body walks into at torso height. Above 0.35 m the room's debris,
# pallet lips and cable runs are rideable and must not seal it, so the layer only
# looks higher, and it needs a patch of OVERHEAD_MIN_POINTS near-horizontal
# gaussians rather than one stray splat (a 0.1 x 0.1 m cell of surface holds tens
# of gaussians; a cable crossing it holds one or two).
OVERHEAD_MIN_HEIGHT_M = 0.35
OVERHEAD_NORMAL_UP_DOT = 0.50
OVERHEAD_MIN_POINTS = 8
# The blocked layer is closed by this many cells before the agent radius is
# inflated, so a one-cell pinhole in a splat cannot be slipped through.
CLOSE_MASK_CELLS = 1
# Two surfaces caught in one cell are not a wall. The largest gap in the vertical
# run has to stay under WALL_MAX_GAP_M, or a low kerb and a high cabinet edge
# share a cell and dress up as a surface crossing the body.
WALL_MAX_GAP_M = 0.20
# The grid is never replaced when it looks crowded; at this blocked fraction the
# artifact says `saturated` so a reviewer looks at the floor and axis instead of
# the router quietly finding a free room. The floor layer blocks the unobserved
# ring outside the room, which is most of the grid in the boiler capture, so the
# fraction describes how much of the grid is not walkable ground rather than how
# much of the room is full.
MAX_BLOCKED_FRACTION = 0.85
# The extracted boxes are already conservative axis aligned footprints of an
# oriented box, so the route needs only a small extra margin on top of them.
ROUTE_SAFETY_MARGIN_M = 0.02
DEFAULT_CLEARANCE_TARGET_M = 0.90
MIN_WAYPOINT_DISTANCE_M = 0.60
# An asset can sit above the floor (a machine mounted on a structure, as in the
# boiler room), and then there is no service ground beside its footprint. The
# inspection then stops on the nearest ground the robot can actually reach,
# within this radius of the asset, instead of a route ending in mid air.
SERVICE_FALLBACK_RADIUS_M = 2.50
# How far a live start may snap before it is refused as a robot that does not fit.
# The Cargo AMR at the door dock snaps 0.85 m, and its body is 0.9 m wide.
START_SNAP_LIMIT_M = 0.90
# How far a destination may snap, in cells of the outward search: 2.5 m along an
# axis, so a machine's inflated footprint never swallows its own inspection stop.
GOAL_SNAP_CELLS = 25
NO_ROUTE_REASON = "no walkable route from this position"
PROXIMITY_RADIUS_M = 2.50
PROXIMITY_STEP_M = 0.50


@dataclass
class Rect:
    x0: float
    z0: float
    x1: float
    z1: float


def _blocks_the_robot(obj: dict, floor_y: float, up_axis: int, up_axis_sign: int) -> bool:
    """True when the object reaches into the robot's body height above the floor.

    `axes` holds the box's own axes as its rows and `extents` the lengths along
    them, so the reach along the world up direction is the up column of the frame
    projected on the extents. Reading a row here instead measures a horizontal
    axis and misjudges every object whose longest axis is not the vertical one.
    """
    centre = np.asarray(obj.get("centre", [0.0, 0.0, 0.0]), dtype=float)
    axes = np.asarray(obj.get("axes", np.eye(3)), dtype=float)
    extents = np.asarray(obj.get("extents", [0.0, 0.0, 0.0]), dtype=float)
    if axes.shape != (3, 3) or extents.shape != (3,):
        axes, extents = np.eye(3), np.asarray(obj.get("size", [0.0, 0.0, 0.0]), dtype=float)
    half = float(np.abs(axes[:, up_axis]) @ (extents / 2.0))
    height = float(centre[up_axis]) * float(up_axis_sign)
    low, high = height - half, height + half
    return not (high < floor_y + OBSTACLE_MIN_HEIGHT_M or low > floor_y + ROBOT_HEIGHT_M)


def object_footprint(obj: dict, up_axis: int = 1) -> Rect:
    """Horizontal footprint of an extracted box, as an axis aligned rectangle.

    `axes` is the box's own frame with one axis per row and `extents` the lengths
    along those axes, so the footprint is the projected envelope: each horizontal
    half width is the sum over the box axes of their share of that direction. A
    box read as if the extents were world sizes puts a machine's height into its
    width, which is how a merged envelope became a wall across an aisle.
    """
    # objects.json uses "centre" (British spelling per scene-artifacts.md); fall
    # back to "center" and then "pos" so the function works with both schemas.
    center = obj.get("centre") or obj.get("center") or obj.get("pos", [0.0, 0.0, 0.0])
    extents = np.asarray(obj.get("extents") or obj.get("size", [0.8, 0.8, 0.8]), dtype=float)
    axes = np.asarray(obj.get("axes", np.eye(3)), dtype=float)
    horizontal = [axis for axis in range(3) if axis != up_axis]
    if axes.shape != (3, 3) or extents.shape != (3,):
        # No frame: the extents are already world aligned.
        half_x = float(extents[horizontal[0]]) / 2.0
        half_z = float(extents[horizontal[1]]) / 2.0
    else:
        half_x = float(np.abs(axes[:, horizontal[0]]) @ (extents / 2.0))
        half_z = float(np.abs(axes[:, horizontal[1]]) @ (extents / 2.0))
    x = float(center[horizontal[0]])
    z = float(center[horizontal[1]])
    return Rect(x - half_x, z - half_z, x + half_x, z + half_z)


def detect_floor(
    points: np.ndarray,
    up_axis: int = 1,
    up_axis_sign: int = 1,
    bin_size_m: float = 0.05,
    manual_override: float | None = None,
) -> tuple[float, float, float]:
    """Detect floor height from point cloud along the given up-axis.

    Returns:
        (floor_height, min_bound, max_bound) along the up-axis.
    """
    if manual_override is not None:
        y_vals = points[:, up_axis] * up_axis_sign
        return float(manual_override), float(np.min(y_vals)), float(np.max(y_vals))

    y_vals = points[:, up_axis] * up_axis_sign
    valid = np.isfinite(y_vals)
    if not np.any(valid):
        return 0.0, 0.0, 1.0

    y_clean = y_vals[valid]
    q01, q99 = np.percentile(y_clean, [1.0, 99.0])
    y_filtered = y_clean[(y_clean >= q01) & (y_clean <= q99)]
    if len(y_filtered) == 0:
        y_filtered = y_clean

    y_min, y_max = float(np.min(y_filtered)), float(np.max(y_filtered))
    num_bins = max(5, int(math.ceil((y_max - y_min) / bin_size_m)))
    counts, edges = np.histogram(y_filtered, bins=num_bins)

    # The floor is the prominent horizontal surface in the lower 30% of height
    lower_cutoff_idx = max(1, int(len(counts) * 0.30))
    lower_counts = counts[:lower_cutoff_idx]
    peak_idx = int(np.argmax(lower_counts))
    floor_y = float((edges[peak_idx] + edges[peak_idx + 1]) / 2.0)

    return floor_y, y_min, y_max


def surface_normals(rotation: np.ndarray, size: np.ndarray) -> np.ndarray:
    """World-space surface normal of each gaussian, from its own ellipsoid.

    A splat is a thin disc, so the flattest of its three axes is the surface it
    lies on. The scene artifact stores `rot` as a unit quaternion (w, x, y, z)
    and `size` as the three ellipsoid axes in metres, so the normal is the image
    of the thinnest axis under that rotation.

    Returns an (N, 3) float32 array of unit vectors, empty for an empty cloud.
    The sign of a normal carries no meaning here and neither does the sign of
    the quaternion, so the test that uses it takes an absolute dot product.
    """
    rotation = np.asarray(rotation)
    size = np.asarray(size, dtype=np.float64)
    count = int(rotation.shape[0]) if rotation.ndim == 2 else 0
    if size.shape != (count, 3):
        raise ValueError(
            f"rot and size disagree: rot has {rotation.shape}, size has {size.shape}"
        )
    if count == 0:
        return np.zeros((0, 3), dtype=np.float32)

    quaternion = np.asarray(rotation, dtype=np.float64)
    length = np.linalg.norm(quaternion, axis=1, keepdims=True)
    quaternion = quaternion / np.maximum(length, 1e-12)
    w, x, y, z = (quaternion[:, index] for index in range(4))
    thinnest = np.argmin(size, axis=1)

    normals = np.zeros((count, 3), dtype=np.float32)
    # The columns of a quaternion's rotation matrix are the images of the local
    # axes, so the k-th column is where local axis k points in the scene frame.
    for axis in range(3):
        selected = thinnest == axis
        if not np.any(selected):
            continue
        wa, xa, ya, za = w[selected], x[selected], y[selected], z[selected]
        if axis == 0:
            column = np.stack(
                [1 - 2 * (ya * ya + za * za), 2 * (xa * ya + wa * za), 2 * (xa * za - wa * ya)],
                axis=1,
            )
        elif axis == 1:
            column = np.stack(
                [2 * (xa * ya - wa * za), 1 - 2 * (xa * xa + za * za), 2 * (ya * za + wa * xa)],
                axis=1,
            )
        else:
            column = np.stack(
                [2 * (xa * za + wa * ya), 2 * (ya * za - wa * xa), 1 - 2 * (xa * xa + ya * ya)],
                axis=1,
            )
        normals[selected] = column.astype(np.float32)
    return normals


def _supported_cells(
    obj: dict,
    footprint: Rect,
    band_points: np.ndarray,
    x0: float,
    z0: float,
    rows: int,
    cols: int,
) -> np.ndarray | None:
    """The cells of an object's envelope that its own observed surface blocks.

    Inside the envelope a cell blocks when the capture put at least
    OBJECT_MIN_POINTS_PER_CELL gaussians in the robot's body band there, and so
    does any cell those points enclose: a machine's surface rings its own
    interior, so the interior goes with it. The open gap of a merged pair reaches
    the envelope's edge and stays free, which is what keeps an aisle from being
    walled off by a box that merely spans it.
    """
    centre = np.asarray(obj.get("centre", [0.0, 0.0, 0.0]), dtype=np.float64)
    axes = np.asarray(obj.get("axes", np.eye(3)), dtype=np.float64)
    extents = np.asarray(obj.get("extents", [0.0, 0.0, 0.0]), dtype=np.float64)
    c0 = max(0, int(math.floor((footprint.x0 - x0) / CELL_M)))
    c1 = min(cols, int(math.ceil((footprint.x1 - x0) / CELL_M)))
    r0 = max(0, int(math.floor((footprint.z0 - z0) / CELL_M)))
    r1 = min(rows, int(math.ceil((footprint.z1 - z0) / CELL_M)))
    if c0 >= c1 or r0 >= r1:
        return None
    cells = np.zeros((rows, cols), dtype=bool)
    if axes.shape != (3, 3) or extents.shape != (3,):
        # No frame: the envelope is all the evidence there is.
        cells[r0:r1, c0:c1] = True
        return cells
    # Cheap world-axis reject before the oriented test. `axes` holds one box
    # axis per row, so the half reach along world component i is the i-th column
    # of the frame, not the i-th row: sum_j |axes[j, i]| * extents[j] / 2.
    reach = np.abs(axes.T) @ (extents / 2.0)
    near = np.all(np.abs(band_points - centre) <= reach, axis=1)
    if not near.any():
        return None
    local = (band_points[near] - centre) @ axes.T
    inside = np.all(np.abs(local) <= extents / 2.0, axis=1)
    if not inside.any():
        return None
    points = band_points[near][inside]
    counts = _cell_counts(points[:, 0], points[:, 2], x0, z0, rows, cols)
    surface = counts[r0:r1, c0:c1] >= OBJECT_MIN_POINTS_PER_CELL
    # Free cells of the envelope window that do not reach its edge are enclosed
    # by the object's own surface, so the object owns them too.
    padded = np.pad((~surface).astype(np.uint8), 1, constant_values=1)
    flood_mask = np.zeros((padded.shape[0] + 2, padded.shape[1] + 2), dtype=np.uint8)
    cv2.floodFill(padded, flood_mask, (0, 0), 2)
    enclosed = (padded == 1)[1:-1, 1:-1]
    cells[r0:r1, c0:c1] = surface | enclosed
    return cells


def _cell_counts(
    horizontal_x: np.ndarray,
    horizontal_z: np.ndarray,
    x0: float,
    z0: float,
    rows: int,
    cols: int,
) -> np.ndarray:
    """Count points per grid cell; points outside the grid are not counted."""
    column = np.floor((horizontal_x - x0) / CELL_M).astype(np.int64)
    row = np.floor((horizontal_z - z0) / CELL_M).astype(np.int64)
    inside = (column >= 0) & (column < cols) & (row >= 0) & (row < rows)
    return np.bincount(
        row[inside] * cols + column[inside], minlength=rows * cols
    ).reshape(rows, cols)


def _cell_height_range(
    heights: np.ndarray,
    horizontal_x: np.ndarray,
    horizontal_z: np.ndarray,
    x0: float,
    z0: float,
    rows: int,
    cols: int,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Height range and largest vertical gap of the points in each cell.

    Returns (lowest, highest, largest gap between consecutive points). An empty
    cell gives inf, -inf and 0. Two surfaces that happen to share a cell show up
    as a large gap, which is how the wall rule tells them from one wall.
    """
    column = np.floor((horizontal_x - x0) / CELL_M).astype(np.int64)
    row = np.floor((horizontal_z - z0) / CELL_M).astype(np.int64)
    inside = (column >= 0) & (column < cols) & (row >= 0) & (row < rows)
    flat = row[inside] * cols + column[inside]
    values = heights[inside]
    lowest = np.full(rows * cols, np.inf, dtype=np.float64)
    highest = np.full(rows * cols, -np.inf, dtype=np.float64)
    np.minimum.at(lowest, flat, values)
    np.maximum.at(highest, flat, values)
    order = np.lexsort((values, flat))
    ordered_cell, ordered_height = flat[order], values[order]
    consecutive = ordered_cell[1:] == ordered_cell[:-1]
    gaps = np.zeros(rows * cols, dtype=np.float64)
    np.maximum.at(
        gaps,
        ordered_cell[:-1][consecutive],
        ordered_height[1:][consecutive] - ordered_height[:-1][consecutive],
    )
    return lowest.reshape(rows, cols), highest.reshape(rows, cols), gaps.reshape(rows, cols)


class Grid:
    """Occupancy grid for one floor. Row index is z, column index is x."""

    def __init__(
        self,
        agent_radius_m: float = DEFAULT_AGENT_RADIUS_M,
        area: dict | None = None,
        blocked_mask: np.ndarray | None = None,
        safety_margin_m: float | None = None,
    ):
        self.agent_radius_m = agent_radius_m
        self.safety_margin_m = SAFETY_MARGIN_M if safety_margin_m is None else float(safety_margin_m)
        if area is not None and blocked_mask is not None:
            self.x0 = float(area["x0"])
            self.z0 = float(area["z0"])
            self.width_m = float(area["x1"]) - self.x0
            self.depth_m = float(area["z1"]) - self.z0
            self.rows, self.cols = blocked_mask.shape
            self.blocked = blocked_mask.astype(np.uint8).copy()
            self.base_blocked = self.blocked.copy()
            self._inflate()
        else:
            raise ValueError("Grid requires (area, blocked_mask).")

    @classmethod
    def from_cloud(
        cls,
        points: np.ndarray,
        floor_y: float,
        up_axis: int = 1,
        up_axis_sign: int = 1,
        agent_radius_m: float = DEFAULT_AGENT_RADIUS_M,
        objects: list[dict] | None = None,
        bounds_pad_m: float = 0.5,
        walkable_height_max_m: float = ROBOT_HEIGHT_M,
        safety_margin_m: float = SAFETY_MARGIN_M,
        normals: np.ndarray | None = None,
    ) -> "Grid":
        """Build the occupancy grid for the capture.

        Four layers are rasterised and unioned before the one-cell closing and
        the single inflation pass: the extracted object boxes (robot-band rule
        and large-footprint skip unchanged), the floor the capture observed, the
        vertical surfaces that cross the robot's body, and the horizontal
        patches above `OVERHEAD_MIN_HEIGHT_M`.

        `normals` is the per-gaussian surface normal, normally
        `surface_normals(scene["rot"], scene["size"])`. A cloud without
        orientation cannot tell a wall from a pipe, so a caller that omits it
        gets the same span and patch tests applied to every point: the rule
        still holds, it is simply less selective.

        The body band runs from `OBSTACLE_MIN_HEIGHT_M` to
        `walkable_height_max_m` above the floor. A low AMR keeps the 0.55 m body
        band; a walking humanoid asks for a taller band so the pipework over an
        aisle crosses its torso.

        The union is never discarded. The grid is reported as `saturated` when
        the inflated blocked fraction passes `MAX_BLOCKED_FRACTION`, and it
        still stands: a wall must not turn a room into free space.
        """
        if up_axis == 1:
            h_x, h_z = points[:, 0], points[:, 2]
            heights = points[:, 1] * up_axis_sign
        else:
            h_x, h_z = points[:, 0], points[:, 1]
            heights = points[:, 2] * up_axis_sign

        cloud_size = int(len(points))
        valid = np.isfinite(h_x) & np.isfinite(h_z) & np.isfinite(heights)
        h_x, h_z, heights = h_x[valid], h_z[valid], heights[valid]

        q01_x, q99_x = np.percentile(h_x, [0.5, 99.5])
        q01_z, q99_z = np.percentile(h_z, [0.5, 99.5])

        x0 = float(q01_x - bounds_pad_m)
        x1 = float(q99_x + bounds_pad_m)
        z0 = float(q01_z - bounds_pad_m)
        z1 = float(q99_z + bounds_pad_m)

        cols = max(10, int(math.ceil((x1 - x0) / CELL_M)))
        rows = max(10, int(math.ceil((z1 - z0) / CELL_M)))

        room_area = max(1e-6, (x1 - x0) * (z1 - z0))
        # The capture's gaussians inside the robot's body band, in scene
        # coordinates: an envelope only blocks where these points support it.
        in_body_band = (heights >= floor_y + OBSTACLE_MIN_HEIGHT_M) & (
            heights <= floor_y + walkable_height_max_m
        )
        if up_axis == 1:
            band_points = np.stack(
                [h_x[in_body_band], heights[in_body_band] * up_axis_sign, h_z[in_body_band]],
                axis=1,
            )
        else:
            band_points = np.stack(
                [h_x[in_body_band], h_z[in_body_band], heights[in_body_band] * up_axis_sign],
                axis=1,
            )
        object_cells = np.zeros((rows, cols), dtype=np.uint8)
        object_boxes = 0
        object_boxes_skipped_large = 0
        object_boxes_skipped_room = 0
        if objects:
            for obj in objects:
                if not _blocks_the_robot(obj, floor_y, up_axis, up_axis_sign):
                    continue
                footprint = object_footprint(obj, up_axis=up_axis)
                width = max(0.0, footprint.x1 - footprint.x0)
                depth = max(0.0, footprint.z1 - footprint.z0)
                area = width * depth
                if area <= 0.0:
                    continue
                if area > LARGE_FOOTPRINT_SHARE * room_area:
                    # Not an envelope at all: it would cover the room it is in.
                    object_boxes_skipped_room += 1
                    continue
                if area > OBJECT_MAX_FOOTPRINT_M2 or max(width, depth) > OBJECT_MAX_SIDE_M:
                    # Too big to be one object: a merged envelope around several.
                    # The other layers guard the structure inside it.
                    object_boxes_skipped_large += 1
                    continue
                supported = _supported_cells(
                    obj, footprint, band_points, x0, z0, rows, cols
                )
                if supported is not None and supported.any():
                    object_cells[supported] = 1
                    object_boxes += 1

        # Floor layer: ground that was not observed is not ground to walk on, so
        # a cell with no gaussian near the floor plane is blocked. This is what
        # keeps the planner inside the room instead of driving through a wall
        # into the unobserved space behind it. A capture samples the floor at
        # about its point spacing, so one missing point is not a hole in the
        # floor: the supported mask is closed by FLOOR_CLOSE_CELLS before the
        # missing cells are blocked, which is the same tolerance the surface
        # layers get.
        floor_band = np.abs(heights.astype(np.float64) - float(floor_y)) <= FLOOR_TOLERANCE_M
        floor_cells = (_cell_counts(h_x[floor_band], h_z[floor_band], x0, z0, rows, cols) > 0)
        if FLOOR_CLOSE_CELLS > 0:
            floor_kernel = np.ones((2 * FLOOR_CLOSE_CELLS + 1,) * 2, dtype=np.uint8)
            floor_cells = cv2.dilate(floor_cells.astype(np.uint8), floor_kernel).astype(bool)
        no_floor_cells = ~floor_cells

        # The robot's own body band, for the overhead patch test.
        band = (heights >= floor_y + OBSTACLE_MIN_HEIGHT_M) & (
            heights <= floor_y + walkable_height_max_m
        )
        upper_band = band & (heights > floor_y + OVERHEAD_MIN_HEIGHT_M)
        # The wall band is taller than the body: it is the room's working
        # height, so a surface that runs the height of the room is a wall and
        # one that stops at a machine is that machine's face.
        wall_band = (heights >= floor_y + OBSTACLE_MIN_HEIGHT_M) & (
            heights <= floor_y + max(WALL_CEILING_M, walkable_height_max_m)
        )
        if normals is not None:
            normals = np.asarray(normals)
            # One normal per point of the cloud as given, before the non-finite
            # filter: the filter drops points and their normals together, so a
            # cloud with a dropped point must not need prefiltered normals.
            if normals.shape != (cloud_size, 3):
                raise ValueError(
                    f"normals has shape {normals.shape} for a cloud of {cloud_size} points; "
                    "pass one normal per point before the non-finite filter"
                )
            normals = normals[valid]
            up = np.zeros(3, dtype=np.float32)
            up[up_axis] = 1.0
            toward_up = np.abs(normals @ up)
            vertical_surface = wall_band & (toward_up < WALL_NORMAL_UP_DOT)
            horizontal_patch = upper_band & (toward_up >= OVERHEAD_NORMAL_UP_DOT)
        else:
            # No orientation: every point is a candidate surface for both tests.
            vertical_surface = wall_band
            horizontal_patch = upper_band

        lowest, highest, largest_gap = _cell_height_range(
            heights[vertical_surface].astype(np.float64),
            h_x[vertical_surface],
            h_z[vertical_surface],
            x0,
            z0,
            rows,
            cols,
        )
        wall_cells = (
            ((highest - lowest) >= WALL_SPAN_M)
            & ((lowest - floor_y) <= WALL_FLOOR_REACH_M)
            & (largest_gap <= WALL_MAX_GAP_M)
        )
        overhead_cells = (
            _cell_counts(h_x[horizontal_patch], h_z[horizontal_patch], x0, z0, rows, cols)
            >= OVERHEAD_MIN_POINTS
        )
        wall_cells = wall_cells.astype(np.uint8)
        overhead_cells = overhead_cells.astype(np.uint8)
        no_floor_cells = no_floor_cells.astype(np.uint8)

        # Independent camera layer, at eye level and without robot inflation.
        camera_band = (heights >= floor_y + CAMERA_BAND_MIN_M) & (
            heights <= floor_y + CAMERA_BAND_MAX_M
        )
        camera_cells = (
            _cell_counts(h_x[camera_band], h_z[camera_band], x0, z0, rows, cols)
            >= CAMERA_STRUCTURE_MIN_POINTS
        ).astype(np.uint8)

        blocked = object_cells | wall_cells | overhead_cells | no_floor_cells
        # Close one cell before the agent radius is inflated, so a one-cell
        # pinhole between two surfaces is not a corridor.
        if CLOSE_MASK_CELLS > 0:
            kernel_size = 2 * CLOSE_MASK_CELLS + 1
            kernel = np.ones((kernel_size, kernel_size), dtype=np.uint8)
            blocked = cv2.morphologyEx(blocked, cv2.MORPH_CLOSE, kernel)
        blocked[0, :] = 1
        blocked[-1, :] = 1
        blocked[:, 0] = 1
        blocked[:, -1] = 1

        grid_instance = cls(
            area={"x0": x0, "z0": z0, "x1": x1, "z1": z1},
            blocked_mask=blocked,
            agent_radius_m=agent_radius_m,
            safety_margin_m=safety_margin_m,
        )
        total_cells = rows * cols
        blocked_cells = int(np.sum(grid_instance.blocked == 1))
        grid_instance.occupancy_fallback = False
        grid_instance.obstacles_from = "objects+structure" if objects else "structure"
        grid_instance.object_cells = int(np.sum(object_cells == 1))
        grid_instance.object_boxes = object_boxes
        grid_instance.object_boxes_skipped_large = object_boxes_skipped_large
        grid_instance.object_boxes_skipped_room = object_boxes_skipped_room
        grid_instance.floor_domain = True
        grid_instance.floor_cells = int(np.sum(floor_cells == 1))
        grid_instance.no_floor_cells = int(np.sum(no_floor_cells == 1))
        grid_instance.wall_cells = int(np.sum(wall_cells == 1))
        grid_instance.overhead_cells = int(np.sum(overhead_cells == 1))
        # Cells the capture's own surfaces blocked, under the old key name. The
        # floor layer is reported on its own: it blocks for lack of evidence,
        # which is not a surface.
        grid_instance.structural_cells = int(np.sum((wall_cells | overhead_cells) == 1))
        grid_instance.structure_min_points = None
        # The raw layers are kept for the debug raster, the tests and the
        # "is this cell behind a wall" check: the inflated mask alone cannot
        # say which surface closed a cell.
        grid_instance.layers = {
            "object": object_cells,
            "wall": wall_cells,
            "overhead": overhead_cells,
            "floor": floor_cells,
            "floor_absent": no_floor_cells,
        }
        grid_instance.camera_mask = camera_cells
        grid_instance.camera_cells = int(np.sum(camera_cells == 1))
        grid_instance.blocked_fraction = round(blocked_cells / max(1, total_cells), 4)
        grid_instance.saturated = bool(grid_instance.blocked_fraction > MAX_BLOCKED_FRACTION)
        return grid_instance

    def _cells(self, rect: Rect) -> tuple[int, int, int, int]:
        c0 = int(math.floor((rect.x0 - self.x0) / CELL_M))
        c1 = int(math.ceil((rect.x1 - self.x0) / CELL_M))
        r0 = int(math.floor((rect.z0 - self.z0) / CELL_M))
        r1 = int(math.ceil((rect.z1 - self.z0) / CELL_M))
        return max(0, c0), min(self.cols, c1), max(0, r0), min(self.rows, r1)

    def add_rect(self, rect: Rect, hard: bool = False) -> None:
        c0, c1, r0, r1 = self._cells(rect)
        self.blocked[r0:r1, c0:c1] = 1

    def _inflate(self) -> None:
        # Before the dilation: what the capture and the blockers really occupy,
        # which is what a measured clearance has to be measured against.
        self.occupied = self.blocked.copy()
        margin = getattr(self, "safety_margin_m", SAFETY_MARGIN_M)
        radius_cells = (self.agent_radius_m + margin) / CELL_M
        k = max(1, int(math.ceil(radius_cells)))
        yy, xx = np.mgrid[-k : k + 1, -k : k + 1]
        kernel = (((xx**2 + yy**2) ** 0.5) <= radius_cells).astype(np.uint8)
        self.blocked = cv2.dilate(self.blocked, kernel, iterations=1)
        self.free = (self.blocked == 0).astype(np.uint8)
        self.clearance_m = cv2.distanceTransform(self.free, cv2.DIST_L2, 5) * CELL_M

    def with_inflation(self, agent_radius_m: float, safety_margin_m: float) -> "Grid":
        """Return a copy for another robot: same layers, inflated for its body."""
        clone = Grid.__new__(Grid)
        clone.__dict__.update(self.__dict__)
        clone.agent_radius_m = float(agent_radius_m)
        clone.safety_margin_m = float(safety_margin_m)
        clone.blocked = self.base_blocked.copy()
        clone._inflate()
        clone.blocked_fraction = round(float(np.mean(clone.blocked == 1)), 4)
        clone.saturated = bool(clone.blocked_fraction > MAX_BLOCKED_FRACTION)
        return clone

    def with_blockers(self, blockers: list[list[float]]) -> "Grid":
        """Return a copy with extra blocked rectangles, inflated identically."""
        clone = Grid.__new__(Grid)
        clone.__dict__.update(
            {k: v for k, v in self.__dict__.items() if k != "blocked"}
        )
        clone.blocked = self.base_blocked.copy()
        for b in blockers:
            clone.add_rect(Rect(*b))
        clone._inflate()
        return clone

    def to_cell(self, point: tuple[float, float] | list[float]) -> tuple[int, int]:
        """The cell holding a world point, binned as the layers are rasterised."""
        col = int(math.floor((float(point[0]) - self.x0) / CELL_M))
        row = int(math.floor((float(point[1]) - self.z0) / CELL_M))
        return row, col

    def to_world(self, row: int, col: int) -> tuple[float, float]:
        """The centre of a cell, the inverse of to_cell."""
        return (
            round(self.x0 + (col + 0.5) * CELL_M, 3),
            round(self.z0 + (row + 0.5) * CELL_M, 3),
        )

    def walkable(self, row: int, col: int) -> bool:
        return 0 <= row < self.rows and 0 <= col < self.cols and self.free[row, col] == 1

    def nearest_walkable(
        self, row: int, col: int, max_m: float = 0.50
    ) -> tuple[int, int] | None:
        if self.walkable(row, col):
            return row, col
        limit = max(1, int(round(max_m / CELL_M)))
        best = None
        for dr in range(-limit, limit + 1):
            for dc in range(-limit, limit + 1):
                r, c = row + dr, col + dc
                if self.walkable(r, c):
                    d = dr * dr + dc * dc
                    if best is None or d < best[0]:
                        best = (d, (r, c))
        return best[1] if best else None


def compute_service_waypoint(
    target_box: dict,
    grid: Grid,
    target_dist_m: float = DEFAULT_CLEARANCE_TARGET_M,
    min_dist_m: float = MIN_WAYPOINT_DISTANCE_M,
    up_axis: int = 1,
) -> tuple[float, float] | None:
    """Find a walkable inspection waypoint beside the target object.

    The waypoint is at least min_dist_m away from the object's boundary
    and selects the walkable cell with the highest clearance.
    """
    # The footprint reads the box through its own frame: `extents` runs along the
    # box's axes, so read as world sizes it puts a machine's height in its width.
    footprint = object_footprint(target_box, up_axis=up_axis)
    cx, cz = (footprint.x0 + footprint.x1) / 2.0, (footprint.z0 + footprint.z1) / 2.0
    half_x, half_z = (footprint.x1 - footprint.x0) / 2.0, (footprint.z1 - footprint.z0) / 2.0
    candidates: list[tuple[float, tuple[float, float]]] = []

    # Sample 16 radial directions around the target
    num_angles = 16
    for i in range(num_angles):
        theta = 2.0 * math.pi * i / num_angles
        dx = math.cos(theta)
        dz = math.sin(theta)

        # Distance from box center to box edge along this ray
        denom_x = abs(dx) if abs(dx) > 1e-5 else 1e-5
        denom_z = abs(dz) if abs(dz) > 1e-5 else 1e-5
        edge_dist = min(half_x / denom_x, half_z / denom_z)

        # Candidate waypoint placed target_dist_m beyond the edge
        cand_x = cx + dx * (edge_dist + target_dist_m)
        cand_z = cz + dz * (edge_dist + target_dist_m)

        # Verify distance to box edge is at least min_dist_m
        dist_to_box = math.dist((cand_x, cand_z), (cx, cz)) - edge_dist
        if dist_to_box < min_dist_m:
            continue

        r, c = grid.to_cell((cand_x, cand_z))
        if grid.walkable(r, c):
            clearance = float(grid.clearance_m[r, c])
            candidates.append((clearance, (round(cand_x, 3), round(cand_z, 3))))

    if candidates:
        # Pick the candidate with the highest obstacle clearance
        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0][1]

    # Fallback: search wider radius if narrow perimeter is constrained
    for extra in (0.3, 0.6, 1.0):
        for i in range(num_angles):
            theta = 2.0 * math.pi * i / num_angles
            cand_x = cx + math.cos(theta) * (max(half_x, half_z) + target_dist_m + extra)
            cand_z = cz + math.sin(theta) * (max(half_x, half_z) + target_dist_m + extra)
            r, c = grid.to_cell((cand_x, cand_z))
            if grid.walkable(r, c):
                return (round(cand_x, 3), round(cand_z, 3))

    return None


def derive_start_position(
    grid: Grid,
    objects: list[dict] | None = None,
    up_axis: int = 1,
) -> tuple[float, float]:
    """Derive start position: near entrance/door object, or at boundary edge with high clearance."""
    if objects:
        for obj in objects:
            # objects.json uses "class"; fall back to "class_proposal" for compatibility.
            cls_name = str(obj.get("class") or obj.get("class_proposal", "")).lower()
            if any(k in cls_name for k in ("door", "entrance", "opening", "exit")):
                # objects.json uses "centre"; fall back to "center" then "pos".
                center = obj.get("centre") or obj.get("center") or obj.get("pos", [0.0, 0.0, 0.0])
                if up_axis == 1:
                    cx, cz = float(center[0]), float(center[2])
                else:
                    cx, cz = float(center[0]), float(center[1])
                wp = compute_service_waypoint(obj, grid, target_dist_m=0.6, up_axis=up_axis)
                if wp:
                    return wp
                cell = grid.nearest_walkable(*grid.to_cell((cx, cz)), max_m=1.0)
                if cell:
                    return grid.to_world(*cell)

    # Perimeter edge search: test walkable boundary cells for highest clearance
    best_candidate: tuple[float, tuple[int, int]] | None = None
    pad = 2
    edge_cells: list[tuple[int, int]] = []
    for c in range(pad, grid.cols - pad):
        edge_cells.append((pad, c))
        edge_cells.append((grid.rows - 1 - pad, c))
    for r in range(pad, grid.rows - pad):
        edge_cells.append((r, pad))
        edge_cells.append((r, grid.cols - 1 - pad))

    for r, c in edge_cells:
        if grid.walkable(r, c):
            clearance = float(grid.clearance_m[r, c])
            if best_candidate is None or clearance > best_candidate[0]:
                best_candidate = (clearance, (r, c))

    if best_candidate:
        return grid.to_world(*best_candidate[1])

    # Absolute fallback: search from center outwards
    mid_r, mid_c = grid.rows // 2, grid.cols // 2
    cell = grid.nearest_walkable(mid_r, mid_c, max_m=5.0)
    if cell:
        return grid.to_world(*cell)

    return (grid.x0 + 1.0, grid.z0 + 1.0)


def _configured_start_position(capture_name: str | None) -> tuple[float, float] | None:
    """Return a reviewed start position for a capture when one is configured."""
    if capture_name is None:
        return None
    root = Path(__file__).resolve().parents[4]
    starts_path = root / "fixtures" / "scene" / "route_starts.json"
    starts = json.loads(starts_path.read_text(encoding="utf-8"))
    captures = starts.get("captures")
    if not isinstance(captures, dict):
        raise ValueError(f"Invalid route-start fixture: expected captures in {starts_path}")
    position = captures.get(capture_name)
    if position is None:
        return None
    if not isinstance(position, list) or len(position) != 2:
        raise ValueError(f"Invalid route start for {capture_name!r} in {starts_path}")
    return float(position[0]), float(position[1])


def astar(grid: Grid, start: tuple[float, float], goal: tuple[float, float]) -> dict[str, Any]:
    """8-connected A*. Returns path in metres, length, clearance, and computation time."""
    t0 = time.perf_counter()
    s = grid.nearest_walkable(*grid.to_cell(start))
    g = grid.nearest_walkable(*grid.to_cell(goal))
    if s is None:
        return {
            "reachable": False,
            "reason": "the start is not on the walkable floor",
            "path": [],
            "distance_m": 0.0,
            "clearance_m": 0.0,
            "astar_ms": round((time.perf_counter() - t0) * 1000.0, 2),
        }
    if g is None:
        return {
            "reachable": False,
            "reason": "the inspection point is blocked",
            "path": [],
            "distance_m": 0.0,
            "clearance_m": 0.0,
            "astar_ms": round((time.perf_counter() - t0) * 1000.0, 2),
        }

    neighbours = [
        (-1, 0, 1.0), (1, 0, 1.0), (0, -1, 1.0), (0, 1, 1.0),
        (-1, -1, math.sqrt(2)), (-1, 1, math.sqrt(2)),
        (1, -1, math.sqrt(2)), (1, 1, math.sqrt(2)),
    ]
    open_heap = [(0.0, s)]
    came: dict[tuple[int, int], tuple[int, int]] = {}
    cost: dict[tuple[int, int], float] = {s: 0.0}
    seen: set[tuple[int, int]] = set()

    while open_heap:
        _, current = heapq.heappop(open_heap)
        if current == g:
            break
        if current in seen:
            continue
        seen.add(current)

        for dr, dc, step in neighbours:
            nxt = (current[0] + dr, current[1] + dc)
            if not grid.walkable(*nxt):
                continue
            # Prevent corner clipping between adjacent obstacles
            if dr and dc and not (
                grid.walkable(current[0] + dr, current[1])
                and grid.walkable(current[0], current[1] + dc)
            ):
                continue

            clearance = float(grid.clearance_m[nxt[0], nxt[1]])
            penalty = 1.0 / max(clearance, 0.15)
            tentative = cost[current] + step * (1.0 + penalty)
            if tentative < cost.get(nxt, float("inf")):
                cost[nxt] = tentative
                came[nxt] = current
                heuristic = math.dist(nxt, g)
                heapq.heappush(open_heap, (tentative + heuristic, nxt))

    elapsed_ms = round((time.perf_counter() - t0) * 1000.0, 2)

    if g not in came and g != s:
        return {
            "reachable": False,
            "reason": NO_ROUTE_REASON,
            "path": [],
            "distance_m": 0.0,
            "clearance_m": 0.0,
            "astar_ms": elapsed_ms,
        }

    cells = [g]
    while cells[-1] != s:
        cells.append(came[cells[-1]])
    cells.reverse()

    path_2d = [grid.to_world(*c) for c in cells]
    length = sum(math.dist(a, b) for a, b in zip(path_2d, path_2d[1:]))

    return {
        "reachable": True,
        "path": [[round(x, 3), round(z, 3)] for x, z in path_2d],
        "distance_m": round(length, 2),
        "clearance_m": round(path_clearance_m(grid, path_2d), 2),
        "astar_ms": elapsed_ms,
        "cells": len(cells),
    }


def path_clearance_m(grid: Grid, path_2d: list[list[float] | tuple[float, float]]) -> float:
    """Smallest distance from a driven polyline to what the grid marks occupied.

    Measured at 5 cm steps to the edges of the uninflated cells and to the grid's
    boundary, for the whole path. A cell is occupied as soon as the capture puts
    a surface anywhere in it, so this errs on the side of the smaller number.
    """
    if not path_2d:
        return 0.0
    points = [(float(p[0]), float(p[1])) for p in path_2d]
    samples = [points[0]]
    for a, b in zip(points, points[1:]):
        steps = max(1, int(math.ceil(math.dist(a, b) / 0.05)))
        samples.extend(
            (a[0] + (b[0] - a[0]) * i / steps, a[1] + (b[1] - a[1]) * i / steps)
            for i in range(1, steps + 1)
        )
    at = np.asarray(samples, dtype=np.float64)
    x1 = grid.x0 + grid.cols * CELL_M
    z1 = grid.z0 + grid.rows * CELL_M
    best = float(
        np.min(np.minimum.reduce([at[:, 0] - grid.x0, x1 - at[:, 0], at[:, 1] - grid.z0, z1 - at[:, 1]]))
    )
    rows, columns = np.nonzero(grid.occupied)
    if rows.size:
        low_x, low_z = grid.x0 + columns * CELL_M, grid.z0 + rows * CELL_M
        for x, z in at:
            gap_x = np.maximum(low_x - x, x - (low_x + CELL_M)).clip(min=0.0)
            gap_z = np.maximum(low_z - z, z - (low_z + CELL_M)).clip(min=0.0)
            best = min(best, float(np.min(np.hypot(gap_x, gap_z))))
    return max(0.0, best)


def reachable_cells(grid: Grid, start: tuple[float, float]) -> np.ndarray:
    """Boolean mask of the cells A* can reach from `start` without corner clipping.

    Orthogonal moves only, which is a subset of what A* allows, so every marked
    cell really is reachable and the mask can be used to place a goal.
    """
    reachable = np.zeros((grid.rows, grid.cols), dtype=bool)
    cell = grid.nearest_walkable(*grid.to_cell(start), max_m=1.0)
    if cell is None:
        return reachable
    reachable[cell] = True
    stack = [cell]
    while stack:
        row, column = stack.pop()
        for row_step, column_step in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            next_row, next_column = row + row_step, column + column_step
            if not (0 <= next_row < grid.rows and 0 <= next_column < grid.cols):
                continue
            if reachable[next_row, next_column] or not grid.walkable(next_row, next_column):
                continue
            reachable[next_row, next_column] = True
            stack.append((next_row, next_column))
    return reachable


def _connected(grid: Grid, start: tuple[float, float], goal: tuple[float, float]) -> bool:
    """True when a route can join the two world points on this grid."""
    cell = grid.nearest_walkable(*grid.to_cell(goal))
    return cell is not None and bool(reachable_cells(grid, start)[cell])


def nearest_reachable_ground(
    grid: Grid,
    start: tuple[float, float],
    target: tuple[float, float],
    max_m: float = SERVICE_FALLBACK_RADIUS_M,
) -> tuple[float, float] | None:
    """The walkable cell closest to `target` that the robot can reach from `start`."""
    reachable = reachable_cells(grid, start)
    rows, columns = np.nonzero(reachable)
    if rows.size == 0:
        return None
    centres_x = grid.x0 + (columns + 0.5) * CELL_M
    centres_z = grid.z0 + (rows + 0.5) * CELL_M
    distance = np.hypot(centres_x - float(target[0]), centres_z - float(target[1]))
    best = int(np.argmin(distance))
    if float(distance[best]) > max_m:
        return None
    world_row = int(rows[best])
    world_column = int(columns[best])
    return grid.to_world(world_row, world_column)


def smooth_path(grid: Grid, path_2d: list[list[float] | tuple[float, float]]) -> list[tuple[float, float]]:
    """Shortcut a grid path where the straight line keeps the stretch's clearance.

    A* pays to stay away from obstacles. A line-of-sight test alone undoes that,
    because a shortcut that skims the inflated edge still has line of sight, so a
    shortcut is taken only when its tightest point is no tighter than the tightest
    point of the stretch it replaces.
    """
    if len(path_2d) <= 2:
        return [(float(p[0]), float(p[1])) for p in path_2d]

    pts = [(float(p[0]), float(p[1])) for p in path_2d]
    smoothed = [pts[0]]
    curr_idx = 0

    while curr_idx < len(pts) - 1:
        next_idx = len(pts) - 1
        found = False
        while next_idx > curr_idx + 1:
            if _has_line_of_sight(grid, pts[curr_idx], pts[next_idx]) and _keeps_clearance(
                grid, pts[curr_idx : next_idx + 1]
            ):
                smoothed.append(pts[next_idx])
                curr_idx = next_idx
                found = True
                break
            next_idx -= 1
        if not found:
            curr_idx += 1
            smoothed.append(pts[curr_idx])

    return smoothed


def _keeps_clearance(grid: Grid, stretch: list[tuple[float, float]]) -> bool:
    """True when the chord of a stretch is no tighter than the stretch itself."""
    tightest = min(float(grid.clearance_m[grid.to_cell(p)]) for p in stretch)
    a, b = stretch[0], stretch[-1]
    samples = max(2, int(math.ceil(math.dist(a, b) / (CELL_M * 0.5))))
    for i in range(samples + 1):
        t = i / float(samples)
        cell = grid.to_cell((a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])))
        if float(grid.clearance_m[cell]) < tightest:
            return False
    return True


def _has_line_of_sight(grid: Grid, p0: tuple[float, float], p1: tuple[float, float]) -> bool:
    dist = math.dist(p0, p1)
    num_samples = max(2, int(math.ceil(dist / (CELL_M * 0.5))))
    for i in range(num_samples + 1):
        t = i / float(num_samples)
        x = p0[0] + t * (p1[0] - p0[0])
        z = p0[1] + t * (p1[1] - p0[1])
        r, c = grid.to_cell((x, z))
        if not grid.walkable(r, c):
            return False
    return True


def _distance_to_box(point: list[float], obj: dict) -> float:
    """Distance from a scene point to an object's oriented box, zero inside it.

    This is the rule the viewer highlights by. An object without a box counts as
    the point at its centre.
    """
    # objects.json uses "centre"; fall back to "center" then "pos".
    centre = np.asarray(
        obj.get("centre") or obj.get("center") or obj.get("pos", [0.0, 0.0, 0.0]), dtype=np.float64
    )
    extents = np.asarray(obj.get("extents") or obj.get("size") or [0.0, 0.0, 0.0], dtype=np.float64)
    axes = np.asarray(obj.get("axes", np.eye(3)), dtype=np.float64)
    if axes.shape != (3, 3) or extents.shape != (3,):
        axes, extents = np.eye(3), np.zeros(3)
    local = axes @ (np.asarray(point, dtype=np.float64) - centre)
    return float(np.linalg.norm(np.maximum(np.abs(local) - extents / 2.0, 0.0)))


def compute_path_proximity(
    path_3d: list[list[float]],
    objects: list[dict],
    mapped_records: list[dict] | None = None,
    radius_m: float = PROXIMITY_RADIUS_M,
    step_m: float = PROXIMITY_STEP_M,
) -> list[dict[str, Any]]:
    """Compute nearby objects within radius_m at regularly sampled intervals along path.

    Satisfies Acceptance Check 5: verifies nearby equipment identity, distance,
    and mapping metadata along the path.
    """
    if not path_3d:
        return []
    if len(path_3d) == 1:
        path_3d = [path_3d[0], path_3d[0]]

    # Build mapping lookup table by object_id
    map_by_obj: dict[str, dict] = {}
    if mapped_records:
        for m in mapped_records:
            obj_id = m.get("object_id") or m.get("id")
            if obj_id:
                map_by_obj[obj_id] = m

    # Calculate cumulative distance along path
    dists = [0.0]
    for p_prev, p_curr in zip(path_3d, path_3d[1:]):
        seg = math.dist(p_prev, p_curr)
        dists.append(dists[-1] + seg)
    total_len = dists[-1]

    # Generate sampling points along the polyline
    sample_targets = []
    curr_d = 0.0
    while curr_d <= total_len:
        sample_targets.append(curr_d)
        curr_d += step_m
    if not sample_targets or (total_len - sample_targets[-1] > 0.1):
        sample_targets.append(total_len)

    samples: list[dict[str, Any]] = []
    seg_idx = 0

    for d_target in sample_targets:
        while seg_idx < len(dists) - 2 and dists[seg_idx + 1] < d_target:
            seg_idx += 1

        seg_len = dists[seg_idx + 1] - dists[seg_idx]
        t = 0.0 if seg_len < 1e-6 else (d_target - dists[seg_idx]) / seg_len
        p0, p1 = path_3d[seg_idx], path_3d[seg_idx + 1]
        sample_pos = [
            round(p0[0] + t * (p1[0] - p0[0]), 3),
            round(p0[1] + t * (p1[1] - p0[1]), 3),
            round(p0[2] + t * (p1[2] - p0[2]), 3),
        ]

        nearby: list[dict[str, Any]] = []
        for obj in objects:
            obj_id = str(obj.get("id", ""))
            dist_to_obj = _distance_to_box(sample_pos, obj)
            if dist_to_obj <= radius_m:
                mapped = map_by_obj.get(obj_id, {})
                tag = mapped.get("tag") or mapped.get("asset_id") or obj.get("tag") or obj_id
                # objects.json uses "class"; fall back to "class_proposal" for compatibility.
                cls_name = mapped.get("class") or obj.get("class") or obj.get("class_proposal", "equipment")
                method = mapped.get("method", "size_prior")
                state = mapped.get("state") or obj.get("state", "NOMINAL")
                nearby.append({
                    "object_id": obj_id,
                    "tag": tag,
                    "class": cls_name,
                    "distance_m": round(dist_to_obj, 2),
                    "method": method,
                    "state": state,
                })

        nearby.sort(key=lambda item: item["distance_m"])
        samples.append({
            "distance_along_path_m": round(d_target, 2),
            "position": sample_pos,
            "nearby_objects": nearby[:3],  # Nearest 3 labelled
        })

    return samples


def path_height(floor_y: float, up_axis_sign: int) -> float:
    """Scene y for a path drawn 5 cm above the floor.

    The floor height is a coordinate along the up axis, and the artifact is in
    scene coordinates, so the sign has to be applied. A y-down capture otherwise
    gets a path under its floor.
    """
    return round(float(up_axis_sign) * (float(floor_y) + 0.05), 3)


def _nearest_free(
    grid: Grid, point: tuple[float, float], radius_cells: int = 6
) -> tuple[float, float] | None:
    """Snap a world point to the nearest free cell centre, searching outward.

    Returns None when nothing is free within the radius, because a caller that
    got the point back would read that as a zero metre snap onto free ground.
    """
    row, col = grid.to_cell(point)
    r0, r1 = max(0, row - radius_cells), min(grid.rows, row + radius_cells + 1)
    c0, c1 = max(0, col - radius_cells), min(grid.cols, col + radius_cells + 1)
    if r0 >= r1 or c0 >= c1:
        return None
    # Nearest by distance, not by square ring: an inflated corner is free on an
    # earlier ring than the side beside it, though the side is the shorter move.
    free_rows, free_cols = np.nonzero(grid.blocked[r0:r1, c0:c1] == 0)
    if free_rows.size == 0:
        return None
    centres_x = grid.x0 + (free_cols + c0 + 0.5) * CELL_M
    centres_z = grid.z0 + (free_rows + r0 + 0.5) * CELL_M
    best = int(np.argmin(np.hypot(centres_x - float(point[0]), centres_z - float(point[1]))))
    return grid.to_world(int(free_rows[best]) + r0, int(free_cols[best]) + c0)


def _file_stamp(path: Path | None) -> tuple[str, int] | None:
    """A cache key that changes when the file does, so a rebuilt artifact is read."""
    if path is None or not path.exists():
        return None
    return str(path), path.stat().st_mtime_ns


@lru_cache(maxsize=2)
def _scene_arrays(stamp: tuple[str, int]) -> tuple[np.ndarray, np.ndarray | None]:
    """The capture's points and per-gaussian normals, read once per artifact."""
    data = np.load(stamp[0])
    points = data["xyz"] if "xyz" in data else data["points"]
    # The floor and wall rules read the gaussians' own shape, so the normals
    # come from the same artifact. A capture without them still builds a grid:
    # the span and patch tests then apply to every point.
    normals = None
    if "rot" in data.files and "size" in data.files:
        normals = surface_normals(data["rot"], data["size"])
    return points, normals


@lru_cache(maxsize=16)
def _layered_grid(
    scene: tuple[str, int],
    objects_stamp: tuple[str, int] | None,
    floor_y: float,
    up_axis: int,
    up_axis_sign: int,
    body_height_m: float,
) -> Grid:
    """The occupancy layers for one body height, which is the slow part of a route.

    A reroute changes the robot's position, its radius or a blocker, and none of
    those touch the layers, so the raster is built once per height and each route
    takes an inflated copy.
    """
    points, normals = _scene_arrays(scene)
    objects: list[dict] = []
    if objects_stamp is not None:
        loaded = json.loads(Path(objects_stamp[0]).read_text())
        objects = loaded if isinstance(loaded, list) else loaded.get("objects", [])
    return Grid.from_cloud(
        points=points,
        floor_y=floor_y,
        up_axis=up_axis,
        up_axis_sign=up_axis_sign,
        agent_radius_m=0.0,
        objects=objects,
        walkable_height_max_m=body_height_m,
        safety_margin_m=0.0,
        normals=normals,
    )


class RouteInputError(ValueError):
    """An artifact the route depends on is missing or cannot be read."""


def _read_json_artifact(path: Path, label: str) -> dict | list:
    """Read a JSON artifact, naming the file and the fix when it cannot be used."""
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise RouteInputError(f"cannot read the {label} artifact {path}: {exc}") from exc
    if not isinstance(document, (dict, list)):
        raise RouteInputError(f"the {label} artifact {path} is not a JSON object or list")
    return document


def _read_scene_frame(path: Path) -> tuple[int, int, str | None]:
    """Return the up axis index, its sign and the capture name from a scene artifact."""
    try:
        with np.load(path, allow_pickle=False) as data:
            meta = json.loads(str(data["meta"]))
    except (OSError, ValueError, KeyError, zipfile.BadZipFile) as exc:
        raise RouteInputError(f"cannot read the scene artifact {path}: {exc}") from exc
    frame = meta.get("frame", {})
    source = meta.get("source", {})
    source_file = source.get("file") if isinstance(source, dict) else None
    return (
        int(frame.get("up_axis_index", 1)),
        int(frame.get("up_axis_sign", 1)),
        source_file if isinstance(source_file, str) else None,
    )


def _walkable_ceiling(objects_doc: dict, up_axis: int, up_axis_sign: int) -> float:
    """Height above the floor a body may use, from the lowest horizontal plane over it.

    A low ceiling plane must not pull pipe trays and ducts into the obstacle band
    and block the whole room. `floor.height` is signed along the up axis, so a
    plane's `n . p + d = 0` is converted to the same measure before comparing.
    """
    floor_height = (objects_doc.get("floor") or {}).get("height")
    planes = (objects_doc.get("planes") or {}).get("items") or []
    if floor_height is None:
        return WALKABLE_HEIGHT_MAX_M
    clearances = []
    for plane in planes:
        normal = plane.get("normal")
        if not plane.get("horizontal") or not normal:
            continue
        along_up = float(normal[up_axis]) * up_axis_sign
        if abs(along_up) < 1e-6:
            continue
        clearance = -float(plane.get("offset", 0.0)) / along_up - float(floor_height)
        if clearance > 0.5:
            clearances.append(clearance)
    if not clearances:
        return WALKABLE_HEIGHT_MAX_M
    # Keep 10 cm margin below the ceiling plane.
    return max(1.5, round(min(clearances) - 0.10, 2))


def _resolve_target(
    target: str, mapped_records: list[dict], objects: list[dict]
) -> tuple[dict | None, str | None]:
    """Return the object mapped to `target`, or why there is none.

    A route to some other object would be reported as a route to the target, so
    there is deliberately no fallback here.
    """
    record = next(
        (row for row in mapped_records if target in (row.get("asset_id"), row.get("tag"))),
        None,
    )
    if record is None:
        return None, f"{target} is not in the mapping"
    object_id = record.get("object_id")
    if not object_id:
        detail = record.get("reason") or "no object cleared the match rule"
        return None, f"{target} is unresolved in the mapping: {detail}"
    target_box = next((obj for obj in objects if obj.get("id") == object_id), None)
    if target_box is None:
        return None, f"{target} is mapped to {object_id}, which is not in the objects artifact; run make map"
    return target_box, None


def build_route(
    scene_path: Path | None = None,
    objects_path: Path | None = None,
    mapped_path: Path | None = None,
    target_asset_id: str = "P-005",
    output_path: Path | None = None,
    manual_floor_y: float | None = None,
    agent_radius_m: float = DEFAULT_AGENT_RADIUS_M,
    agent_height_m: float = ROBOT_HEIGHT_M,
    blockers: list[list[float]] | None = None,
    start_override: tuple[float, float] | None = None,
    goal_override: tuple[float, float] | None = None,
    standing_height_m: float | None = None,
) -> dict[str, Any]:
    """End-to-end execution for Seat B: produces route.json matching Acceptance Checks 4 & 5.

    ``blockers`` is a list of ``[x0, z0, x1, z1]`` rectangles (in metres, splat
    frame) that are added on top of the permanent occupancy grid before A* runs.
    They model a blocked aisle, a parked forklift, or any transient obstacle the
    viewer lets the judge place.  Passing an empty list or None leaves the grid
    unchanged.
    """
    # A path that was passed is an artifact the route depends on, so a missing or
    # unreadable one stops the plan. Only a path left out means planning without
    # that input.
    up_axis, up_axis_sign, capture_name = 1, 1, None
    if scene_path is not None:
        up_axis, up_axis_sign, capture_name = _read_scene_frame(scene_path)

    objects: list[dict] = []
    walkable_ceiling_m = WALKABLE_HEIGHT_MAX_M
    if objects_path is not None:
        obj_data = _read_json_artifact(objects_path, "objects")
        objects = obj_data if isinstance(obj_data, list) else obj_data.get("objects", [])
        if isinstance(obj_data, dict):
            walkable_ceiling_m = _walkable_ceiling(obj_data, up_axis, up_axis_sign)

    target_box: dict | None = None
    target_problem: str | None = None
    if mapped_path is not None:
        map_data = _read_json_artifact(mapped_path, "mapping")
        mapped_records = map_data if isinstance(map_data, list) else map_data.get("mappings", [])
        target_box, target_problem = _resolve_target(target_asset_id, mapped_records, objects)
    else:
        mapped_records = []

    # Build grid from scene point cloud or fallback
    if scene_path is not None:
        scene_stamp = _file_stamp(scene_path)
        points, _ = _scene_arrays(scene_stamp)
        floor_y, _, _ = detect_floor(
            points,
            up_axis=up_axis,
            up_axis_sign=up_axis_sign,
            manual_override=manual_floor_y,
        )

        def layers_for(height_m: float) -> Grid:
            return _layered_grid(
                scene_stamp,
                _file_stamp(objects_path),
                float(floor_y),
                up_axis,
                up_axis_sign,
                max(OBSTACLE_MIN_HEIGHT_M, min(float(height_m), float(walkable_ceiling_m))),
            )

        grid = layers_for(agent_height_m).with_inflation(agent_radius_m, ROUTE_SAFETY_MARGIN_M)
    else:
        # No scene artifact: plan on an empty floor so the route document is
        # still structurally valid for the API tests.
        grid = Grid(
            area={"x0": -5.0, "z0": -5.0, "x1": 5.0, "z1": 5.0},
            blocked_mask=np.zeros((100, 100), dtype=np.uint8),
            agent_radius_m=agent_radius_m,
        )
        floor_y = 0.0

    # Derive start position and target waypoint
    start_2d = derive_start_position(grid, objects=objects, up_axis=up_axis)
    if start_override is None:
        configured_start = _configured_start_position(capture_name)
        if configured_start is not None:
            cell = grid.nearest_walkable(*grid.to_cell(configured_start), max_m=1.0)
            if cell is None:
                raise ValueError(f"Configured start for {capture_name!r} is not on the walkable floor")
            start_2d = grid.to_world(*cell)

    target_centre_2d: tuple[float, float] | None = None
    goal_from = "service_ring"
    if target_box:
        goal_2d = compute_service_waypoint(target_box, grid, up_axis=up_axis)
        c = (
            target_box.get("centre")
            or target_box.get("center")
            or target_box.get("pos")
            or [0.0, 0.0, 0.0]
        )
        target_centre_2d = (
            float(c[0]), float(c[2]) if up_axis == 1 else float(c[1])
        )
        if not goal_2d:
            # No service ground beside the footprint. That happens when the asset
            # is mounted above the floor, and the older fallback dropped the goal
            # 0.9 m off the asset wherever that landed: in the boiler room it
            # landed on air. The goal is resolved after the start is final, below.
            goal_2d = None
            goal_from = "nearest_reachable_ground"
    else:
        goal_2d = (grid.x0 + grid.width_m * 0.7, grid.z0 + grid.depth_m * 0.7)
        goal_from = "area_centre"

    horizontal = [axis for axis in range(3) if axis != up_axis]

    # Apply transient blockers (parked forklift, closed aisle, etc.)
    permanent_grid = grid
    if blockers:
        grid = grid.with_blockers(blockers)

    # A live robot replans from where it stands, not from the artifact's start.
    # Snapping to a free cell is fine for rounding to the grid, but a large
    # clearance can block the robot's own dock entirely. Jumping to whichever
    # free cell is nearest then teleports it across the room and reports a
    # short route that the robot could never drive, so that case is refused.
    start_problem = None
    if start_override is not None:
        requested_start = (float(start_override[0]), float(start_override[1]))
        snapped_start = _nearest_free(
            grid, requested_start, radius_cells=int(math.ceil(START_SNAP_LIMIT_M / CELL_M))
        )
        start_2d = snapped_start if snapped_start is not None else requested_start
        snap_m = math.dist(start_2d, requested_start)
        if snapped_start is None or snap_m > START_SNAP_LIMIT_M:
            start_problem = (
                f"the robot does not fit at its current position with "
                f"{agent_radius_m:g} m clearance"
            )

    if goal_2d is None and target_centre_2d is not None:
        goal_2d = nearest_reachable_ground(grid, start_2d, target_centre_2d)
        if goal_2d is not None:
            goal_from = "nearest_reachable_ground"
        else:
            goal_2d = (target_centre_2d[0] + 0.9, target_centre_2d[1])
            goal_from = "off_asset_offset"

    if goal_override is not None:
        # A destination is an object centre, so it usually lands inside that
        # object's inflated footprint. Snap outward up to 2.5 m to the nearest
        # free cell, which becomes the inspection waypoint for the visit.
        wanted = (float(goal_override[0]), float(goal_override[1]))
        goal_2d = _nearest_free(grid, wanted, radius_cells=GOAL_SNAP_CELLS) or wanted
        goal_from = "goal_override"
        if not _connected(grid, start_2d, goal_2d) and (
            not blockers or not _connected(permanent_grid, start_2d, goal_2d)
        ):
            # The nearest free cell is a pocket no route enters, and no obstacle
            # the user placed is the reason, so the robot stops on the nearest
            # ground it can reach. A blocker that cuts the room stays a refusal:
            # stopping at the blocker would hide the thing the user asked about.
            ground = nearest_reachable_ground(
                grid, start_2d, wanted, max_m=GOAL_SNAP_CELLS * CELL_M * math.sqrt(2)
            )
            if ground is not None:
                goal_2d = ground
                goal_from = "goal_override_reachable"
    elif target_problem:
        # The target has no object to drive to. An explicit destination above
        # does not need one, so only this case refuses the plan.
        goal_2d = start_2d
        goal_from = "unresolved_target"

    # Compute A* path
    if goal_override is None and target_problem:
        plan_result = {"reachable": False, "path": [], "reason": target_problem}
    else:
        plan_result = astar(grid, start_2d, goal_2d)
        if not plan_result["reachable"] and blockers and plan_result["reason"] == NO_ROUTE_REASON:
            plan_result["reason"] = "no walkable route with this obstruction"
    if start_problem:
        plan_result = {"reachable": False, "path": [], "reason": start_problem}

    # The route document is in scene coordinates, so the height above the floor
    # is multiplied by the sign of the up axis. Writing the height coordinate
    # itself put a y-down capture's path under the floor.
    y_render = path_height(floor_y, up_axis_sign)
    if plan_result["reachable"]:
        raw_path = plan_result["path"]
        smoothed_2d = smooth_path(grid, raw_path)
        path_3d = [[round(x, 3), y_render, round(z, 3)] for x, z in smoothed_2d]
        # The robot drives the smoothed line, so that is what gets reported.
        plan_result["distance_m"] = round(
            sum(math.dist(a, b) for a, b in zip(smoothed_2d, smoothed_2d[1:])), 2
        )
        plan_result["clearance_m"] = round(path_clearance_m(grid, smoothed_2d), 2)
    else:
        path_3d = []

    # Proximity queries along path (Acceptance Check 5)
    samples = compute_path_proximity(
        path_3d=path_3d,
        objects=objects,
        mapped_records=mapped_records,
        radius_m=PROXIMITY_RADIUS_M,
        step_m=PROXIMITY_STEP_M,
    )

    # When the route was planned crouched, work out which stretches actually
    # need it. A second grid at standing height is built and the path is checked
    # against it, so the viewer can crouch only under the low structure instead
    # of walking folded for the whole route.
    crouch_spans: list[list[float]] = []
    if (
        standing_height_m is not None
        and float(standing_height_m) > float(agent_height_m) + 0.01
        and len(path_3d) >= 2
    ):
        # The crouch span is a question about the body column, not about
        # navigation clearance: the route already keeps the body radius away
        # from obstacles. A 0.12 m column approximates a humanoid turning
        # sideways to slip past structure, which is how a person would pass
        # pipework beside the path. Testing the full navigation inflation made
        # the model duck for obstacles it could simply walk past.
        standing_grid = layers_for(float(standing_height_m)).with_inflation(0.12, 0.0)
        if blockers:
            standing_grid = standing_grid.with_blockers(blockers)
        distances = [0.0]
        for index in range(1, len(path_3d)):
            previous = path_3d[index - 1]
            current = path_3d[index]
            distances.append(
                distances[-1]
                + float(np.hypot(current[0] - previous[0], current[2] - previous[2]))
            )
        # Route vertices are metres apart, so sampling only the vertices misses
        # the obstacle between them. Walk every segment at 10 cm.
        needed: list[tuple[float, float]] = []
        open_start: float | None = None
        travelled = 0.0
        for index in range(1, len(path_3d)):
            previous = path_3d[index - 1]
            current = path_3d[index]
            segment = max(
                0.001,
                float(
                    np.hypot(current[0] - previous[0], current[2] - previous[2])
                    if up_axis == 1
                    else np.hypot(current[0] - previous[0], current[1] - previous[1])
                ),
            )
            steps = max(1, int(np.ceil(segment / 0.1)))
            for step in range(steps + (1 if index == len(path_3d) - 1 else 0)):
                ratio = min(1.0, step / steps)
                at = travelled + segment * ratio
                if up_axis == 1:
                    cell = standing_grid.to_cell(
                        (
                            float(previous[0]) + (float(current[0]) - float(previous[0])) * ratio,
                            float(previous[2]) + (float(current[2]) - float(previous[2])) * ratio,
                        )
                    )
                else:
                    cell = standing_grid.to_cell(
                        (
                            float(previous[0]) + (float(current[0]) - float(previous[0])) * ratio,
                            float(previous[1]) + (float(current[1]) - float(previous[1])) * ratio,
                        )
                    )
                blocked_here = not standing_grid.walkable(*cell)
                if blocked_here and open_start is None:
                    open_start = max(0.0, at - 0.1)
                elif not blocked_here and open_start is not None:
                    needed.append((open_start, at))
                    open_start = None
            travelled += segment
        if open_start is not None:
            needed.append((open_start, travelled))
        merged: list[list[float]] = []
        for start_m, end_m in needed:
            if merged and start_m - merged[-1][1] < 0.6:
                merged[-1][1] = end_m
            else:
                merged.append([round(start_m, 2), round(end_m, 2)])
        crouch_spans = merged

    # How far the inspection stops from the target's footprint. 0 for a normal
    # service waypoint, larger when the asset sits where no floor-level ground
    # beside it exists and the route has to stop on the nearest reachable ground.
    goal_standoff_m = 0.0
    standoff_box = target_box
    if goal_override is not None:
        # A destination is not the default target. The viewer sends an object's
        # centre, so the box is the one centred there; a point that is no object's
        # centre has no footprint, and the distance to it is the stand-off.
        wanted = (float(goal_override[0]), float(goal_override[1]))
        standoff_box = next(
            (
                obj
                for obj in objects
                if "centre" in obj
                and math.dist((obj["centre"][horizontal[0]], obj["centre"][horizontal[1]]), wanted) < 0.01
            ),
            None,
        )
        goal_standoff_m = math.dist(goal_2d, wanted)
    if standoff_box is not None:
        footprint = object_footprint(standoff_box, up_axis=up_axis)
        gap_x = max(footprint.x0 - goal_2d[0], 0.0, goal_2d[0] - footprint.x1)
        gap_z = max(footprint.z0 - goal_2d[1], 0.0, goal_2d[1] - footprint.z1)
        goal_standoff_m = float(np.hypot(gap_x, gap_z))

    free_count = int(np.sum(grid.free == 1))
    blocked_count = int(np.sum(grid.blocked == 1))
    total_cells = max(1, grid.rows * grid.cols)
    blocked_fraction = blocked_count / total_cells

    route_doc: dict[str, Any] = {
        "floor_height_m": round(floor_y, 3),
        "up_axis": ("+" if up_axis_sign == 1 else "-") + ("y" if up_axis == 1 else "z"),
        # The robot profile and the layer sources are part of the document, not
        # only of grid_stats: the viewer and the notes read them from here.
        "obstacles_from": getattr(grid, "obstacles_from", "points"),
        "agent_radius_m": round(float(agent_radius_m), 3),
        "agent_height_m": round(float(agent_height_m), 3),
        "start": [round(start_2d[0], 3), y_render, round(start_2d[1], 3)],
        "target_asset_id": target_asset_id,
        "target_object_id": target_box.get("id") if target_box else None,
        "target_waypoint": [round(goal_2d[0], 3), y_render, round(goal_2d[1], 3)],
        "target_waypoint_from": goal_from,
        "target_waypoint_standoff_m": round(goal_standoff_m, 2),
        # How far the stop is from the destination the viewer asked for. A large
        # figure with "goal_override_reachable" means a taller body could not get
        # near it, so a crouched plan may stop closer.
        "goal_snap_m": (
            round(math.dist(goal_2d, (float(goal_override[0]), float(goal_override[1]))), 2)
            if goal_override is not None
            else 0.0
        ),
        "planned_height_m": round(float(agent_height_m), 3),
        "crouch_spans_m": crouch_spans,
        "reachable": plan_result["reachable"],
        "reason": plan_result.get("reason"),
        "distance_m": plan_result.get("distance_m", 0.0),
        "clearance_m": plan_result.get("clearance_m", 0.0),
        "astar_ms": plan_result.get("astar_ms", 0.0),
        "path": path_3d,
        "path_samples": samples,
        "active_blockers": blockers or [],
        "grid": {
            "x0": round(grid.x0, 3),
            "z0": round(grid.z0, 3),
            "cell_m": CELL_M,
            "rows": grid.rows,
            "cols": grid.cols,
            "horizontal_axes": [horizontal[0], horizontal[1]],
            "blocked_packed": __import__("base64").b64encode(
                np.packbits(grid.blocked.astype(np.uint8).ravel())
            ).decode("ascii"),
        },
        "camera_grid": {
            "x0": round(grid.x0, 3),
            "z0": round(grid.z0, 3),
            "cell_m": CELL_M,
            "rows": grid.rows,
            "cols": grid.cols,
            "horizontal_axes": [horizontal[0], horizontal[1]],
            "blocked_packed": __import__("base64").b64encode(
                np.packbits(np.asarray(getattr(grid, "camera_mask", np.zeros_like(grid.blocked))).astype(np.uint8).ravel())
            ).decode("ascii"),
            "camera_band_m": [CAMERA_BAND_MIN_M, CAMERA_BAND_MAX_M],
            "camera_blocked_cells": int(getattr(grid, "camera_cells", 0)),
        },
        "grid_stats": {
            "robot_height_m": round(float(agent_height_m), 3),
            "agent_height_m": round(float(agent_height_m), 3),
            "cols": grid.cols,
            "rows": grid.rows,
            "resolution_m": CELL_M,
            "free_cells": free_count,
            "blocked_cells": blocked_count,
            "blocked_fraction": round(blocked_fraction, 4),
            "object_blocked_cells": int(getattr(grid, "object_cells", 0)),
            "object_boxes": int(getattr(grid, "object_boxes", 0)),
            "object_boxes_skipped_large": int(getattr(grid, "object_boxes_skipped_large", 0)),
            "object_boxes_skipped_room": int(getattr(grid, "object_boxes_skipped_room", 0)),
            "object_max_footprint_m2": OBJECT_MAX_FOOTPRINT_M2,
            "object_max_side_m": OBJECT_MAX_SIDE_M,
            "structural_blocked_cells": int(getattr(grid, "structural_cells", 0)),
            "floor_blocked_cells": int(getattr(grid, "no_floor_cells", 0)),
            "floor_cells": int(getattr(grid, "floor_cells", 0)),
            "wall_blocked_cells": int(getattr(grid, "wall_cells", 0)),
            "overhead_blocked_cells": int(getattr(grid, "overhead_cells", 0)),
            "walls_from": WALLS_FROM,
            "floor_tolerance_m": FLOOR_TOLERANCE_M,
            "overhead_min_height_m": OVERHEAD_MIN_HEIGHT_M,
            "overhead_min_points": OVERHEAD_MIN_POINTS,
            "structure_min_points": getattr(grid, "structure_min_points", None),
            "blocked_fraction_limit": MAX_BLOCKED_FRACTION,
            "saturated": bool(blocked_fraction > MAX_BLOCKED_FRACTION),
            "floor_domain": bool(getattr(grid, "floor_domain", False)),
            "occupancy_fallback": bool(getattr(grid, "occupancy_fallback", False)),
            "obstacles_from": getattr(grid, "obstacles_from", "points"),
            "agent_radius_m": round(float(agent_radius_m), 3),
            "safety_margin_m": round(float(getattr(grid, "safety_margin_m", SAFETY_MARGIN_M)), 3),
        },
    }

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(route_doc, indent=2))

    return route_doc
