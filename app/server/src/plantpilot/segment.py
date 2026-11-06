"""Turn a splat into framed objects: planes, components, boxes, class proposals.

The pipeline is the one the plan fixes: remove the floor and the dominant wall
surfaces, voxelise what is left, group the occupied voxels into connected
components, split components that are still too big, and fit one oriented box
per piece.

Everything is derived from the capture. No room constant is baked in: the floor
height, the up axis, the voxel size, the point counts and the split thresholds
are measured or passed as parameters, and the ones that matter are reported in
`objects.json`. The same command runs on another capture and writes the same
artifact.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np

from .splat import Scene, load_scene

OBJECTS_VERSION = 1

# Defaults chosen from the supplied capture and kept as parameters so another
# scene can override them. They are spatial scales, not measurements of this
# room; `make objects` prints the values in force.
DEFAULTS = {
    "voxel_m": 0.03,
    "plane_distance_m": 0.025,
    "planes_max": 12,
    "plane_min_fraction": 0.02,
    "plane_sample": 60_000,
    "plane_iterations": 400,
    "min_points": 60,
    "split_points": 20_000,
    "split_target": 6_000,
    "split_max_extent_m": 3.0,
    "max_objects": 120,
    "seed": 0,
}

# The half neighbourhood of a 26-connected voxel graph: enough to find every
# edge once.
HALF_NEIGHBOURS = tuple(
    (dx, dy, dz)
    for dx in (-1, 0, 1)
    for dy in (-1, 0, 1)
    for dz in (-1, 0, 1)
    if (dx, dy, dz) > (0, 0, 0)
)


@dataclass
class Plane:
    """A plane n . p + d = 0 with its support on the full cloud."""

    normal: list[float]
    offset: float
    inliers: int
    rms_m: float
    horizontal: bool
    kind: str = "unknown"

    def distance(self, points: np.ndarray) -> np.ndarray:
        return points @ np.asarray(self.normal, dtype=np.float64) + self.offset


def _fit_plane_lsq(points: np.ndarray) -> tuple[np.ndarray, float, float]:
    """Least squares plane through points. Returns (normal, offset, rms)."""
    centroid = points.mean(axis=0)
    centred = points - centroid
    # The smallest principal direction of the covariance is the normal.
    _, _, vt = np.linalg.svd(centred, full_matrices=False)
    normal = vt[-1]
    normal = normal / float(np.linalg.norm(normal))
    offset = -float(normal @ centroid)
    rms = float(np.sqrt(np.mean((centred @ normal) ** 2)))
    return normal, offset, rms


def _ransac_plane(points: np.ndarray, threshold: float, iterations: int, rng: np.random.Generator) -> tuple[np.ndarray, float, int] | None:
    """Best plane by inlier count on the sample. Deterministic for a given rng."""
    n = points.shape[0]
    if n < 3:
        return None
    best: tuple[int, np.ndarray, float] | None = None
    picks = rng.integers(0, n, size=(iterations, 3))
    for a, b, c in picks:
        p0, p1, p2 = points[a], points[b], points[c]
        normal = np.cross(p1 - p0, p2 - p0)
        norm = float(np.linalg.norm(normal))
        if norm < 1e-9:
            continue
        normal = normal / norm
        offset = -float(normal @ p0)
        inliers = int(np.count_nonzero(np.abs(points @ normal + offset) < threshold))
        if inliers < 3:
            continue
        if best is None or inliers > best[0]:
            best = (inliers, normal, offset)
    if best is None:
        return None
    return best[1], best[2], best[0]


def find_planes(
    xyz: np.ndarray,
    *,
    up: np.ndarray,
    threshold: float,
    max_planes: int,
    min_fraction: float,
    sample_points: int,
    iterations: int,
    seed: int,
) -> tuple[list[Plane], np.ndarray]:
    """Find and remove the dominant planes. Returns (planes, keep mask).

    Candidates come from a fixed decimated sample; the support is counted on
    the full cloud and every plane is refitted to its full inlier set, so the
    numbers reported are the numbers removed.
    """
    rng = np.random.default_rng(seed)
    total = xyz.shape[0]
    sample_idx = np.sort(rng.choice(total, size=min(sample_points, total), replace=False))
    sample = xyz[sample_idx].astype(np.float64)
    sample_remaining = np.ones(sample.shape[0], dtype=bool)
    keep = np.ones(total, dtype=bool)
    planes: list[Plane] = []

    for _ in range(max_planes):
        pool = sample[sample_remaining]
        if pool.shape[0] < 100:
            break
        candidate = _ransac_plane(pool, threshold, iterations, rng)
        if candidate is None:
            break
        normal, offset, inliers = candidate
        if inliers < max(200, min_fraction * pool.shape[0]):
            break
        # refit on the sample inliers, then on the full cloud inliers
        for _ in range(2):
            mask = np.abs(sample @ normal + offset) < threshold
            if int(mask.sum()) < 3:
                break
            normal, offset, _ = _fit_plane_lsq(sample[mask])
        full_mask = np.abs(xyz @ normal + offset) < threshold
        if int(full_mask.sum()) < 3:
            break
        for _ in range(2):
            normal, offset, rms = _fit_plane_lsq(xyz[full_mask].astype(np.float64))
            full_mask = np.abs(xyz @ normal + offset) < threshold
        inlier_count = int(full_mask.sum())
        if inlier_count < max(3, min_fraction * total):
            break
        normal, offset, rms = _fit_plane_lsq(xyz[full_mask].astype(np.float64))
        full_mask = np.abs(xyz @ normal + offset) < threshold
        inlier_count = int(full_mask.sum())
        if inlier_count == 0:
            break
        horizontal = abs(float(normal @ up)) > 0.85
        planes.append(
            Plane(
                normal=[round(float(v), 6) for v in normal],
                offset=round(float(offset), 6),
                inliers=inlier_count,
                rms_m=round(float(rms), 5),
                horizontal=bool(horizontal),
                kind="horizontal" if horizontal else "vertical",
            )
        )
        keep &= ~full_mask
        # remove the same support from the sample pool
        sample_remaining &= ~(np.abs(sample @ normal + offset) < threshold)
        if not keep.any():
            break
    return planes, keep


def floor_plane(planes: list[Plane], up: np.ndarray) -> Plane | None:
    """The largest plane whose normal is close to the up axis."""
    candidates = [p for p in planes if p.horizontal]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.inliers)


def height_above_plane(points: np.ndarray, plane: Plane, up: np.ndarray) -> np.ndarray:
    """Signed height above a plane, positive on the up side."""
    normal = np.asarray(plane.normal, dtype=np.float64)
    down = float(normal @ up)
    if abs(down) < 1e-6:
        return np.zeros(points.shape[0])
    return (points @ normal + plane.offset) / down


def voxel_indices(points: np.ndarray, voxel: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Quantise points to voxels. Returns (voxel keys, inverse, dims)."""
    lo = points.min(axis=0)
    ijk = np.floor((points - lo) / voxel).astype(np.int64)
    dims = ijk.max(axis=0) + 1
    keys = (ijk[:, 0] * dims[1] + ijk[:, 1]) * dims[2] + ijk[:, 2]
    unique, inverse = np.unique(keys, return_inverse=True)
    return unique, inverse, dims


