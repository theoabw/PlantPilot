"""Turn a splat into framed objects: planes, components, boxes, class proposals.

The pipeline: remove the floor, ceiling and wall surfaces, voxelise what is
left, group the occupied voxels into connected components, join components that
are stacked bands of one instance, split a component that is still oversized at
a measured gap or at its thinnest neck, and fit one oriented box per instance,
upright when the instance stands on the floor.

Plane removal is what decides whether an object survives at all. A plane is
proposed from the gaussians' own normals as well as from three point draws, so a
wall is proposed as easily as the floor, and the two orientations get their own
budget because one family taking the whole budget is how every plane used to be
horizontal. A horizontal plane is removed through a gate: a gaussian goes only
when its own surface normal, the thinnest axis of its ellipsoid, agrees with the
plane, or when the column of points through it is a thin sheet in the band. A
machine face crossed by a horizontal plane fails both tests however noisy its
normals are, which is what stops a plane from slicing an object. A vertical
plane is a wall, and a wall removed only in part is a connected sheet that welds
every object standing against it into one component, so walls are removed whole.

Nothing in the room is assumed. The floor height, the up axis, the voxel size,
the point counts, the split thresholds and the cap are measured or passed as
parameters, and the ones that matter are reported in `objects.json`, including
the clusters the cap dropped and the count of cuts made from evidence and from a
quota.
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

from .splat import Scene, hero_camera_pose, load_scene

OBJECTS_VERSION = 1

# A 26-connected voxel graph only holds a surface together when the voxel is at
# least as large as the distance between neighbouring points. Captures differ in
# density, so the stage measures the spacing on the floor and coarsens the voxel
# to it. The factor is a margin for the uneven spacing of a real capture.
VOXEL_PER_SPACING = 1.4

# A box is fitted to the points between these percentiles on each axis. The
# 2nd to 98th used to trim a few centimetres off every box, which is why a
# completed washing machine still read as short and why an anchor's own box
# held only 88 percent of the anchor's points: at half a percent the box holds
# 99 percent of its own points and still ignores a stray gaussian.
EXTENT_PERCENTILE = 0.5

# A component over the size limits is cut only at an empty run at least this
# wide, in metres. Two rows of gaussians on one surface are a few millimetres
# apart; two objects are not.
SPLIT_GAP_M = 0.10

# A box is framed upright when its lowest points are this close to the floor and
# it is at least this tall: it is standing on the measured floor, so gravity is
# the one direction its box has to respect. A pipe lying on the floor, a pallet
# and a strip of cable keep the free frame.
STANDING_M = 0.10
STANDING_HEIGHT_M = 0.30

# Defaults chosen from the supplied capture and kept as parameters so another
# scene can override them. They are spatial scales, not measurements of this
# room; `make objects` prints the values in force.
DEFAULTS = {
    "voxel_m": 0.03,
    # The splat surface is about 2.6 cm thick (rms 1.3 cm on the floor). A band
    # narrower than that cuts through the slab and leaves a shell of the same
    # surface behind, which keeps the room connected: measured on the supplied
    # capture, a 2.5 cm band left components 3.8 times larger than a 4 cm band
    # with the same number of planes.
    "plane_distance_m": 0.04,
    "planes_max": 16,
    "planes_horizontal_max": 8,
    "planes_vertical_max": 8,
    "plane_min_fraction": 0.01,
    "plane_removal": "gated",
    "plane_vertical_removal": "band",
    "plane_sample": 40_000,
    "plane_iterations": 400,
    # Planes are proposed from each gaussian's own normal as well as from
    # three-point draws. 400 draws on a 60k sample never found a wall: a wall
    # holds a few percent of the points, so it is rarely drawn, while a
    # normal-guided draw lands on it whenever the sampled point is on it.
    "plane_normal_draws": 1_200,
    "plane_score_points": 8_000,
    "plane_normal_agreement": 0.8,
    # The column test: points of a cell, projected through the plane, must be a
    # thin sheet inside the band. Measured against the band removes 84 percent
    # of the floor and 14 percent of the machine's cross section.
    "plane_column_cell_m": 0.05,
    "plane_column_window_m": 0.12,
    "plane_column_share": 0.7,
    "plane_column_min_points": 3,
    # Gaussians are close to isotropic (median thin/middle size ratio 0.53), so
    # a single gaussian's thinnest axis is a poor normal: only 46 percent of the
    # floor's gaussians agree with straight up within 37 degrees, against 78
    # percent for the same normals pooled per 8 cm voxel.
    "normal_pool_m": 0.08,
    "min_points": 60,
    "split_points": 12_000,
    "split_target": 6_000,
    "split_max_extent_m": 3.0,
    "split_allow_quota": True,
    # Two components are bands of one instance when their heights leave at most
    # this gap and their floor footprints coincide: a band has the same
    # footprint as the shape it was cut from.
    # A component over the size limits can be peeled of room-sized sheets before
    # it is split, for a wall the global pass could not reach. Measured on the
    # supplied equipment capture it changed neither the mean anchor error nor the
    # fragment count, so it is off: a pass that costs runtime and does not move a
    # measured number stays a parameter, not a default.
    "peel_sheet_share": 0.0,
    "peel_sheet_min_m": 1.0,
    "merge_gap_m": 0.10,
    "merge_footprint_share": 0.6,
    "merge_containment_share": 0.6,
    "merge_span_m": 2.4,
    # A box whose bottom lands this close above the floor is standing on it, and
    # the planes removed the last few centimetres of its feet.
    "floor_snap_m": 0.08,
    "max_objects": 150,
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
    """A plane n . p + d = 0 with its support on the full cloud.

    `inliers` is the number of gaussians the plane removes, which is the number
    the stage reports. `band_inliers` is the distance-only count, so the
    difference between the two is what the normal and flatness tests kept.
    """

    normal: list[float]
    offset: float
    inliers: int
    rms_m: float
    horizontal: bool
    kind: str = "unknown"
    band_inliers: int = 0
    normal_inliers: int = 0
    flat_inliers: int = 0

    def distance(self, points: np.ndarray) -> np.ndarray:
        return points @ np.asarray(self.normal, dtype=np.float64) + self.offset


def _fit_plane_lsq(points: np.ndarray, limit: int = 60_000) -> tuple[np.ndarray, float, float]:
    """Least squares plane through points. Returns (normal, offset, rms).

    The fit is decimated to a fixed subset above `limit` points: a plane's two
    directions are already settled by a sixty thousand point sample of a floor,
    and the SVD on half a million rows is the slowest step in the stage.
    """
    if points.shape[0] > limit:
        picks = np.linspace(0, points.shape[0] - 1, limit).astype(np.int64)
        points = points[picks]
    centroid = points.mean(axis=0)
    centred = points - centroid
    # The smallest principal direction of the covariance is the normal.
    _, _, vt = np.linalg.svd(centred, full_matrices=False)
    normal = vt[-1]
    normal = normal / float(np.linalg.norm(normal))
    offset = -float(normal @ centroid)
    rms = float(np.sqrt(np.mean((centred @ normal) ** 2)))
    return normal, offset, rms


def gaussian_normals(scene: Scene) -> np.ndarray | None:
    """Unit surface normal per gaussian: its rotated thinnest ellipsoid axis.

    A gaussian is an ellipsoid whose three axes are the columns of its rotation
    matrix, scaled by the three stored sizes, so the thinnest axis is the normal
    of the sheet it was fitted to. This is the gaussian's own normal, before any
    pooling. Returns None for an artifact that carries no rotations, and the
    plane removal then relies on the flatness test alone.
    """
    if scene.rot is None:
        return None
    rotation = np.asarray(scene.rot, dtype=np.float64)
    w, x, y, z = (rotation[:, index] for index in range(4))
    thin = np.argmin(np.asarray(scene.size, dtype=np.float64), axis=1)
    normals = np.empty((rotation.shape[0], 3), dtype=np.float64)
    # Only the column at the thinnest axis is needed, so each third of the
    # gaussians gets its own column formula rather than a full 3x3 matrix.
    columns = {
        0: (1.0 - 2.0 * (y * y + z * z), 2.0 * (x * y + z * w), 2.0 * (x * z - y * w)),
        1: (2.0 * (x * y - z * w), 1.0 - 2.0 * (x * x + z * z), 2.0 * (y * z + x * w)),
        2: (2.0 * (x * z + y * w), 2.0 * (y * z - x * w), 1.0 - 2.0 * (x * x + y * y)),
    }
    for column, parts in columns.items():
        mask = thin == column
        if not mask.any():
            continue
        for axis in range(3):
            normals[mask, axis] = parts[axis][mask]
    length = np.linalg.norm(normals, axis=1, keepdims=True)
    return normals / np.maximum(length, 1e-12)


def pooled_normals(xyz: np.ndarray, normals: np.ndarray, voxel: float) -> np.ndarray:
    """The dominant normal direction of each gaussian's voxel.

    A gaussian whose three sizes are nearly equal cannot resolve its own normal,
    and most of them cannot: the median thin/middle ratio on the supplied
    capture is 0.53. The dominant eigenvector of the summed n n^T of a voxel's
    gaussians is orientation-free, so it recovers the surface the individual
    normals scatter around. Measured on the floor, agreement with straight up
    within 37 degrees rises from 46 percent per gaussian to 78 percent pooled.
    """
    xyz = np.asarray(xyz, dtype=np.float64)
    normals = np.asarray(normals, dtype=np.float64)
    indices = np.floor((xyz - xyz.min(axis=0)) / voxel).astype(np.int64)
    dims = indices.max(axis=0) + 1
    keys = (indices[:, 0] * dims[1] + indices[:, 1]) * dims[2] + indices[:, 2]
    _, inverse = np.unique(keys, return_inverse=True)
    inverse = inverse.reshape(-1).astype(np.int64)
    count = int(inverse.max()) + 1 if inverse.size else 0
    weight = np.maximum(np.bincount(inverse, minlength=count), 1)
    outward = np.stack(
        [
            np.bincount(inverse, weights=normals[:, 0] * normals[:, 0], minlength=count),
            np.bincount(inverse, weights=normals[:, 1] * normals[:, 1], minlength=count),
            np.bincount(inverse, weights=normals[:, 2] * normals[:, 2], minlength=count),
            np.bincount(inverse, weights=normals[:, 0] * normals[:, 1], minlength=count),
            np.bincount(inverse, weights=normals[:, 0] * normals[:, 2], minlength=count),
            np.bincount(inverse, weights=normals[:, 1] * normals[:, 2], minlength=count),
        ],
        axis=1,
    ) / weight[:, None]
    tensor = np.zeros((count, 3, 3), dtype=np.float64)
    tensor[:, 0, 0] = outward[:, 0]
    tensor[:, 1, 1] = outward[:, 1]
    tensor[:, 2, 2] = outward[:, 2]
    tensor[:, 0, 1] = tensor[:, 1, 0] = outward[:, 3]
    tensor[:, 0, 2] = tensor[:, 2, 0] = outward[:, 4]
    tensor[:, 1, 2] = tensor[:, 2, 1] = outward[:, 5]
    # Power iteration on a symmetric 3x3: the dominant eigenvector of a mean of
    # outer products converges in a handful of steps, and a batched LAPACK call
    # over half a million tiny matrices costs more than the rest of the stage.
    direction = np.full((count, 3), 1.0 / math.sqrt(3.0), dtype=np.float64)
    for _ in range(8):
        direction = np.einsum("ij,ijk->ik", direction, tensor)
        length = np.linalg.norm(direction, axis=1, keepdims=True)
        flat = length[:, 0] < 1e-12
        direction = np.where(flat[:, None], np.array([1.0, 0.0, 0.0]), direction / np.maximum(length, 1e-12))
    return direction[inverse]


def _flat_columns(
    xyz: np.ndarray,
    normal: np.ndarray,
    offset: float,
    *,
    threshold: float,
    cell: float,
    window: float,
    share: float,
    min_points: int,
) -> np.ndarray:
    """Points whose column through the plane is a thin sheet inside the band.

    The scene is projected onto the plane, one point per cell, and the column of
    everything within `window` of the plane is measured. A surface that lies in
    the plane, a floor or a wall, fills the window with points inside the band.
    A machine face crossed by the band does not: its column continues above and
    below, so only the band's share of it is in the band.
    """
    if not 0.0 < share <= 1.0 or window <= threshold or cell <= 0.0:
        return np.zeros(xyz.shape[0], dtype=bool)
    helper = np.array([1.0, 0.0, 0.0]) if abs(float(normal[0])) < 0.9 else np.array([0.0, 1.0, 0.0])
    first = np.cross(normal, helper)
    first = first / float(np.linalg.norm(first))
    second = np.cross(normal, first)
    distance = xyz @ normal + offset
    flat = np.zeros(xyz.shape[0], dtype=bool)
    # Only the column of points within the window can change an answer, and on a
    # room sized plane that is a tenth of the cloud.
    near = np.flatnonzero(np.abs(distance) < window)
    if near.size < min_points:
        return flat
    band = np.abs(distance[near]) < threshold
    along_first = xyz[near] @ first
    along_second = xyz[near] @ second
    column_first = np.floor((along_first - along_first.min()) / cell).astype(np.int64)
    column_second = np.floor((along_second - along_second.min()) / cell).astype(np.int64)
    keys = column_first * (int(column_second.max()) + 1) + column_second
    cells = int(keys.max()) + 1
    total = np.bincount(keys, minlength=cells)
    inside = np.bincount(keys[band], minlength=cells)
    fraction = inside / np.maximum(total, 1)
    flat[near] = (fraction[keys] >= share) & (total[keys] >= min_points)
    return flat


def plane_removal_mask(
    xyz: np.ndarray,
    normal: np.ndarray,
    offset: float,
    *,
    threshold: float,
    normals: np.ndarray | None = None,
    agreement: float = 0.8,
    cell: float = 0.05,
    window: float = 0.12,
    share: float = 0.7,
    min_points: int = 3,
) -> tuple[np.ndarray, dict]:
    """Which gaussians belong to a plane surface, and why.

    A gaussian is removed only when it is inside the band and one of two
    independent tests says the surface it belongs to is this plane:

    - `normal`: its own surface normal, or the voxel-pooled normal when the
      caller supplies pooled ones, agrees with the plane normal;
    - `flat`: the column of points through it is a thin sheet in the band.

    Either test on its own is necessary but not sufficient in practice. The
    per-gaussian normal is noisy on a capture whose gaussians are close to
    isotropic, so a normal-only gate leaves a third of the floor behind. The
    flatness test alone is what makes a material label look like a plane. Tested
    together, each covers the other's blind spot, and neither can cut a machine
    in half: a normal that disagrees and a column that is not flat both say the
    points are part of an object.
    """
    direction = np.asarray(normal, dtype=np.float64)
    direction = direction / max(float(np.linalg.norm(direction)), 1e-12)
    offset = float(offset)
    band = np.abs(xyz @ direction + offset) < threshold
    stats = {"band_inliers": int(band.sum()), "normal_inliers": 0, "flat_inliers": 0, "removed": 0}
    removed = np.zeros(xyz.shape[0], dtype=bool)
    if normals is not None:
        agrees = np.abs(np.asarray(normals, dtype=np.float64) @ direction) >= agreement
        removed |= band & agrees
        stats["normal_inliers"] = int((band & agrees).sum())
    flat = _flat_columns(
        xyz,
        direction,
        offset,
        threshold=threshold,
        cell=cell,
        window=window,
        share=share,
        min_points=min_points,
    )
    removed |= band & flat
    stats["flat_inliers"] = int((band & flat).sum())
    stats["removed"] = int(removed.sum())
    return removed, stats


def _plane_candidates(
    points: np.ndarray,
    normals: np.ndarray | None,
    *,
    iterations: int,
    normal_draws: int,
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray]:
    """Proposed plane normals and offsets: normal-guided draws and triangles.

    A normal-guided draw is the plane through a sampled point with that point's
    own normal, which is a native candidate for the surface the point was
    reconstructed from, so a wall is proposed whenever a wall point is drawn. The
    three-point draws are kept as the fallback for a surface whose normals are
    unreliable. Both are deterministic for a given rng.
    """
    count = points.shape[0]
    proposals: list[np.ndarray] = []
    offsets: list[np.ndarray] = []
    if normals is not None and normal_draws > 0:
        picks = rng.integers(0, count, size=normal_draws)
        candidate = normals[picks]
        proposals.append(candidate)
        offsets.append(-np.einsum("ij,ij->i", points[picks], candidate))
    if iterations > 0:
        picks = rng.integers(0, count, size=(iterations, 3))
        first = points[picks[:, 0]]
        second = points[picks[:, 1]] - first
        third = points[picks[:, 2]] - first
        candidate = np.cross(second, third)
        length = np.linalg.norm(candidate, axis=1)
        good = length > 1e-9
        if good.any():
            candidate = candidate[good] / length[good, None]
            proposals.append(candidate)
            offsets.append(-np.einsum("ij,ij->i", points[picks[good, 0]], candidate))
    if not proposals:
        return np.zeros((0, 3), dtype=np.float64), np.zeros(0, dtype=np.float64)
    return np.concatenate(proposals, axis=0), np.concatenate(offsets, axis=0)


def score_plane_candidates(
    points: np.ndarray,
    normals: np.ndarray | None,
    candidates: np.ndarray,
    offsets: np.ndarray,
    *,
    threshold: float,
    agreement: float,
) -> np.ndarray:
    """The number of gaussians each candidate explains, gated like the removal.

    A plane's worth is measured with the same two tests that decide a removal,
    so a candidate that would be refused by the gate cannot win a search. The
    work is bounded by the caller's points: `find_planes` scores everything on a
    small subset first and only rescores the shortlist on the larger one.
    """
    scores = np.zeros(candidates.shape[0], dtype=np.int64)
    if candidates.shape[0] == 0 or points.shape[0] == 0:
        return scores
    for start in range(0, candidates.shape[0], 64):
        block = candidates[start : start + 64]
        distance = np.abs(points @ block.T + offsets[start : start + 64])
        inside = distance < threshold
        if normals is not None:
            inside &= np.abs(normals @ block.T) >= agreement
        scores[start : start + block.shape[0]] = inside.sum(axis=0)
    return scores


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
    normals: np.ndarray | None = None,
    normal_draws: int = 1_200,
    agreement: float = 0.8,
    normal_pool_m: float = 0.08,
    score_points: int = 8_000,
    column_cell: float = 0.05,
    column_window: float = 0.12,
    column_share: float = 0.7,
    column_min_points: int = 3,
    horizontal_max: int = 8,
    vertical_max: int = 8,
    removal: str = "gated",
    vertical_removal: str = "band",
    pooled: np.ndarray | None = None,
) -> tuple[list[Plane], np.ndarray]:
    """Find and remove the dominant planes. Returns (planes, keep mask).

    Candidates come from a fixed decimated sample, both from three-point draws
    and from each sampled point's own normal, so a wall or a machine face is
    proposed as easily as the floor. The support is counted on the full cloud and
    every plane is refitted to its own gated inlier set, so the numbers reported
    are the numbers removed. A plane is only recorded when the gated support is
    at least `min_fraction` of the cloud, which is what keeps a machine top from
    being registered as a room plane.

    The horizontal and vertical families get their own budget. Measured on the
    equipment capture, an unlimited search spent its first eight planes on the
    ceiling clutter and never proposed a wall, which is how every wall stayed in
    the object pool and welded the room to the machine. A room has a handful of
    surfaces in each family, and one family taking the whole budget is the
    failure this split prevents.

    `removal` decides what an accepted horizontal plane takes out of the cloud,
    and `vertical_removal` the same for a vertical one:

    - "band": every gaussian inside the band, which is the clean removal. The
      normal and flatness counts are still measured and reported, and they are
      what qualifies the plane, but a plane does not leave a sparse shell of
      itself behind. A sparse shell at a third of the capture's density is still
      connected at a 3 cm voxel, and measured on the equipment capture it welds
      every object that touches a wall into one component.
    - "gated": only the gaussians the two tests claim, which keeps a machine's
      side surface out of a horizontal plane but leaves the shell described
      above.

    The defaults differ by family because the two families fail differently.
    A horizontal plane crossing an object cuts it in two, so its removal is
    gated and the machine keeps its side surface. A vertical plane is a wall, and
    a wall that is only partly removed is a connected sheet that welds every
    object standing against it into one component: measured on the equipment
    capture the largest component fell from 24 percent of the capture to a
    handful of objects once walls were removed whole.
    """
    rng = np.random.default_rng(seed)
    total = xyz.shape[0]
    sample_index = np.sort(rng.choice(total, size=min(sample_points, total), replace=False))
    sample = xyz[sample_index].astype(np.float64)
    if pooled is not None:
        search_normals = pooled
    else:
        search_normals = None if normals is None else pooled_normals(xyz, normals, normal_pool_m)
    # A capture whose gaussians all share one orientation carries no per-gaussian
    # surface normal: the mean unit normal is that shared direction, and a gate
    # built on it would refuse every plane that is not perpendicular to it. The
    # proposals then rank on distance alone and the flatness test still decides a
    # removal, so a capture like that is segmented rather than skipped.
    scoring_normals = search_normals
    if search_normals is not None:
        average = np.linalg.norm(search_normals.mean(axis=0))
        if average > 0.9:
            scoring_normals = None
    sample_normals = None if search_normals is None else search_normals[sample_index]
    sample_remaining = np.ones(sample.shape[0], dtype=bool)
    keep = np.ones(total, dtype=bool)
    planes: list[Plane] = []
    horizontal_count = 0
    vertical_count = 0

    for _ in range(max_planes):
        pool = sample[sample_remaining]
        if pool.shape[0] < 100:
            break
        allow_horizontal = horizontal_count < int(horizontal_max)
        allow_vertical = vertical_count < int(vertical_max)
        if not allow_horizontal and not allow_vertical:
            break
        pool_normals = None if scoring_normals is None else scoring_normals[sample_index][sample_remaining]
        take = min(pool.shape[0], max(1, int(score_points)))
        score_index = np.linspace(0, pool.shape[0] - 1, take).astype(np.int64)
        candidates, offsets = _plane_candidates(
            pool,
            pool_normals,
            iterations=iterations,
            normal_draws=normal_draws,
            rng=rng,
        )
        if candidates.shape[0] == 0:
            break
        # A family at its budget is filtered out before the shortlist, not after
        # it: the shortlist is ordered by score, and the clutter that exhausts a
        # family also fills the top of that order.
        flat_family = np.abs(candidates @ up) > 0.85
        usable = np.flatnonzero(np.where(flat_family, allow_horizontal, allow_vertical))
        if usable.size == 0:
            break
        candidates = candidates[usable]
        offsets = offsets[usable]
        short_index = np.linspace(0, pool.shape[0] - 1, min(pool.shape[0], 2_500)).astype(np.int64)
        short_scores = score_plane_candidates(
            pool[short_index],
            None if pool_normals is None else pool_normals[short_index],
            candidates,
            offsets,
            threshold=threshold,
            agreement=agreement,
        )
        shortlisted = np.argsort(short_scores)[::-1][:32]
        rescored = score_plane_candidates(
            pool[score_index],
            None if pool_normals is None else pool_normals[score_index],
            candidates[shortlisted],
            offsets[shortlisted],
            threshold=threshold,
            agreement=agreement,
        )
        best = int(shortlisted[int(np.argmax(rescored))])
        normal = candidates[best]
        offset = float(offsets[best])
        # Straighten the proposal on the full cloud before the gated count, so a
        # candidate that came from one noisy normal still lands on the plane.
        for _ in range(2):
            band = np.abs(xyz @ normal + offset) < threshold
            if int(band.sum()) < 3:
                break
            normal, offset, _ = _fit_plane_lsq(xyz[band])
        removed, stats = plane_removal_mask(
            xyz,
            normal,
            offset,
            threshold=threshold,
            normals=search_normals,
            agreement=agreement,
            cell=column_cell,
            window=column_window,
            share=column_share,
            min_points=column_min_points,
        )
        horizontal = abs(float(normal @ up)) > 0.85
        mode = removal if horizontal else vertical_removal
        # The support that decides whether a plane is worth removing is the
        # support its own family is removed on: a wall is justified by how much
        # of it is there, a horizontal plane by how much of it is a surface.
        support = stats["band_inliers"] if mode == "band" else stats["removed"]
        if support < max(3, min_fraction * total):
            break
        # One refit on the gated set, then count again: the reported plane is the
        # plane whose removal is reported.
        normal, offset, _ = _fit_plane_lsq(xyz[removed])
        removed, stats = plane_removal_mask(
            xyz,
            normal,
            offset,
            threshold=threshold,
            normals=search_normals,
            agreement=agreement,
            cell=column_cell,
            window=column_window,
            share=column_share,
            min_points=column_min_points,
        )
        if mode == "band":
            removed = np.abs(xyz @ normal + offset) < threshold
        inlier_count = int(removed.sum())
        if inlier_count < max(3, min_fraction * total):
            break
        normal, offset, _ = _fit_plane_lsq(xyz[removed])
        rms = float(np.sqrt(np.mean((xyz[removed] @ normal + offset) ** 2)))
        if horizontal:
            horizontal_count += 1
        else:
            vertical_count += 1
        planes.append(
            Plane(
                normal=[round(float(v), 6) for v in normal],
                offset=round(float(offset), 6),
                inliers=int(inlier_count),
                rms_m=round(float(rms), 5),
                horizontal=bool(horizontal),
                kind="horizontal" if horizontal else "vertical",
                band_inliers=int(stats["band_inliers"]),
                normal_inliers=int(stats["normal_inliers"]),
                flat_inliers=int(stats["flat_inliers"]),
            )
        )
        inlier_count = int(removed.sum())
        keep &= ~removed
        # Take the band out of the sample pool as well, so the same surface is
        # not proposed again a centimetre away from where it was just removed.
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


def floor_plane_for(scene: Scene, planes: list[Plane], up: np.ndarray) -> Plane | None:
    """The horizontal plane at the floor the ingest detected.

    The largest horizontal plane is often the ceiling: it carries the services
    and can hold more points than the floor. The scene metadata records which
    slab is the floor, so pick that plane and fall back to the largest one only
    when the metadata has nothing.
    """
    frame = scene.meta.get("frame", {})
    slab = frame.get("floor_slab")
    axis = frame.get("up_axis_index")
    candidates = [p for p in planes if p.horizontal]
    if slab is None or axis is None or not candidates:
        return floor_plane(planes, up)
    along = [p for p in candidates if abs(float(np.asarray(p.normal)[axis])) > 1e-6]
    if not along:
        return floor_plane(planes, up)
    return min(along, key=lambda p: abs(-p.offset / float(np.asarray(p.normal)[axis]) - float(slab)))


def estimate_spacing(
    xyz: np.ndarray,
    planes: list[Plane],
    up: np.ndarray,
    *,
    threshold: float,
    cell: float = 0.05,
) -> dict:
    """Estimate the distance between neighbouring points from the floor.

    The largest flat surface in a capture is the most reliable density sample it
    contains: its area can be measured directly by counting occupied cells, so
    points divided by area gives a density and the square root of its inverse is
    the spacing. Returns a record with the numbers and the method, so the voxel
    size chosen from it can be explained.
    """
    floor = floor_plane(planes, up)
    if floor is None:
        return {"spacing_m": None, "method": "no floor plane, the requested voxel size stands"}
    normal = np.asarray(floor.normal, dtype=np.float64)
    distance = np.abs(xyz @ normal + floor.offset)
    mask = distance < max(threshold, 0.03)
    points = xyz[mask]
    if points.shape[0] < 500:
        return {
            "spacing_m": None,
            "floor_points": int(points.shape[0]),
            "method": "too few floor points to measure a spacing",
        }
    helper = np.array([1.0, 0.0, 0.0]) if abs(normal[0]) < 0.9 else np.array([0.0, 1.0, 0.0])
    tangent = np.cross(normal, helper)
    tangent = tangent / float(np.linalg.norm(tangent))
    second = np.cross(normal, tangent)
    u = points @ tangent
    v = points @ second
    cells_u = np.floor((u - u.min()) / cell).astype(np.int64)
    cells_v = np.floor((v - v.min()) / cell).astype(np.int64)
    keys = np.unique(cells_u * (int(cells_v.max()) + 1) + cells_v)
    area = float(keys.size) * cell * cell
    density = float(points.shape[0]) / max(area, 1e-9)
    spacing = 1.0 / math.sqrt(density)
    return {
        "spacing_m": round(spacing, 4),
        "floor_points": int(points.shape[0]),
        "floor_area_m2": round(area, 2),
        "density_per_m2": round(density, 1),
        "cell_m": cell,
        "method": "points within 3 cm of the floor plane, divided by the occupied cell area",
    }


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
    # int32 labels and the index form of the minimum keep the round cost down:
    # this loop is the single most expensive part of the stage on a capture with
    # hundreds of thousands of occupied voxels.
    neighbour = np.full((n, len(HALF_NEIGHBOURS)), -1, dtype=np.int32)
    index = np.arange(n, dtype=np.int32)
    for column, (dx, dy, dz) in enumerate(HALF_NEIGHBOURS):
        delta = (dx * d1 + dy) * d2 + dz
        candidate = np.searchsorted(keys, keys + delta).astype(np.int32)
        clipped = np.minimum(candidate, n - 1)
        found = (candidate < n) & (keys[clipped] == keys + delta)
        # Fill both directions of the edge: the propagation reads one neighbour
        # table, so a voxel must see the neighbour that is below it as well.
        neighbour[found, column] = candidate[found]
        neighbour[candidate[found], column] = index[found]

    labels = np.arange(n, dtype=np.int32)
    for _ in range(64):
        updated = labels.copy()
        for column in range(neighbour.shape[1]):
            other = neighbour[:, column]
            np.minimum(updated, np.where(other >= 0, labels[np.maximum(other, 0)], updated), out=updated)
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


def _tighten_pair(points: np.ndarray, axes: np.ndarray, first: int, second: int) -> np.ndarray:
    """Rotate two box axes in their plane to the tightest rectangle.

    The third axis is untouched, so this is a rotation about it. Returns the
    axes with the better pair. Used only when the covariance cannot choose the
    rotation itself, which is exactly the square cross section case.
    """
    local = points @ axes.T
    angles = np.linspace(0.0, np.pi / 2.0, 181, endpoint=False)
    cosine = np.cos(angles)[None, :]
    sine = np.sin(angles)[None, :]
    along_first = local[:, first][:, None]
    along_second = local[:, second][:, None]
    # Every angle at once: the widest pair of rotations is 181 small matrices,
    # and a Python loop over them is the slowest step in the stage once a capture
    # has hundreds of objects with a square cross section.
    rotated_first = along_first * cosine + along_second * sine
    rotated_second = -along_first * sine + along_second * cosine
    areas = (rotated_first.max(axis=0) - rotated_first.min(axis=0)) * (
        rotated_second.max(axis=0) - rotated_second.min(axis=0)
    )
    theta = float(angles[int(np.argmin(areas))])
    cosine, sine = math.cos(theta), math.sin(theta)
    tightened = axes.copy()
    tightened[first] = cosine * axes[first] + sine * axes[second]
    tightened[second] = -sine * axes[first] + cosine * axes[second]
    return tightened


def _upright_axes(points: np.ndarray, up: np.ndarray) -> np.ndarray:
    """A box frame with one axis on the up direction and the other two level.

    A floor standing object is framed upright, because the up direction is the
    one direction its box must respect. A free PCA frame tilts the box to the
    object's own diagonal, which is why a chair came out as a tilted
    parallelogram with a height nobody could see. The two level axes are the
    principal directions of the points projected onto the floor plane.
    """
    direction = np.asarray(up, dtype=np.float64)
    direction = direction / max(float(np.linalg.norm(direction)), 1e-12)
    helper = np.array([1.0, 0.0, 0.0]) if abs(float(direction[0])) < 0.9 else np.array([0.0, 1.0, 0.0])
    first = np.cross(direction, helper)
    first = first / max(float(np.linalg.norm(first)), 1e-12)
    second = np.cross(direction, first)
    level = np.stack([points @ first, points @ second], axis=1)
    level = level - level.mean(axis=0)
    values, vectors = np.linalg.eigh(level.T @ level / max(1, points.shape[0] - 1))
    order = np.argsort(values)[::-1]
    horizontal_first = first * vectors[0, order[0]] + second * vectors[1, order[0]]
    horizontal_second = first * vectors[0, order[1]] + second * vectors[1, order[1]]
    axes = np.stack([horizontal_first, horizontal_second, direction])
    if (values[order[0]] - values[order[1]]) / max(values[order[0]], 1e-12) < 0.1:
        axes = _tighten_pair(points, axes, 0, 1)
    return axes


def _extents(points: np.ndarray, up: np.ndarray | None = None) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Box frame plus robust extents of a point set.

    A box with a square cross section has two equal eigenvalues, so its PCA
    frame is degenerate: the two equal axes are free to spin and the box comes
    out wider than the points in it. When a pair of eigenvalues is that close,
    that pair is rotated to the tightest rectangle around the points instead.
    The extents are the 0.5th to 99.5th percentile on each axis, which keeps a
    stray gaussian out of the box without trimming the box short of its own
    points.

    Passing `up` asks for an upright frame, which is what a floor standing
    object gets: an object on the floor is framed with one axis on the up
    direction, because that is the one direction its box has to respect.
    """
    centroid = points.mean(axis=0)
    centred = points - centroid
    if up is not None:
        axes = _upright_axes(centred, np.asarray(up, dtype=np.float64))
    else:
        covariance = centred.T @ centred / max(1, points.shape[0] - 1)
        values, vectors = np.linalg.eigh(covariance)
        order = np.argsort(values)[::-1]
        values = values[order]
        axes = vectors[:, order].T

        if values[0] > 0 and (values[0] - values[1]) / values[0] < 0.1:
            axes = _tighten_pair(points - centroid, axes, 0, 1)
        if values[1] > 0 and (values[1] - values[2]) / values[1] < 0.1:
            axes = _tighten_pair(points - centroid, axes, 1, 2)

    # sign convention: the largest extent points along the dominant direction
    for row in range(3):
        dominant = int(np.argmax(np.abs(axes[row])))
        if axes[row, dominant] < 0:
            axes[row] = -axes[row]
    local = centred @ axes.T
    low = np.percentile(local, EXTENT_PERCENTILE, axis=0)
    high = np.percentile(local, 100.0 - EXTENT_PERCENTILE, axis=0)
    extents = high - low
    if up is not None:
        # The upright frame is ordered largest extent first, like the free one.
        order = np.argsort(extents)[::-1]
        axes = axes[order]
        low = low[order]
        high = high[order]
        extents = extents[order]
    centre = centroid + axes.T @ ((low + high) / 2.0)
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
    gap_m: float = SPLIT_GAP_M,
    neck_share: float = 0.35,
    allow_quota: bool = False,
    stats: dict | None = None,
    depth: int = 0,
) -> list[np.ndarray]:
    """Cut an oversized cluster only at a measured gap between two objects.

    A component over the size limits is cut along its longest axis at the widest
    run of empty coordinate bins when that run is at least `gap_m` wide: two rows
    of gaussians on one surface are millimetres apart, two objects are not. When
    there is no gap the cut goes at the thinnest cross section, and only when
    that section is at most `neck_share` of the profile's median: a machine
    joined to a pipe rack through a pipe is two objects joined by a neck, while
    a machine with no profile minimum at all stays whole. A target point count is
    never a reason to cut. Measured on the equipment capture, the old target-size cut turned
    the washing machine's neighbourhood into three boxes; a gap test finds none
    inside a machine. `target` is accepted so the parameters and the call sites
    stay stable, and it no longer forces a cut: a piece is cut from evidence,
    not from a quota. Returns index arrays into `points`.
    """
    whole = np.arange(points.shape[0])
    if depth >= 8:
        return [whole]
    if points.shape[0] <= max(40, int(target) // 4):
        return [whole]
    centre, axes, extents = _extents(points)
    if points.shape[0] <= max_points and float(extents.max()) <= max_extent:
        return [whole]

    direction = axes[int(np.argmax(extents))]
    coordinate = (points - centre) @ direction
    low, high = np.percentile(coordinate, [0.5, 99.5])
    if high - low <= max(1e-3, gap_m):
        return [whole]

    bins = max(6, int(math.ceil((high - low) / 0.05)))
    counts, edges = np.histogram(coordinate, bins=bins, range=(low, high))
    empty = np.flatnonzero(counts == 0)
    cut: float | None = None
    reason = "none"
    if empty.size:
        runs = np.split(empty, np.flatnonzero(np.diff(empty) > 1) + 1)
        interior = [run for run in runs if run[0] > 0 and run[-1] < bins - 1]
        if interior:
            widest = max(interior, key=lambda run: float(edges[run[-1] + 1] - edges[run[0]]))
            width = float(edges[widest[-1] + 1] - edges[widest[0]])
            if width >= gap_m:
                cut = float((edges[widest[0]] + edges[widest[-1] + 1]) / 2.0)
                reason = "gap"
    if cut is None:
        # No gap, so look for a neck: the thinnest cross section of the cluster.
        # Two machines joined by a pipe are joined through a neck, and cutting
        # there is a statement about the geometry rather than a quota: the
        # profile has to be at most `neck_share` of its own median.
        profile = counts.astype(np.float64)
        if profile.size < 5 or float(np.median(profile)) <= 0.0:
            return [whole]
        candidates = profile[1:-1]
        thinnest = int(np.argmin(candidates)) + 1
        if float(profile[thinnest]) > neck_share * float(np.median(profile)):
            if not allow_quota:
                return [whole]
            share = min(0.9, max(0.1, float(target) / max(1, points.shape[0])))
            cut = float(np.quantile(coordinate, share))
            reason = "quota"
        else:
            cut = float((edges[thinnest] + edges[thinnest + 1]) / 2.0)
            reason = "neck"

    left = np.flatnonzero(coordinate <= cut)
    right = np.flatnonzero(coordinate > cut)
    if not left.size or not right.size:
        return [whole]
    if stats is not None:
        stats[reason] = stats.get(reason, 0) + 1
    pieces: list[np.ndarray] = []
    for subset in (left, right):
        for piece in split_component(
            points[subset],
            target=target,
            max_points=max_points,
            max_extent=max_extent,
            gap_m=gap_m,
            neck_share=neck_share,
            allow_quota=allow_quota,
            stats=stats,
            depth=depth + 1,
        ):
            pieces.append(subset[piece])
    return pieces


def merge_stacked(
    points: np.ndarray,
    groups: list[np.ndarray],
    *,
    up: np.ndarray,
    gap_m: float,
    footprint_share: float,
    span_m: float,
    cell: float = 0.05,
    containment_share: float = 0.0,
) -> tuple[list[np.ndarray], dict]:
    """Join components that are stacked bands of one instance.

    A band fragment has the same floor footprint as the shape it was cut from
    and sits within a plane band of the next piece, so two components are joined
    when their heights leave at most `gap_m` between them, the smaller of the two
    floor footprints is `footprint_share` covered by the larger, and neither
    piece is wider than `span_m`. The footprint containment is what keeps two
    machines standing side by side apart, and the size cap is what keeps a chain
    of bands from rebuilding a room sized component. Returns the joined groups
    and a record of how many pairs were joined.
    """
    if not groups:
        return groups, {"components": 0, "components_after": 0, "pairs_joined": 0}
    helper = np.array([1.0, 0.0, 0.0]) if abs(float(up[0])) < 0.9 else np.array([0.0, 1.0, 0.0])
    first = np.cross(up, helper)
    first = first / max(float(np.linalg.norm(first)), 1e-12)
    second = np.cross(up, first)
    heights = points @ np.asarray(up, dtype=np.float64)
    along_first = points @ first
    along_second = points @ second
    low_row = np.floor((along_first - along_first.min()) / cell).astype(np.int64)
    second_row = np.floor((along_second - along_second.min()) / cell).astype(np.int64)
    keys = low_row * (int(second_row.max()) + 1) + second_row

    count = len(groups)
    owner = np.arange(count, dtype=np.int64)
    low = np.empty(count, dtype=np.float64)
    high = np.empty(count, dtype=np.float64)
    footprint: list[np.ndarray] = []
    for index, group in enumerate(groups):
        group_heights = heights[group]
        low[index] = float(group_heights.min())
        high[index] = float(group_heights.max())
        footprint.append(np.unique(keys[group]))

    def root(index: int) -> int:
        while owner[index] != index:
            owner[index] = owner[owner[index]]
            index = int(owner[index])
        return index

    reach = np.empty((count, 3), dtype=np.float64)
    for index, group in enumerate(groups):
        group_points = points[group]
        low_corner = group_points.min(axis=0)
        high_corner = group_points.max(axis=0)
        reach[index] = high_corner - low_corner

    joined = 0
    order = np.argsort(low, kind="stable")
    for position, index in enumerate(order):
        index = int(index)
        for other in order[position + 1 :]:
            other = int(other)
            if low[other] > high[index] + gap_m:
                break
            if low[other] < high[index] - 1e-9:
                continue
            first_root, other_root = root(index), root(other)
            if first_root == other_root:
                continue
            smaller = min(footprint[index].size, footprint[other].size)
            if smaller < 1:
                continue
            shared = int(np.intersect1d(footprint[index], footprint[other], assume_unique=True).size)
            # The smaller footprint has to sit inside the larger one: a machine's
            # top and its front panel do, two machines side by side do not.
            if shared < footprint_share * smaller:
                continue
            if containment_share > 0.0 and shared < containment_share * max(footprint[index].size, footprint[other].size):
                continue
            # The union has to stay the size of one instance, measured on the
            # pieces' own world extents, so a merge cannot rebuild a room.
            if float(reach[index].max()) > span_m or float(reach[other].max()) > span_m:
                continue
            owner[max(first_root, other_root)] = min(first_root, other_root)
            reach[index] = reach[index] + reach[other]
            reach[other] = reach[index]
            joined += 1

    merged: list[np.ndarray] = []
    seen: dict[int, list[int]] = {}
    for index in range(count):
        seen.setdefault(root(index), []).append(index)
    for members in seen.values():
        if len(members) == 1:
            merged.append(groups[members[0]])
        else:
            merged.append(np.concatenate([groups[member] for member in members]))
    merged.sort(key=lambda group: group.size, reverse=True)
    return merged, {"components": count, "components_after": len(merged), "pairs_joined": joined}


def _sheet_span(points: np.ndarray, normal: np.ndarray) -> float:
    """The smaller of a sheet's two in-plane extents, in metres."""
    helper = np.array([1.0, 0.0, 0.0]) if abs(float(normal[0])) < 0.9 else np.array([0.0, 1.0, 0.0])
    first = np.cross(normal, helper)
    first = first / max(float(np.linalg.norm(first)), 1e-12)
    second = np.cross(normal, first)
    along_first = points @ first
    along_second = points @ second
    span_first = float(np.percentile(along_first, 98.0) - np.percentile(along_first, 2.0))
    span_second = float(np.percentile(along_second, 98.0) - np.percentile(along_second, 2.0))
    return min(span_first, span_second)


def peel_component(
    points: np.ndarray,
    pooled: np.ndarray | None,
    *,
    up: np.ndarray,
    threshold: float,
    voxel: float,
    max_points: int,
    max_extent: float,
    min_points: int,
    sheet_share: float,
    sheet_min_m: float,
    iterations: int,
    seed: int,
    depth: int = 0,
    max_depth: int = 2,
) -> tuple[list[np.ndarray], dict]:
    """Remove room-sized sheets from an oversized component until it breaks up.

    A wall that stayed welded to a machine is a plane *inside* that component,
    and it is far below the global support floor once the rest of the wall has
    been removed. This pass fits the best plane in the component itself, so the
    support test is a share of the component rather than of the capture, and a
    wall holding a fifth of the component qualifies. The sheet has to be at least
    `sheet_min_m` across, which is what separates a room surface from a machine's
    own face: the machine's top is half a metre wide and is left alone.

    The search runs on a decimated sample of the component and only the winning
    plane's mask is applied to all of it, which keeps a local pass cheap enough
    to run on every oversized component. Returns index arrays into `points` for
    the surviving pieces, and a record of what was peeled. The removed sheet
    points are not returned: they are the room surface the global pass could not
    reach, not objects.
    """
    whole = [np.arange(points.shape[0])]
    record = {"components": 1, "sheets": 0, "points_removed": 0}
    if depth >= max_depth:
        return whole, record
    count = points.shape[0]
    if count <= max_points and float(_extents(points)[2].max()) <= max_extent:
        return whole, record
    if count < max(4 * min_points, 120):
        return whole, record
    take = min(count, 20_000)
    sample_index = np.linspace(0, count - 1, take).astype(np.int64)
    sample = points[sample_index]
    sample_pooled = None if pooled is None else pooled[sample_index]
    planes, _ = find_planes(
        sample,
        up=up,
        threshold=threshold,
        max_planes=1,
        min_fraction=sheet_share,
        sample_points=min(take, 20_000),
        iterations=iterations,
        seed=seed,
        normals=None,
        pooled=sample_pooled,
        normal_draws=min(600, max(64, take // 20)),
        agreement=0.8,
        column_cell=0.05,
        column_window=0.12,
        column_share=0.7,
        column_min_points=3,
        horizontal_max=1,
        vertical_max=1,
        removal="gated",
    )
    if not planes:
        return whole, record
    direction = np.asarray(planes[0].normal, dtype=np.float64)
    removed, _ = plane_removal_mask(
        points,
        direction,
        float(planes[0].offset),
        threshold=threshold,
        normals=pooled,
        agreement=0.8,
        cell=0.05,
        window=0.12,
        share=0.7,
        min_points=3,
    )
    removed_points = int(removed.sum())
    if removed_points < max(4 * min_points, int(sheet_share * count)):
        return whole, record
    if _sheet_span(points[removed], direction) < sheet_min_m:
        return whole, record
    keep = ~removed
    rest = np.flatnonzero(keep)
    if rest.size < 3:
        return [], record
    keys, inverse, dims = voxel_indices(points[rest], voxel)
    groups = component_points(keys, dims, inverse)
    pieces: list[np.ndarray] = []
    record = {"components": len(groups), "sheets": 1, "points_removed": removed_points}
    for group in groups:
        subset = rest[group]
        sub_pieces, sub_record = peel_component(
            points[subset],
            None if pooled is None else pooled[subset],
            up=up,
            threshold=threshold,
            voxel=voxel,
            max_points=max_points,
            max_extent=max_extent,
            min_points=min_points,
            sheet_share=sheet_share,
            sheet_min_m=sheet_min_m,
            iterations=iterations,
            seed=seed,
            depth=depth + 1,
            max_depth=max_depth,
        )
        record["sheets"] += sub_record["sheets"]
        record["points_removed"] += sub_record["points_removed"]
        for piece in sub_pieces:
            pieces.append(subset[piece])
    return pieces, record


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
    bottom_above_floor: float = 0.0
    floor_snapped: bool = False

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
            "bottom_above_floor": payload["bottom_above_floor"],
            "floor_snapped": payload["floor_snapped"],
            "volume_m3": payload["volume_m3"],
            "planarity": payload["planarity"],
        }


def build_object(
    index: int,
    points: np.ndarray,
    *,
    up: np.ndarray,
    floor: Plane | None,
    snap_m: float = 0.08,
    clamp_m: float = 0.35,
) -> Object:
    """One oriented box around a cluster, completed to the floor when it stands on it.

    A machine standing on the floor loses its lowest gaussian layer to the floor
    plane, so its fitted box starts a few centimetres up and the audit reads a
    floating band. A capture also contains points a little below the measured
    floor, which pulls the fitted bottom under it. For an object whose own points
    reach the floor, the floor is the support, so the box's lowest corner is put
    on the floor: down when the bottom is within `snap_m` above it, up when it is
    within `clamp_m` below it. The centre moves by half the change so the top of
    the box does not move. Nothing is invented: an object that does not reach the
    floor keeps the bottom its own points gave it.
    """
    standing = False
    if floor is not None and points.shape[0] > 1:
        heights = height_above_plane(points, floor, up)
        lowest = float(np.percentile(heights, EXTENT_PERCENTILE))
        highest = float(np.percentile(heights, 100.0 - EXTENT_PERCENTILE))
        # A box stands on the floor and is tall enough for its uprightness to
        # matter. A pipe on the floor, a pallet, a strip of cable: free frame.
        standing = lowest <= STANDING_M and highest - lowest >= STANDING_HEIGHT_M
    centre, axes, extents = _extents(points, up=up if standing else None)
    if floor is not None:
        height = float(height_above_plane(centre[None, :], floor, up)[0])
    else:
        height = float(centre @ up)
    span = float(np.sum(np.abs(axes @ up) * extents))
    bottom = height - span / 2.0
    snapped = False
    if floor is not None and standing and -clamp_m < bottom <= snap_m:
        vertical_axis = int(np.argmax(np.abs(axes @ up)))
        alignment = abs(float(axes[vertical_axis] @ up))
        if alignment > 0.5:
            extents = extents.copy()
            extents[vertical_axis] += bottom / alignment
            centre = centre - np.asarray(up, dtype=np.float64) * (bottom / 2.0)
            height = float(height_above_plane(centre[None, :], floor, up)[0])
            bottom = 0.0
            snapped = True
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
        bottom_above_floor=round(float(bottom), 3),
        floor_snapped=bool(snapped),
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

    normals = gaussian_normals(scene)
    pooled_all = None if normals is None else pooled_normals(xyz, normals, float(options["normal_pool_m"]))
    planes, keep = find_planes(
        xyz,
        up=up,
        threshold=float(options["plane_distance_m"]),
        max_planes=int(options["planes_max"]),
        min_fraction=float(options["plane_min_fraction"]),
        sample_points=int(options["plane_sample"]),
        iterations=int(options["plane_iterations"]),
        seed=int(options["seed"]),
        normals=normals,
        normal_draws=int(options["plane_normal_draws"]),
        agreement=float(options["plane_normal_agreement"]),
        normal_pool_m=float(options["normal_pool_m"]),
        score_points=int(options["plane_score_points"]),
        column_cell=float(options["plane_column_cell_m"]),
        column_window=float(options["plane_column_window_m"]),
        column_share=float(options["plane_column_share"]),
        column_min_points=int(options["plane_column_min_points"]),
        horizontal_max=int(options["planes_horizontal_max"]),
        vertical_max=int(options["planes_vertical_max"]),
        removal=str(options["plane_removal"]),
        vertical_removal=str(options["plane_vertical_removal"]),
        pooled=pooled_all,
    )
    floor = floor_plane_for(scene, planes, up)
    removed_points = int((~keep).sum())
    remaining = xyz[keep]
    if remaining.shape[0] < 3:
        raise ValueError("every point was removed as a plane; the plane threshold is too wide")

    spacing = estimate_spacing(xyz, planes, up, threshold=float(options["plane_distance_m"]))
    voxel = float(options["voxel_m"])
    if spacing["spacing_m"]:
        voxel = max(voxel, VOXEL_PER_SPACING * float(spacing["spacing_m"]))
    voxel = round(voxel, 4)

    keys, inverse, dims = voxel_indices(remaining, voxel)
    groups = component_points(keys, dims, inverse)
    component_count = len(groups)

    kept_groups: list[np.ndarray] = []
    dropped_small = 0
    for group in groups:
        if group.size < int(options["min_points"]):
            dropped_small += 1
            continue
        kept_groups.append(group)

    pieces: list[np.ndarray] = []
    peel_stats = {"components": 0, "sheets": 0, "points_removed": 0}
    pooled = None if pooled_all is None else pooled_all[keep]
    for group in kept_groups:
        group_points = remaining[group]
        if (
            group.size <= int(options["split_points"])
            and float(_extents(group_points)[2].max()) <= float(options["split_max_extent_m"])
        ):
            pieces.append(group)
            continue
        peeled, record = peel_component(
            group_points,
            None if pooled is None else pooled[group],
            up=up,
            threshold=float(options["plane_distance_m"]),
            voxel=voxel,
            max_points=int(options["split_points"]),
            max_extent=float(options["split_max_extent_m"]),
            min_points=int(options["min_points"]),
            sheet_share=float(options["peel_sheet_share"]) if float(options["peel_sheet_share"]) > 0 else 1e9,
            sheet_min_m=float(options["peel_sheet_min_m"]),
            iterations=int(options["plane_iterations"]),
            seed=int(options["seed"]),
        )
        peel_stats["components"] += int(record["components"])
        peel_stats["sheets"] += int(record["sheets"])
        peel_stats["points_removed"] += int(record["points_removed"])
        for piece in peeled:
            pieces.append(group[piece])

    merged, merge_stats = merge_stacked(
        remaining,
        pieces,
        up=up,
        gap_m=float(options["merge_gap_m"]),
        footprint_share=float(options["merge_footprint_share"]),
        span_m=float(options["merge_span_m"]),
        cell=voxel,
        containment_share=float(options["merge_containment_share"]),
    )

    clusters: list[np.ndarray] = []
    split_components = 0
    split_reasons: dict[str, int] = {}
    for group in merged:
        points = remaining[group]
        pieces = split_component(
            points,
            target=int(options["split_target"]),
            max_points=int(options["split_points"]),
            max_extent=float(options["split_max_extent_m"]),
            gap_m=SPLIT_GAP_M,
            allow_quota=bool(options["split_allow_quota"]),
            stats=split_reasons,
        )
        if len(pieces) > 1:
            split_components += 1
        for piece in pieces:
            if piece.size >= int(options["min_points"]):
                clusters.append(group[piece])
            else:
                dropped_small += 1

    clusters.sort(key=lambda cluster: cluster.size, reverse=True)
    limit = int(options["max_objects"])
    capped = clusters[:limit]
    dropped_by_cap = clusters[limit:]
    objects = [
        build_object(index + 1, remaining[cluster], up=up, floor=floor, snap_m=float(options["floor_snap_m"]))
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
    pose = hero_camera_pose(scene)
    eye = np.asarray(pose["eye"], dtype=np.float64)
    forward = np.asarray(pose["forward"], dtype=np.float64)
    look = eye + forward * 4.0
    camera = {
        "eye": pose["eye"],
        "target": [round(float(value), 4) for value in look],
        "up": pose["up"],
    }

    payload = {
        "artifact": "objects",
        "version": OBJECTS_VERSION,
        "source": {
            "scene": str(source_path) if source_path is not None else "data/scene/scene.npz",
            "capture": scene.meta.get("source", {}).get("file"),
            "points": int(total),
            "up_axis": frame.get("up_axis"),
            "units": frame.get("units"),
        },
        "parameters": {
            **{name: (round(value, 4) if isinstance(value, float) else value) for name, value in options.items()},
            "voxel_m_effective": voxel,
            "spacing": spacing,
        },
        "planes": {
            "removed": len(planes),
            "removed_points": removed_points,
            "removed_fraction": round(removed_points / max(1, total), 4),
            "horizontal": sum(1 for plane in planes if plane.horizontal),
            "vertical": sum(1 for plane in planes if not plane.horizontal),
            "items": [asdict(plane) for plane in planes],
        },
        "normals": {
            "source": "the rotated thinnest gaussian axis, pooled per voxel for the plane test",
            "available": normals is not None,
            "pool_m": float(options["normal_pool_m"]),
            "agreement": float(options["plane_normal_agreement"]),
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
            "components_kept": int(len(kept_groups)),
            "components_merged": int(merge_stats["components"] - merge_stats["components_after"]),
            "components_peeled": int(peel_stats["sheets"]),
            "peel_points_removed": int(peel_stats["points_removed"]),
            "merge_pairs_joined": int(merge_stats["pairs_joined"]),
            "components_split": int(split_components),
            "splits_by_gap": int(split_reasons.get("gap", 0)),
            "splits_by_neck": int(split_reasons.get("neck", 0)),
            "splits_by_quota": int(split_reasons.get("quota", 0)),
            "clusters": int(len(clusters)),
            "clusters_dropped_min_points": int(dropped_small),
            "objects": len(objects),
            "capped": int(max(0, len(clusters) - len(objects))),
            "capped_points": int(sum(cluster.size for cluster in dropped_by_cap)),
            "capped_largest_points": [int(cluster.size) for cluster in dropped_by_cap[:5]],
            "floor_snapped": int(sum(1 for obj in objects if obj.floor_snapped)),
            "points_in_objects": in_objects,
            "points_in_objects_fraction": round(in_objects / max(1, total), 4),
            "largest_object_share": round(largest / max(1, total), 4),
            "median_points_per_object": int(np.median([obj.points for obj in objects])) if objects else 0,
            "objects_by_class": _class_counts(objects),
        },
        "scale_check": scale_check(objects, up),
        "timing_s": round(elapsed, 2),
        "camera": camera,
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
    parameters = payload["parameters"]
    spacing = parameters["spacing"]
    voxel = parameters["voxel_m_effective"]
    by_class = ", ".join(f"{name} {count}" for name, count in counts["objects_by_class"].items())
    lines = [
        f"points            {payload['source']['points']:,} in, {planes['removed_points']:,} removed as planes "
        f"({planes['removed_fraction']:.1%})",
        f"planes removed    {planes['removed']} "
        f"({planes.get('horizontal', 0)} horizontal, {planes.get('vertical', 0)} vertical)",
        f"floor             " + (f"at {floor['height']:+.3f} ({floor['inliers']:,} inliers, rms {floor['rms_m']:.3f} m)" if floor["detected"] else "not detected"),
        f"point spacing     " + (
            f"{spacing['spacing_m']:.3f} m on the floor, voxel {voxel:.3f} m"
            if spacing.get("spacing_m") else
            f"not measured, voxel {voxel:.3f} m"
        )
        + f" (requested {parameters['voxel_m']:.3f} m)",
        f"components        {counts['components']:,} at {voxel * 100:.1f} cm, "
        f"{counts['components_split']} split ({counts['splits_by_gap']} gap, "
        f"{counts['splits_by_neck']} neck, {counts['splits_by_quota']} quota), "
        f"{counts['components_merged']} merged "
        f"({counts['merge_pairs_joined']} stacked pairs), "
        f"{counts['components_peeled']} peeled sheets",
        f"objects framed    {counts['objects']:,} from {counts['clusters']:,} clusters"
        + f", {counts['clusters_dropped_min_points']} below the point floor"
        + (f", {counts['capped']} capped" if counts["capped"] else ", nothing capped"),
        f"points in objects {counts['points_in_objects']:,} ({counts['points_in_objects_fraction']:.1%}), "
        f"largest object {counts['largest_object_share']:.1%}",
        f"median points     {counts['median_points_per_object']:,} per object, "
        f"{counts['floor_snapped']} boxes completed down to the floor",
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
    parser.add_argument("--plane-distance", default=None, type=float,
                        help="half thickness of the band removed around each plane, in scene units")
    parser.add_argument("--min-points", default=None, type=int, help="minimum points per object")
    parser.add_argument("--max-objects", default=None, type=int, help="maximum objects kept")
    parser.add_argument("--json", action="store_true", help="print the metadata as JSON")
    args = parser.parse_args(argv)

    overrides = {}
    if args.voxel is not None:
        overrides["voxel_m"] = args.voxel
    if args.planes is not None:
        overrides["planes_max"] = args.planes
    if args.plane_distance is not None:
        overrides["plane_distance_m"] = args.plane_distance
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
