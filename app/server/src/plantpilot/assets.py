"""Merge raw geometric boxes and colour seeds into coherent equipment assets.

The segmentation stage frames a box per connected cluster, which is geometry
and nothing more: the supplied boiler room capture comes out as 150 heavily
overlapping boxes, 40 of them longer than 2 m, and the two large vessels are
absorbed into boxes classed as ducts. This stage turns that raw set into a small
list a person can read: coherent instances with an id, a class, a human label,
a confidence and the raw objects or seeded points behind them.

Two independent evidence channels feed it.

The capture's own colour seeds the first channel. Points whose red or blue
channel dominates are voxelised at `COLOUR_VOXEL_M`, grouped by 26-connectivity
and kept when they are equipment sized: at least `COLOUR_MIN_POINTS` gaussians,
a vertical span of at least `COLOUR_MIN_SPAN_M` above the floor, an oriented-box
volume of at least `COLOUR_MIN_VOLUME_M3` and a longest side of at most
`MAX_EQUIPMENT_SIDE_M`. Red dominance is measured relative to the channel's own
brightness as well as against the other two channels, because a warm floor and
lit timber are bright and warm: `RED_RELATIVE_CHROMA` is the share of the red
channel the margin over green and blue has to reach. A compact component
(longest side under three times the shortest) reads as a vessel or a tank; an
elongated one as pipework. Height is measured along the scene's own up axis from
`Scene.meta`, never a constant.

The second channel is the geometric proposals from `objects.json`: classes
pump, motor, machine, drum, valve and tank, kept when they are equipment sized
(the same `MAX_EQUIPMENT_SIDE_M`, at least `GEOMETRY_MIN_SIDE_M` on the thinnest
side, at least `GEOMETRY_MIN_POINTS` points and at least `GEOMETRY_MIN_VOLUME_M3`).
Structural classes are never candidates, whatever their size.

The two sets are merged in 3D. Colour instances are accepted first because the
capture's own colour is direct evidence. Then geometry candidates are offered in
descending confidence and dropped when their centre lies inside an accepted
asset or their oriented-box 3D IoU with an accepted asset exceeds
`IOU_LIMIT`; the same test runs between candidates, so the strongest proposal of
an overlapping group of boxes survives and the rest are counted as suppressed.

`confidence` is a strength in [0, 1], not a calibrated probability. A colour
instance scores 0.6, plus up to 0.2 for evidence size (points divided by
`COLOUR_SIZE_FULL`, capped at one) and 0.15 when it is compact rather than
elongated, capped at 0.95. A geometry box is scored from its observable support
instead of the segmentation stage's class prior: 0.45 base, 0.20 times points
divided by `GEOMETRY_SIZE_FULL` capped at one, 0.15 when its longest side is
under three times its shortest (0.075 when under four), and 0.05 when its class
is pump, motor, machine, drum or tank, capped at 0.85. The two scores are
comparable in range but not identical in meaning; acceptance order is fixed by
method first, never by the score.

`verified` means the asset belongs in the default view. A colour instance is
verified because its class rests on the capture's own paint. A geometric box is
verified when its class is pump, motor, machine, drum or tank, it holds at least
`GEOMETRY_VERIFIED_MIN_POINTS` points and its box is compact (longest side under
three times the shortest). Valve boxes and long or flat fragments stay available
as unverified proposals. An asset id is the first eight hex characters of the
SHA-1 of its centimetre-rounded centre and extents, prefixed `AS-`, so the same
instance keeps its id across runs and captures.

Two approximations are deliberate. The oriented-box IoU is measured on a
`IOU_VOXEL_M` lattice rather than as an exact polytope intersection: a shared
voxel count is deterministic, needs no extra package and is well inside the
margin of a 0.2 threshold. And a box is fitted by PCA with extents from the 2nd
to the 98th percentile along each axis, so a box is a robust envelope of its
points, not a tight hull.

The output document is `assets.json`. It is deterministic: the same scene and
objects inputs give byte-identical JSON, so the stage can be wired into `make`
and diffed.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from . import segment
from .splat import Scene, load_scene

ASSETS_VERSION = 1

# The seed masks are requested thresholds, not fitted ones. A channel has to be
# bright enough to be painted, beat both other channels by an absolute margin,
# and beat them by a margin relative to its own strength: a warm floor or a lit
# timber surface is bright, so an absolute margin alone lets the room through.
RED_MIN_CHANNEL = 80
RED_MIN_CHROMA = 25
RED_RELATIVE_CHROMA = 0.30
BLUE_MIN_CHANNEL = 80
BLUE_MIN_CHROMA = 15

# A seeded component has to hold together at this voxel size, at least this many
# gaussians, this much height above the floor and this much box volume.
COLOUR_VOXEL_M = 0.05
COLOUR_MIN_POINTS = 1500
COLOUR_MIN_SPAN_M = 0.35
COLOUR_MIN_VOLUME_M3 = 0.08

# An equipment instance has to fit the same envelope the geometry gate uses. A
# colour component longer than this is a seeded background region (the warm
# floor and walls of a lit room), not a machine, so it is not offered as one.
MAX_EQUIPMENT_SIDE_M = 2.5

# The geometric classes that can become equipment, and the gates a box passes.
EQUIPMENT_CLASSES = ("pump", "motor", "machine", "drum", "valve", "tank")
GEOMETRY_MIN_POINTS = 800
GEOMETRY_MIN_SIDE_M = 0.12
GEOMETRY_MIN_VOLUME_M3 = 0.03

# A geometric box is verified, rather than merely proposed, when its class is
# machinery a shape can support, it is supported by enough points and it is
# compact rather than a long or flat fragment.
VERIFIED_GEOMETRY_CLASSES = ("pump", "motor", "machine", "drum", "tank")
GEOMETRY_VERIFIED_MIN_POINTS = 4000

# Two accepted boxes closer than this in volume are the same piece of equipment.
IOU_LIMIT = 0.2
IOU_VOXEL_M = 0.05

# Confidence, defined in the module docstring. A colour instance earns a base,
# a size term and a compactness term; a geometry box earns its own support
# terms instead of reusing the segmentation stage's class prior.
COLOUR_CONFIDENCE_BASE = 0.6
COLOUR_CONFIDENCE_SIZE = 0.2
COLOUR_CONFIDENCE_COMPACT = 0.15
COLOUR_CONFIDENCE_CAP = 0.95
COLOUR_SIZE_FULL = 20_000.0

GEOMETRY_CONFIDENCE_BASE = 0.45
GEOMETRY_CONFIDENCE_SIZE = 0.20
GEOMETRY_SIZE_FULL = 12_000.0
GEOMETRY_CONFIDENCE_COMPACT = 0.15
GEOMETRY_CONFIDENCE_COMPACT_HALF = 0.075
GEOMETRY_CONFIDENCE_EQUIPMENT = 0.05
GEOMETRY_CONFIDENCE_CAP = 0.85

# Voxel keys for the IoU lattice are three 21-bit fields with a bias, so a
# negative world coordinate still packs into a positive int64.
_VOXEL_BIAS = 1_000_000
_VOXEL_BITS = 21

COLOUR_ORDER = ("red", "blue")


@dataclass
class Asset:
    """One coherent equipment instance, ready for JSON."""

    id: str
    class_name: str
    label: str
    confidence: float
    verified: bool
    centre: list[float]
    axes: list[list[float]]
    extents: list[float]
    points: int
    mean_rgb: list[int]
    source_object_ids: list[str]
    method: str
    reason: str

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "class": self.class_name,
            "label": self.label,
            "confidence": self.confidence,
            "verified": self.verified,
            "centre": self.centre,
            "axes": self.axes,
            "extents": self.extents,
            "points": self.points,
            "mean_rgb": self.mean_rgb,
            "source_object_ids": self.source_object_ids,
            "method": self.method,
            "reason": self.reason,
        }


@dataclass
class Proposal:
    """An instance before suppression and before its colour is sampled.

    Numpy arrays are kept here because the geometry tests run on them, and the
    dataclass stays out of the JSON document. `seeds` holds the scene rows of a
    colour instance, for the mean colour; a geometry proposal has none.
    """

    class_name: str
    label: str
    confidence: float
    verified: bool
    centre: np.ndarray
    axes: np.ndarray
    extents: np.ndarray
    points: int
    source_object_ids: list[str]
    method: str
    reason: str
    seeds: np.ndarray | None = None


def seed_masks(rgb: np.ndarray) -> dict[str, np.ndarray]:
    """Boolean red and blue seed masks over the scene's 0 to 255 colours.

    The red test is relative as well as absolute: a warm floor, a lit timber
    panel or a beige wall is bright and warm, so it passes a fixed margin over
    green and blue while being nowhere near red paint. Requiring the margin to
    be a share of the channel itself keeps the seed on painted surfaces. The
    arithmetic runs in int16 so a dark red point cannot wrap around a uint8
    channel and pass the blue test.
    """
    channels = np.asarray(rgb).astype(np.int16)
    red, green, blue = channels[:, 0], channels[:, 1], channels[:, 2]
    red_chroma = red - np.maximum(green, blue)
    return {
        "red": (red > RED_MIN_CHANNEL)
        & (red_chroma > RED_MIN_CHROMA)
        & (red_chroma > RED_RELATIVE_CHROMA * red),
        "blue": (blue > BLUE_MIN_CHANNEL) & ((blue - np.maximum(red, green)) > BLUE_MIN_CHROMA),
    }


def fit_box(points: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """PCA axes plus robust extents (2nd to 98th percentile) for a point set.

    The axes are signed so each row points along the dominant positive direction
    of its own axis. That makes the frame reproducible, which the asset id
    depends on, and matches the box convention of `objects.json`.
    """
    points = np.asarray(points, dtype=np.float64)
    centroid = points.mean(axis=0)
    centred = points - centroid
    covariance = centred.T @ centred / max(1, points.shape[0] - 1)
    values, vectors = np.linalg.eigh(covariance)
    axes = vectors[:, np.argsort(values)[::-1]].T
    for row in range(3):
        dominant = int(np.argmax(np.abs(axes[row])))
        if axes[row, dominant] < 0:
            axes[row] = -axes[row]
    local = centred @ axes.T
    lo = np.percentile(local, 2.0, axis=0)
    hi = np.percentile(local, 98.0, axis=0)
    centre = centroid + axes.T @ ((lo + hi) / 2.0)
    return centre, axes, np.maximum(hi - lo, 1e-4)


def _colour_label(colour: str, compact: bool) -> tuple[str, str]:
    """Machine class and human label for a seeded instance."""
    if compact:
        if colour == "red":
            return "pressure_vessel", "red pressure vessel"
        return "tank", "blue tank"
    return "pipework", f"{colour} pipework"


def _colour_confidence(points: int, compact: bool) -> float:
    """The documented colour evidence score, in [0.6, 0.95]."""
    size = min(float(points) / COLOUR_SIZE_FULL, 1.0)
    score = COLOUR_CONFIDENCE_BASE + COLOUR_CONFIDENCE_SIZE * size
    if compact:
        score += COLOUR_CONFIDENCE_COMPACT
    return round(min(score, COLOUR_CONFIDENCE_CAP), 3)


def _inside(centre: np.ndarray, box: Proposal, tolerance: float = 1e-6) -> bool:
    """True when a point lies inside an oriented box."""
    local = (np.asarray(centre, dtype=np.float64) - box.centre) @ box.axes.T
    return bool((np.abs(local) <= box.extents / 2.0 + tolerance).all())


def _object_ids_inside(records: list[dict], box: Proposal) -> list[str]:
    """Raw object ids whose centre falls inside an instance box."""
    return [record["id"] for record in records if _inside(np.asarray(record["centre"], float), box)]


def colour_proposals(scene: Scene, records: list[dict]) -> list[Proposal]:
    """Seed instances from the capture's own red and blue paint.

    Components are walked largest first within each colour, so the order is
    deterministic. `source_object_ids` records the raw boxes this instance
    absorbs, which is how a colour asset shows it replaces a misleading
    geometric proposal.
    """
    masks = seed_masks(scene.rgb)
    height = scene.height()
    xyz = scene.xyz
    proposals: list[Proposal] = []
    for colour in COLOUR_ORDER:
        rows = np.flatnonzero(masks[colour])
        if rows.size == 0:
            continue
        keys, inverse, dims = segment.voxel_indices(xyz[rows], COLOUR_VOXEL_M)
        components = segment.component_points(keys, dims, inverse)
        for component in components:
            if component.size < COLOUR_MIN_POINTS:
                break  # components are sorted by size, so the rest are smaller too
            seeds = rows[component]
            span = float(np.ptp(height[seeds]))
            if span < COLOUR_MIN_SPAN_M:
                continue
            centre, axes, extents = fit_box(xyz[seeds])
            volume = float(np.prod(extents))
            longest, shortest = float(extents.max()), float(extents.min())
            if volume < COLOUR_MIN_VOLUME_M3 or longest > MAX_EQUIPMENT_SIDE_M:
                continue
            compact = longest < 3.0 * shortest
            class_name, label = _colour_label(colour, compact)
            proposal = Proposal(
                class_name=class_name,
                label=label,
                confidence=_colour_confidence(int(seeds.size), compact),
                verified=True,
                centre=centre,
                axes=axes,
                extents=extents,
                points=int(seeds.size),
                source_object_ids=[],
                method="colour_instance",
                reason=(
                    f"{colour} seed, {int(seeds.size)} gaussians in one "
                    f"{COLOUR_VOXEL_M:.2f} m component, vertical span {span:.2f} m, "
                    f"{'compact' if compact else 'elongated'} box "
                    f"{extents[0]:.2f} x {extents[1]:.2f} x {extents[2]:.2f} m"
                ),
                seeds=seeds,
            )
            proposal.source_object_ids = _object_ids_inside(records, proposal)
            proposals.append(proposal)
    return proposals


def _candidate(record: dict) -> bool:
    """True when a raw geometric box clears the equipment gates."""
    if record.get("class") not in EQUIPMENT_CLASSES:
        return False
    extents = np.sort(np.asarray(record["extents"], dtype=np.float64))[::-1]
    return bool(
        extents[0] <= MAX_EQUIPMENT_SIDE_M
        and extents[2] >= GEOMETRY_MIN_SIDE_M
        and int(record.get("points", 0)) >= GEOMETRY_MIN_POINTS
        and float(record.get("volume_m3", 0.0)) >= GEOMETRY_MIN_VOLUME_M3
    )


def _side_ratio(extents: np.ndarray) -> float:
    """Longest side divided by the shortest, the compactness measure."""
    sides = np.sort(np.asarray(extents, dtype=np.float64))[::-1]
    return float(sides[0] / max(float(sides[2]), 1e-6))


def _geometry_confidence(extents: np.ndarray, points: int, class_name: str) -> float:
    """Documented geometry support score, in [0.45, 0.85]."""
    score = GEOMETRY_CONFIDENCE_BASE + GEOMETRY_CONFIDENCE_SIZE * min(
        float(points) / GEOMETRY_SIZE_FULL, 1.0
    )
    ratio = _side_ratio(extents)
    if ratio < 3.0:
        score += GEOMETRY_CONFIDENCE_COMPACT
    elif ratio < 4.0:
        score += GEOMETRY_CONFIDENCE_COMPACT_HALF
    if class_name in VERIFIED_GEOMETRY_CLASSES:
        score += GEOMETRY_CONFIDENCE_EQUIPMENT
    return round(min(score, GEOMETRY_CONFIDENCE_CAP), 3)


def _geometry_verified(extents: np.ndarray, points: int, class_name: str) -> bool:
    """True when a geometric box has the class and support to be shown as sure."""
    return bool(
        class_name in VERIFIED_GEOMETRY_CLASSES
        and points >= GEOMETRY_VERIFIED_MIN_POINTS
        and _side_ratio(extents) < 3.0
    )


def geometry_proposals(records: list[dict]) -> list[Proposal]:
    """Equipment-class geometric boxes, strongest support first."""
    proposals: list[Proposal] = []
    for record in records:
        if not _candidate(record):
            continue
        extents = np.asarray(record["extents"], dtype=np.float64)
        points = int(record.get("points", 0))
        class_name = str(record["class"])
        proposals.append(
            Proposal(
                class_name=class_name,
                label=class_name,
                confidence=_geometry_confidence(extents, points, class_name),
                verified=_geometry_verified(extents, points, class_name),
                centre=np.asarray(record["centre"], dtype=np.float64),
                axes=np.asarray(record["axes"], dtype=np.float64),
                extents=extents,
                points=points,
                source_object_ids=[str(record["id"])],
                method="geometry_box",
                reason=(
                    f"{record.get('class_reason', 'no shape rule matched')}; passed the "
                    f"equipment gate at {extents[0]:.2f} x {extents[1]:.2f} x {extents[2]:.2f} m, "
                    f"{points} points, {float(record.get('volume_m3', 0.0)):.2f} m3"
                ),
            )
        )
    proposals.sort(key=lambda proposal: (-proposal.confidence, proposal.source_object_ids[0]))
    return proposals


def _box_corners(box: Proposal) -> np.ndarray:
    """The eight corners of an oriented box, in world coordinates."""
    half = box.extents / 2.0
    signs = np.array(
        [[-1.0, -1.0, -1.0], [-1.0, -1.0, 1.0], [-1.0, 1.0, -1.0], [-1.0, 1.0, 1.0],
         [1.0, -1.0, -1.0], [1.0, -1.0, 1.0], [1.0, 1.0, -1.0], [1.0, 1.0, 1.0]]
    )
    return box.centre + (half[None, :] * signs) @ box.axes


def _box_voxels(box: Proposal, cell: float = IOU_VOXEL_M) -> np.ndarray:
    """Lattice keys of the lattice points inside an oriented box.

    The lattice is anchored at the world origin, so two boxes share keys only
    when they share a volume, which is what the IoU estimate needs. Keys are
    packed as three biased 21-bit fields.
    """
    corners = _box_corners(box)
    lo = corners.min(axis=0)
    hi = corners.max(axis=0)
    indices = [np.arange(np.ceil(lo[axis] / cell), np.floor(hi[axis] / cell) + 1.0)
               for axis in range(3)]
    grid = np.stack(np.meshgrid(*indices, indexing="ij"), axis=-1).reshape(-1, 3)
    points = grid.astype(np.float64) * cell
    local = (points - box.centre) @ box.axes.T
    inside = (np.abs(local) <= box.extents / 2.0 + 1e-9).all(axis=1)
    kept = grid[inside].astype(np.int64) + _VOXEL_BIAS
    return (kept[:, 0] << (2 * _VOXEL_BITS)) | (kept[:, 1] << _VOXEL_BITS) | kept[:, 2]


def _iou(left: np.ndarray, right: np.ndarray) -> float:
    """Voxel IoU from two lattice key arrays."""
    intersection = int(np.intersect1d(left, right, assume_unique=True).size)
    if intersection == 0:
        return 0.0
    union = int(left.size) + int(right.size) - intersection
    return intersection / union if union else 0.0


def _may_overlap(left: Proposal, right: Proposal) -> bool:
    """Cheap axis-aligned pre-test: without it the pair cannot share volume."""
    left_corners, right_corners = _box_corners(left), _box_corners(right)
    if (left_corners.max(axis=0) < right_corners.min(axis=0)).any():
        return False
    if (right_corners.max(axis=0) < left_corners.min(axis=0)).any():
        return False
    return True


def suppress(
    colour: list[Proposal],
    candidates: list[Proposal],
) -> tuple[list[Proposal], int]:
    """Merge the two channels in 3D and count the candidates that lost.

    Colour instances are accepted first. Candidates arrive in descending
    confidence and are dropped when they collide with anything already accepted,
    so the strongest box of an overlapping group represents that equipment.
    """
    accepted = list(colour)
    voxels = [_box_voxels(proposal) for proposal in accepted]
    suppressed = 0
    for candidate in candidates:
        candidate_voxels: np.ndarray | None = None
        dropped = False
        for index, asset in enumerate(accepted):
            if _inside(candidate.centre, asset):
                dropped = True
                break
            if not _may_overlap(candidate, asset):
                continue
            if candidate_voxels is None:
                candidate_voxels = _box_voxels(candidate)
            if _iou(candidate_voxels, voxels[index]) > IOU_LIMIT:
                dropped = True
                break
        if dropped:
            suppressed += 1
            continue
        if candidate_voxels is None:
            candidate_voxels = _box_voxels(candidate)
        accepted.append(candidate)
        voxels.append(candidate_voxels)
    return accepted, suppressed


def _mean_colour(scene: Scene, proposal: Proposal) -> list[int]:
    """Mean RGB behind a proposal.

    A colour instance is described by its seeded points, the paint it was found
    by. A geometry box is described by the scene points its box contains, with
    [0, 0, 0] when the box is empty.
    """
    if proposal.seeds is not None:
        sample = scene.rgb[proposal.seeds]
    else:
        corners = _box_corners(proposal)
        lo, hi = corners.min(axis=0), corners.max(axis=0)
        xyz = scene.xyz
        around = ((xyz >= lo) & (xyz <= hi)).all(axis=1)
        local = (xyz[around] - proposal.centre) @ proposal.axes.T
        inside = (np.abs(local) <= proposal.extents / 2.0 + 1e-9).all(axis=1)
        sample = scene.rgb[around][inside]
    if sample.size == 0:
        return [0, 0, 0]
    mean = np.asarray(sample, dtype=np.float64).mean(axis=0)
    return [int(value) for value in np.rint(mean)]


def _asset_id(centre: np.ndarray, extents: np.ndarray) -> str:
    """Stable id from the centimetre-rounded centre and extents."""
    key = ",".join(f"{round(float(value), 2):.2f}" for value in (*centre, *extents))
    digest = hashlib.sha1(key.encode("ascii")).hexdigest()
    return f"AS-{digest[:8]}"


def _to_asset(scene: Scene, proposal: Proposal) -> Asset:
    """Finish a proposal: stable id, sampled colour and JSON-ready numbers."""
    centre = np.asarray(proposal.centre, dtype=np.float64)
    axes = np.asarray(proposal.axes, dtype=np.float64)
    extents = np.asarray(proposal.extents, dtype=np.float64)
    return Asset(
        id=_asset_id(centre, extents),
        class_name=proposal.class_name,
        label=proposal.label,
        confidence=float(proposal.confidence),
        verified=bool(proposal.verified),
        centre=[round(float(value), 4) for value in centre],
        axes=[[round(float(value), 5) for value in row] for row in axes],
        extents=[round(float(value), 4) for value in extents],
        points=int(proposal.points),
        mean_rgb=_mean_colour(scene, proposal),
        source_object_ids=list(proposal.source_object_ids),
        method=proposal.method,
        reason=proposal.reason,
    )


def build_assets(
    scene: Scene,
    objects: dict,
    *,
    scene_path: Path | str = "data/scene/scene.npz",
    objects_path: Path | str = "data/scene/objects.json",
) -> dict:
    """Run the merge stage and return the `assets.json` document.

    `objects` is the parsed `objects.json` payload, and the two paths are
    recorded in the document so an artifact can be traced to its inputs. No
    timing or machine state reaches the document: the same inputs must give
    byte-identical JSON.
    """
    records = list(objects.get("objects", []))
    colour = colour_proposals(scene, records)
    candidates = geometry_proposals(records)
    accepted, suppressed = suppress(colour, candidates)
    assets = [_to_asset(scene, proposal) for proposal in accepted]
    frame = scene.meta.get("frame", {})
    return {
        "artifact": "assets",
        "version": ASSETS_VERSION,
        "source": {
            "scene": str(scene_path),
            "objects": str(objects_path),
            "capture": scene.meta.get("source", {}).get("file"),
            "points": int(scene.xyz.shape[0]),
            "up_axis": frame.get("up_axis"),
        },
        "counts": {
            "raw_objects": len(records),
            "colour_instances": len(colour),
            "geometry_candidates": len(candidates),
            "suppressed": int(suppressed),
            "assets": len(assets),
            "verified": int(sum(1 for asset in assets if asset.verified)),
        },
        "assets": [asset.as_dict() for asset in assets],
    }


def write_assets(payload: dict, out: Path) -> Path:
    """Write the document with the repository's JSON convention."""
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=1) + "\n")
    return out