def label_components(keys: np.ndarray, dims: np.ndarray) -> np.ndarray:
    """26-connected components over sorted, unique voxel keys.

    A min-label propagation with pointer jumping (Shiloach-Vishkin style): each
    round every voxel takes the smallest label among itself and its existing
    neighbours, then the label graph is jumped to its root. It converges in a
    logarithmic number of rounds and needs no extra package.
    """
    n = keys.shape[0]
    if n == 0:
        return np.zeros(0, dtype=np.int64)
    d1, d2 = int(dims[1]), int(dims[2])
    neighbour = np.full((n, len(HALF_NEIGHBOURS)), -1, dtype=np.int64)
    index = np.arange(n, dtype=np.int64)
    for column, (dx, dy, dz) in enumerate(HALF_NEIGHBOURS):
        delta = (dx * d1 + dy) * d2 + dz
        candidate = np.searchsorted(keys, keys + delta)
        clipped = np.minimum(candidate, n - 1)
        found = (candidate < n) & (keys[clipped] == keys + delta)
        # Fill both directions of the edge: the propagation reads one neighbour
        # table, so a voxel must see the neighbour that is below it as well.
        neighbour[found, column] = candidate[found]
        neighbour[candidate[found], column] = index[found]

    labels = np.arange(n, dtype=np.int64)
    for _ in range(64):
        updated = labels.copy()
        for column in range(neighbour.shape[1]):
            other = neighbour[:, column]
            has = other >= 0
            if not has.any():
                continue
            updated[has] = np.minimum(updated[has], labels[other[has]])
        for _ in range(12):
            jumped = updated[updated]
            if np.array_equal(jumped, updated):
                break
            updated = jumped
        if np.array_equal(updated, labels):
            break
        labels = updated
    _, component = np.unique(labels, return_inverse=True)
    return component.astype(np.int64)


