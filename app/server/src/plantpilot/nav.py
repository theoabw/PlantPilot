"""Floor, occupancy grid and A* for one floor of the reference plant.

The grid is built from the plant spec, not from the raw cloud, so a route is
deterministic and testable. A cloud-derived grid can replace it later behind
the same interface; the callers only need `plan()`.
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

CELL_M = 0.10
DEFAULT_AGENT_RADIUS_M = 0.35
SAFETY_MARGIN_M = 0.10
WALKABLE_HEIGHT_MAX_M = 1.5


@dataclass
class Rect:
    x0: float
    z0: float
    x1: float
    z1: float


def asset_footprint(asset: dict) -> Rect:
    x, _, z = asset["pos"]
    if asset.get("shape") == "cylinder":
        r = asset["size"][0] / 2.0
        return Rect(x - r, z - r, x + r, z + r)
    sx, _, sz = asset["size"]
    return Rect(x - sx / 2.0, z - sz / 2.0, x + sx / 2.0, z + sz / 2.0)


class Grid:
    """Occupancy grid for one floor. Row index is z, column index is x."""

    def __init__(self, spec: dict, agent_radius_m: float = DEFAULT_AGENT_RADIUS_M):
        area = spec["area"]
        self.x0, self.z0 = float(area["x0"]), float(area["z0"])
        self.width_m = float(area["x1"]) - self.x0
        self.depth_m = float(area["z1"]) - self.z0
        self.cols = int(round(self.width_m / CELL_M))
        self.rows = int(round(self.depth_m / CELL_M))
        self.blocked = np.zeros((self.rows, self.cols), dtype=np.uint8)

        # walls: one cell border, so a path never hugs or leaves the floor
        self.blocked[0, :] = 1
        self.blocked[-1, :] = 1
        self.blocked[:, 0] = 1
        self.blocked[:, -1] = 1

        for asset in spec["assets"]:
            self.add_rect(asset_footprint(asset), hard=True)
        self.agent_radius_m = agent_radius_m
        self.base_blocked = self.blocked.copy()
        self._inflate()

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
        radius_cells = (self.agent_radius_m + SAFETY_MARGIN_M) / CELL_M
        k = int(math.ceil(radius_cells))
        yy, xx = np.mgrid[-k : k + 1, -k : k + 1]
        kernel = (((xx ** 2 + yy ** 2) ** 0.5) <= radius_cells).astype(np.uint8)
        self.blocked = cv2.dilate(self.blocked, kernel, iterations=1)
        self.free = (self.blocked == 0).astype(np.uint8)
        self.clearance_m = cv2.distanceTransform(self.free, cv2.DIST_L2, 5) * CELL_M

    def with_blockers(self, blockers: list[list[float]]) -> "Grid":
        """A copy with extra blocked rectangles, inflated the same way."""
        clone = Grid.__new__(Grid)
        clone.__dict__.update({k: v for k, v in self.__dict__.items() if k != "blocked"})
        clone.blocked = self.base_blocked.copy()
        for b in blockers:
            clone.add_rect(Rect(*b))
        clone._inflate()
        return clone

    def to_cell(self, point) -> tuple[int, int]:
        col = int(round((float(point[0]) - self.x0) / CELL_M))
        row = int(round((float(point[1]) - self.z0) / CELL_M))
        return row, col

    def to_world(self, row: int, col: int) -> tuple[float, float]:
        return (self.x0 + col * CELL_M, self.z0 + row * CELL_M)

    def walkable(self, row: int, col: int) -> bool:
        return 0 <= row < self.rows and 0 <= col < self.cols and self.free[row, col] == 1

    def nearest_walkable(self, row: int, col: int, max_m: float = 0.35) -> tuple[int, int] | None:
        if self.walkable(row, col):
            return row, col
        limit = int(max_m / CELL_M)
        best = None
        for dr in range(-limit, limit + 1):
            for dc in range(-limit, limit + 1):
                if self.walkable(row + dr, col + dc):
                    d = dr * dr + dc * dc
                    if best is None or d < best[0]:
                        best = (d, (row + dr, col + dc))
        return best[1] if best else None


def astar(grid: Grid, start: tuple[float, float], goal: tuple[float, float]) -> dict:
    """8-connected A*. Returns the path in metres, its length and its clearance."""
    s = grid.nearest_walkable(*grid.to_cell(start))
    g = grid.nearest_walkable(*grid.to_cell(goal))
    if s is None:
        return {"reachable": False, "reason": "the start is not on the walkable floor", "path": []}
    if g is None:
        return {"reachable": False, "reason": "the inspection point is blocked", "path": []}

    neighbours = [(-1, 0, 1.0), (1, 0, 1.0), (0, -1, 1.0), (0, 1, 1.0),
                  (-1, -1, math.sqrt(2)), (-1, 1, math.sqrt(2)),
                  (1, -1, math.sqrt(2)), (1, 1, math.sqrt(2))]
    open_heap = [(0.0, s)]
    came: dict[tuple[int, int], tuple[int, int]] = {}
    cost = {s: 0.0}
    seen = set()
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
            if dr and dc and not (grid.walkable(current[0] + dr, current[1])
                                  and grid.walkable(current[0], current[1] + dc)):
                continue  # no slipping through the corner between two obstacles
            # prefer the middle of an aisle: a tight cell costs more than an open one
            clearance = float(grid.clearance_m[nxt[0], nxt[1]])
            penalty = 0.4 / max(clearance, 0.2)
            tentative = cost[current] + step * (1.0 + penalty)
            if tentative < cost.get(nxt, float("inf")):
                cost[nxt] = tentative
                came[nxt] = current
                heuristic = math.dist(nxt, g)
                heapq.heappush(open_heap, (tentative + heuristic, nxt))

    if g not in came and g != s:
        return {"reachable": False, "reason": "no walkable route with this obstruction", "path": []}

    cells = [g]
    while cells[-1] != s:
        cells.append(came[cells[-1]])
    cells.reverse()
    path = [grid.to_world(*c) for c in cells]
    length = sum(math.dist(a, b) for a, b in zip(path, path[1:]))
    # distanceTransform measures to the inflated obstacle, so add the inflation back
    # to report metres to the real machine surface.
    inflation = grid.agent_radius_m + SAFETY_MARGIN_M
    clearance = min(float(grid.clearance_m[r, c]) for r, c in cells) + inflation
    return {
        "reachable": True,
        "path": [[round(x, 3), round(z, 3)] for x, z in path],
        "distance_m": round(length, 2),
        "clearance_m": round(clearance, 2),
        "cells": len(cells),
    }


def load_spec(path: Path) -> dict:
    import json

    return json.loads(path.read_text())


def plan(spec: dict, start, goal, blockers: list[list[float]] | None = None,
         agent_radius_m: float = DEFAULT_AGENT_RADIUS_M) -> dict:
    grid = Grid(spec, agent_radius_m)
    if blockers:
        grid = grid.with_blockers(blockers)
    return astar(grid, start, goal)