def _label_counts(assets: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for asset in assets:
        label = str(asset["label"])
        counts[label] = counts.get(label, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: item[1], reverse=True))


def format_report(payload: dict) -> str:
    """Human readable summary, printed by `make assets`."""
    counts = payload["counts"]
    assets = payload["assets"]
    labels = ", ".join(f"{name} {count}" for name, count in _label_counts(assets).items())
    largest = max(assets, key=lambda asset: max(asset["extents"]), default=None)
    lines = [
        f"counts            raw {counts['raw_objects']}, colour {counts['colour_instances']}, "
        f"candidates {counts['geometry_candidates']}, suppressed {counts['suppressed']}, "
        f"assets {counts['assets']}, verified {counts['verified']}",
        f"labels            {labels or 'none'}",
    ]
    if largest is not None:
        lines.append(
            f"largest           {largest['id']} {largest['label']} "
            f"{largest['extents'][0]:.2f} x {largest['extents'][1]:.2f} x "
            f"{largest['extents'][2]:.2f} m"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m plantpilot.assets",
        description="Merge raw boxes and colour seeds into data/scene/assets.json.",
    )
    parser.add_argument("--scene", default=Path("data/scene/scene.npz"), type=Path)
    parser.add_argument("--objects", default=Path("data/scene/objects.json"), type=Path)
    parser.add_argument("--out", default=Path("data/scene/assets.json"), type=Path)
    parser.add_argument("--json", action="store_true", help="print the document as JSON")
    args = parser.parse_args(argv)

    try:
        scene = load_scene(args.scene)
        objects = segment.load_objects(args.objects)
        payload = build_assets(scene, objects, scene_path=args.scene, objects_path=args.objects)
        write_assets(payload, args.out)
    except Exception as exc:  # noqa: BLE001 - the message is the point of the failure
        print(f"assets failed: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(format_report(payload))
        print(f"wrote             {args.out} ({Path(args.out).stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