def component_points(keys: np.ndarray, dims: np.ndarray, inverse: np.ndarray) -> list[np.ndarray]:
    """Point indices per component, largest first."""
    labels = label_components(keys, dims)
    point_labels = labels[inverse]
    order = np.argsort(point_labels, kind="stable")
    sorted_labels = point_labels[order]
    boundaries = np.flatnonzero(np.diff(sorted_labels)) + 1
    groups = np.split(order, boundaries)
    groups = [group for group in groups if group.size]
    groups.sort(key=lambda group: group.size, reverse=True)
    return groups


def _extents(points: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """PCA frame plus robust extents (2nd to 98th percentile) of a point set."""
    centroid = points.mean(axis=0)
    centred = points - centroid
    covariance = centred.T @ centred / max(1, points.shape[0] - 1)
    values, vectors = np.linalg.eigh(covariance)
    order = np.argsort(values)[::-1]
    values = values[order]
    axes = vectors[:, order].T
    # sign convention: the largest extent points along the dominant direction
    for row in range(3):
        dominant = int(np.argmax(np.abs(axes[row])))
        if axes[row, dominant] < 0:
            axes[row] = -axes[row]
    local = centred @ axes.T
    lo = np.percentile(local, 2.0, axis=0)
    hi = np.percentile(local, 98.0, axis=0)
    centre = centroid + axes.T @ ((lo + hi) / 2.0)
    extents = hi - lo
    return centre, axes, np.maximum(extents, 1e-4)


def _planarity(values: np.ndarray) -> float:
    total = float(values.sum()) or 1e-12
    return float(values[2] / total)


def split_component(
    points: np.ndarray,
    *,
    target: int,
    max_points: int,
    max_extent: float,
    depth: int = 0,
) -> list[np.ndarray]:
    """Cut an oversized cluster into pieces along its longest axis.

    The cut goes at the widest empty gap in the coordinate histogram when there
    is one, otherwise where the left piece reaches the target size. Cutting
    along the dominant direction keeps pipe runs and machine faces as pieces a
    person would name, which k-means on a connected component does not. A piece
    stops when it is under both limits, so the split follows the geometry
    rather than a fixed piece count. Returns index arrays into `points`.
    """
    whole = np.arange(points.shape[0])
    if depth >= 8:
        return [whole]
    if points.shape[0] <= max(40, target // 4):
        return [whole]
    centre, axes, extents = _extents(points)
    if points.shape[0] <= max_points and float(extents.max()) <= max_extent:
        return [whole]

    direction = axes[int(np.argmax(extents))]
    coordinate = (points - centre) @ direction
    lo, hi = np.percentile(coordinate, [0.5, 99.5])
    if hi - lo <= 1e-3:
        return [whole]

    bins = max(6, int(math.ceil((hi - lo) / 0.05)))
    counts, edges = np.histogram(coordinate, bins=bins, range=(lo, hi))
    empty = np.flatnonzero(counts == 0)
    share = min(0.9, max(0.1, target / max(1, points.shape[0])))
    cut = float(np.quantile(coordinate, share))
    if empty.size:
        runs = np.split(empty, np.flatnonzero(np.diff(empty) > 1) + 1)
        interior = [run for run in runs if run[0] > 0 and run[-1] < bins - 1]
        if interior:
            widest = max(interior, key=lambda run: run[-1] - run[0] + 1)
            cut = float((edges[widest[0]] + edges[widest[-1] + 1]) / 2.0)

    left = coordinate <= cut
    if not left.any() or left.all():
        order = np.argsort(coordinate)
        half = order.size // 2
        left_order, right_order = order[:half], order[half:]
    else:
        left_order = np.flatnonzero(left)
        right_order = np.flatnonzero(~left)

    pieces: list[np.ndarray] = []
    for subset in (left_order, right_order):
        for piece in split_component(
            points[subset],
            target=target,
            max_points=max_points,
            max_extent=max_extent,
            depth=depth + 1,
        ):
            pieces.append(subset[piece])
    return pieces


def classify(extents: np.ndarray, axes: np.ndarray, up: np.ndarray, height_above_floor: float) -> tuple[str, float, str]:
    """A geometric class proposal, its confidence and the reason.

    This is a proposal, never an identification: the box says what shape it is,
    not what the machine is. The mapping stage decides which proposal a package
    record may use, and the interface shows the confidence.
    """
    sizes = np.sort(extents)[::-1]
    longest, middle, shortest = (float(s) for s in sizes)
    vertical_axis = int(np.argmax(np.abs(axes @ up)))
    vertical = float(extents[vertical_axis])
    horizontal = np.sort(np.delete(extents, vertical_axis))[::-1]
    footprint = float(horizontal[0] * horizontal[1])
    ratio = longest / max(middle, 1e-6)
    flatness = shortest / max(middle, 1e-6)
    low = height_above_floor <= 0.45

    if shortest <= 0.12 and middle >= 0.5 and longest >= 1.0:
        return "surface", 0.5, "flat strip left over after the planes were removed"
    if 1.6 <= vertical <= 2.4 and 0.55 <= horizontal[0] <= 1.4 and shortest <= 0.3 and height_above_floor <= 0.5:
        return "door", 0.5, "vertical panel about two metres tall standing on the floor"
    if longest >= 0.8 and middle <= 0.32 and shortest <= 0.32 and ratio >= 2.4:
        if height_above_floor >= 1.2 and vertical <= 0.5:
            return "beam", 0.45, "long horizontal run above head height"
        return "pipe", 0.5, "long run with a small cross section"
    if ratio >= 2.0 and 0.32 < middle <= 1.1 and shortest <= 0.9:
        return "duct", 0.4, "long run with a wide cross section"
    if low and vertical <= 0.35 and horizontal[1] >= 0.5 and longest >= 0.8:
        return "pallet", 0.4, "flat stack on the floor"
    if 0.05 <= footprint <= 0.6 and 0.45 <= vertical <= 1.15 and flatness >= 0.65 and height_above_floor <= 1.4:
        return "drum", 0.35, "compact round footprint standing in the room"
    if shortest <= 0.22 and vertical >= 1.2 and horizontal[0] >= 0.35:
        return "cabinet", 0.35, "thin vertical box standing on the floor"
    if 0.06 <= longest <= 0.75 and middle <= 0.6 and shortest >= 0.03:
        if height_above_floor >= 0.35:
            return "valve", 0.4, "compact body above the floor"
        return "pump", 0.35, "compact body next to the floor"
    if 0.75 < longest <= 2.2 and middle <= 1.5 and shortest <= 1.5:
        if height_above_floor <= 0.9:
            return "motor", 0.3, "machine sized body at floor level"
        return "machine", 0.3, "machine sized body standing in the room"
    if vertical >= 1.6 and horizontal[0] <= 0.9 and shortest <= 0.5:
        return "ladder", 0.25, "tall thin frame"
    if shortest <= 0.25 and horizontal[0] >= 0.4:
        return "panel", 0.3, "thin plate"
    if longest >= 2.0:
        return "structure", 0.2, "large surface left after plane removal"
    return "unknown", 0.2, "no shape rule matched"


@dataclass
class Object:
    id: str
    centre: list[float]
    axes: list[list[float]]
    extents: list[float]
    points: int
    class_: str
    class_confidence: float
    class_reason: str
    height_above_floor: float
    volume_m3: float
    planarity: float

    def as_dict(self) -> dict:
        payload = asdict(self)
        payload["class"] = payload.pop("class_")
        return {
            "id": payload["id"],
            "centre": payload["centre"],
            "axes": payload["axes"],
            "extents": payload["extents"],
            "points": payload["points"],
            "class": payload["class"],
            "class_confidence": payload["class_confidence"],
            "class_reason": payload["class_reason"],
            "height_above_floor": payload["height_above_floor"],
            "volume_m3": payload["volume_m3"],
            "planarity": payload["planarity"],
        }


def build_object(
    index: int,
    points: np.ndarray,
    *,
    up: np.ndarray,
    floor: Plane | None,
) -> Object:
    centre, axes, extents = _extents(points)
    if floor is not None:
        height = float(height_above_plane(centre[None, :], floor, up)[0])
    else:
        height = float(centre @ up)
    class_name, confidence, reason = classify(extents, axes, up, height)
    covariance = np.cov((points - points.mean(axis=0)).T) if points.shape[0] > 1 else np.eye(3)
    values = np.sort(np.linalg.eigvalsh(covariance))[::-1]
    return Object(
        id=f"OBJ-{index:03d}",
        centre=[round(float(v), 4) for v in centre],
        axes=[[round(float(v), 5) for v in row] for row in axes],
        extents=[round(float(v), 4) for v in extents],
        points=int(points.shape[0]),
        class_=class_name,
        class_confidence=round(float(confidence), 2),
        class_reason=reason,
        height_above_floor=round(height, 3),
        volume_m3=round(float(np.prod(extents)), 3),
        planarity=round(_planarity(values), 3),
    )


def vertical_extent(obj: Object, up: np.ndarray) -> float:
    """The box extent along the up axis."""
    axes = np.asarray(obj.axes, dtype=np.float64)
    return float(obj.extents[int(np.argmax(np.abs(axes @ up)))])


def scale_check(objects: list[Object], up: np.ndarray) -> dict:
    """Compare door-like proposals with a standard door height.

    A standard door is about 2.0 m. If the capture contains two or more door
    proposals whose heights agree, the ratio of their height to 2.0 is the
    scene scale. Without doors the check cannot run and the artifact says so,
    which is why distances stay in file units until it passes.
    """
    doors = [obj for obj in objects if obj.class_ == "door"]
    heights = [vertical_extent(door, up) for door in doors]
    if not heights:
        return {
            "performed": False,
            "reason": "no door-like box was framed, so the units stay as delivered",
        }
    heights.sort()
    median = float(np.median(heights))
    scale = median / 2.0
    spread = (max(heights) - min(heights)) / median if median else 0.0
    consistent = 0.85 <= scale <= 1.15 and spread <= 0.25
    return {
        "performed": True,
        "door_heights": [round(h, 3) for h in heights],
        "median_door_height": round(median, 3),
        "assumed_door_height": 2.0,
        "scale": round(scale, 3),
        "spread": round(spread, 3),
        "units_are_metres": bool(consistent),
        "reason": (
            "door proposals agree with a 2 m door, distances can be quoted in metres"
            if consistent
            else "door proposals disagree with a 2 m door, distances stay in file units"
        ),
    }


def segment(
    scene: Scene,
    out: Path,
    *,
    params: dict | None = None,
    source_path: Path | None = None,
) -> dict:
    """Run the extraction stage and write `objects.json`. Returns the payload."""
    started = time.perf_counter()
    options = dict(DEFAULTS)
    if params:
        options.update(params)
    up = np.zeros(3)
    up[scene.up_index] = float(scene.up_sign)
    xyz = scene.xyz.astype(np.float64)

    planes, keep = find_planes(
        xyz,
        up=up,
        threshold=float(options["plane_distance_m"]),
        max_planes=int(options["planes_max"]),
        min_fraction=float(options["plane_min_fraction"]),
        sample_points=int(options["plane_sample"]),
        iterations=int(options["plane_iterations"]),
        seed=int(options["seed"]),
    )
    floor = floor_plane(planes, up)
    removed_points = int((~keep).sum())
    remaining = xyz[keep]
    if remaining.shape[0] < 3:
        raise ValueError("every point was removed as a plane; the plane threshold is too wide")

    keys, inverse, dims = voxel_indices(remaining, float(options["voxel_m"]))
    groups = component_points(keys, dims, inverse)
    component_count = len(groups)

    clusters: list[np.ndarray] = []
    split_components = 0
    for group in groups:
        if group.size < int(options["min_points"]):
            continue
        points = remaining[group]
        pieces = split_component(
            points,
            target=int(options["split_target"]),
            max_points=int(options["split_points"]),
            max_extent=float(options["split_max_extent_m"]),
        )
        if len(pieces) > 1:
            split_components += 1
        for piece in pieces:
            if piece.size >= int(options["min_points"]):
                clusters.append(group[piece])

    clusters.sort(key=lambda cluster: cluster.size, reverse=True)
    capped = clusters[: int(options["max_objects"])]
    objects = [
        build_object(index + 1, remaining[cluster], up=up, floor=floor)
        for index, cluster in enumerate(capped)
    ]
    objects.sort(key=lambda obj: (obj.centre[0], obj.centre[1], obj.centre[2]))
    for index, obj in enumerate(objects, start=1):
        obj.id = f"OBJ-{index:03d}"

    largest = max((obj.points for obj in objects), default=0)
    in_objects = int(sum(obj.points for obj in objects))
    total = xyz.shape[0]
    floor_height = None
    if floor is not None:
        normal = np.asarray(floor.normal, dtype=np.float64)
        floor_height = float(-floor.offset / float(normal @ up))
    elapsed = time.perf_counter() - started

    frame = scene.meta.get("frame", {})
    payload = {
        "artifact": "objects",
        "version": OBJECTS_VERSION,
        "source": {
            "scene": str(source_path) if source_path is not None else "data/scene/scene.npz",
            "points": int(total),
            "up_axis": frame.get("up_axis"),
            "units": frame.get("units"),
        },
        "parameters": {name: (round(value, 4) if isinstance(value, float) else value) for name, value in options.items()},
        "planes": {
            "removed": len(planes),
            "removed_points": removed_points,
            "removed_fraction": round(removed_points / max(1, total), 4),
            "items": [asdict(plane) for plane in planes],
        },
        "floor": {
            "detected": floor is not None,
            "height": None if floor_height is None else round(floor_height, 4),
            "normal": None if floor is None else floor.normal,
            "inliers": 0 if floor is None else floor.inliers,
            "rms_m": None if floor is None else floor.rms_m,
        },
        "counts": {
            "components": int(component_count),
            "components_split": int(split_components),
            "clusters": int(len(clusters)),
            "objects": len(objects),
            "capped": int(max(0, len(clusters) - len(objects))),
            "points_in_objects": in_objects,
            "points_in_objects_fraction": round(in_objects / max(1, total), 4),
            "largest_object_share": round(largest / max(1, total), 4),
            "median_points_per_object": int(np.median([obj.points for obj in objects])) if objects else 0,
            "objects_by_class": _class_counts(objects),
        },
        "scale_check": scale_check(objects, up),
        "timing_s": round(elapsed, 2),
        "objects": [obj.as_dict() for obj in objects],
    }

    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=1) + "\n")
    return payload


def _class_counts(objects: list[Object]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for obj in objects:
        counts[obj.class_] = counts.get(obj.class_, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: item[1], reverse=True))


def format_report(payload: dict) -> str:
    """Human readable summary of an extraction run, printed by `make objects`."""
    counts = payload["counts"]
    planes = payload["planes"]
    floor = payload["floor"]
    scale = payload["scale_check"]
    by_class = ", ".join(f"{name} {count}" for name, count in counts["objects_by_class"].items())
    lines = [
        f"points            {payload['source']['points']:,} in, {planes['removed_points']:,} removed as planes "
        f"({planes['removed_fraction']:.1%})",
        f"planes removed    {planes['removed']}",
        f"floor             " + (f"at {floor['height']:+.3f} ({floor['inliers']:,} inliers, rms {floor['rms_m']:.3f} m)" if floor["detected"] else "not detected"),
        f"components        {counts['components']:,} at {payload['parameters']['voxel_m'] * 100:.0f} cm, {counts['components_split']} split",
        f"objects framed    {counts['objects']:,} from {counts['clusters']:,} clusters"
        + (f", {counts['capped']} capped" if counts["capped"] else ""),
        f"points in objects {counts['points_in_objects']:,} ({counts['points_in_objects_fraction']:.1%}), "
        f"largest object {counts['largest_object_share']:.1%}",
        f"median points     {counts['median_points_per_object']:,} per object",
        f"classes           {by_class}",
        f"scale check       " + (f"{scale['median_door_height']:.2f} m door, scale {scale['scale']:.2f}, "
                                + ("metres" if scale["units_are_metres"] else "file units") if scale["performed"] else scale["reason"]),
        f"extraction        {payload['timing_s']:.2f} s",
    ]
    return "\n".join(lines)


def load_objects(path: Path) -> dict:
    return json.loads(Path(path).read_text())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m plantpilot.segment",
        description="Extract framed objects from data/scene/scene.npz into data/scene/objects.json.",
    )
    parser.add_argument("--scene", default=Path("data/scene/scene.npz"), type=Path)
    parser.add_argument("--out", default=Path("data/scene/objects.json"), type=Path)
    parser.add_argument("--voxel", default=None, type=float, help="voxel size in scene units")
    parser.add_argument("--planes", default=None, type=int, help="maximum planes to remove")
    parser.add_argument("--min-points", default=None, type=int, help="minimum points per object")
    parser.add_argument("--max-objects", default=None, type=int, help="maximum objects kept")
    parser.add_argument("--json", action="store_true", help="print the metadata as JSON")
    args = parser.parse_args(argv)

    overrides = {}
    if args.voxel is not None:
        overrides["voxel_m"] = args.voxel
    if args.planes is not None:
        overrides["planes_max"] = args.planes
    if args.min_points is not None:
        overrides["min_points"] = args.min_points
    if args.max_objects is not None:
        overrides["max_objects"] = args.max_objects

    try:
        scene = load_scene(args.scene)
        payload = segment(scene, args.out, params=overrides, source_path=args.scene)
    except Exception as exc:  # noqa: BLE001 - the message is the point of the failure
        print(f"extraction failed: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(format_report(payload))
        print(f"wrote             {args.out} ({Path(args.out).stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
