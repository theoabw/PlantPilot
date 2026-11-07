"""Find the objects on the floor and walls with a vision model, offline, on a GPU.

Geometry alone cannot part objects that touch in a cluttered room, so this script
looks at the capture instead. It is a build step and never part of the demo path: it
writes a small fixture, and the product reads the fixture with no model installed.

1. Render posed views from inside the room, without the ceiling services.
2. Ask SAM 2.1 to outline everything in each view. It outlines and does not name.
3. Lift each outline onto the gaussians it sees, through the capture's own depth.
4. Join outlines from different views that hold the same gaussians, so an object is
   one thing seen from several sides, and keep what at least two views agree on.
5. Fit an upright box to each object's gaussians, leaving out walls and floor.

Needs torch, transformers, numpy, pillow and opencv, which the project itself does not
depend on: run it in its own environment. See docs/vision-boxes.md.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "server" / "src"))

from plantpilot import classes, segment  # noqa: E402
from plantpilot.splat import load_scene  # noqa: E402
from plantpilot.splat_render import Camera, from_scene, render  # noqa: E402

MODEL = "facebook/sam2.1-hiera-large"
# A horizontal plane this far above the floor or higher can be the ceiling.
CEILING_MIN_HEIGHT_M = 1.2
SERVICE_LINE_SHARE = 0.85
EYE_HEIGHTS_M = (0.55, 1.25)
YAWS = 8
EYE_GRID_M = 1.2
EYE_CLEARANCE_M = 0.18
# An eye is in the room only if floor was captured under it.
EYE_FLOOR_RADIUS_M = 0.6
EYE_FLOOR_MIN_POINTS = 100
# A view must have capture in this share of its coarse image cells.
VIEW_COVER_CELL_PX = 32
VIEW_MIN_COVER = 0.4
# An outline mostly on unrendered background is the void, not an object.
DARK_LUMA = 10
MASK_MAX_DARK = 0.5
FOV_DEG = 80.0
WIDTH, HEIGHT = 1024, 768
# Depth is built on a coarser grid so gaps between gaussian centres do not let the
# far side of an object show through the near side.
DEPTH_CELL_PX = 4
DEPTH_TOLERANCE_M = 0.06
MASK_MIN_AREA = 0.0015
MASK_MAX_AREA = 0.35
MASK_MIN_POINTS = 40
VOXEL_M = 0.03
JOIN_IOU = 0.45
JOIN_CONTAINED = 0.7
MIN_VIEWS = 3
MAX_SIDE_M = 2.0
MIN_POINTS = 400
BOX_OVERLAP_DROP = 0.8
# Tuned against hand grades of the first full run (scripts/tune_vision_boxes.py, docs/vision-boxes.md):
# fewer views, fewer points or a longer side were mostly clutter; joining more joined few splits
# and merged more objects than it joined.
# What splat_render.render() draws by default. A gaussian it culls is in no image, so
# it must not occlude anything in the depth buffer or be claimed by an outline.
DRAWN_MAX_SIZE_M = 0.12
DRAWN_MIN_ALPHA = 0.03
OUTLINE_ARGS = {"points_per_batch": 128, "points_per_crop": 32, "pred_iou_thresh": 0.8, "stability_score_thresh": 0.9}
# A voxel held by more outlines than this is ignored when joining.
MAX_VOXEL_HOLDERS = 400


def lift_cache_path(work: Path, view: dict) -> Path:
    """Where one view's lifted outlines are kept, so tuning the join needs no model.
    The name changes with anything that changes the outlines or the lifting."""
    text = json.dumps(
        ["png", MODEL, OUTLINE_ARGS, MASK_MIN_AREA, MASK_MAX_AREA, DARK_LUMA, MASK_MAX_DARK, MASK_MIN_POINTS,
         DEPTH_CELL_PX, DEPTH_TOLERANCE_M, DRAWN_MAX_SIZE_M, DRAWN_MIN_ALPHA]
    )
    return work / f"lift_{view_key(view)}_{hashlib.sha1(text.encode()).hexdigest()[:8]}.npz"


def view_key(view: dict) -> str:
    """A render's cache name, from its camera, so a trial's renders can never be reused
    for a different camera in a later run."""
    text = json.dumps([view["eye"], view["target"], WIDTH, HEIGHT, FOV_DEG, SERVICE_LINE_SHARE])
    return hashlib.sha1(text.encode()).hexdigest()[:16]


def ceiling_height(payload: dict, up: np.ndarray, origin: float) -> float | None:
    """The ceiling's height above the floor: the horizontal plane with the most inliers
    at least CEILING_MIN_HEIGHT_M up, or None when the capture shows no ceiling."""
    best: tuple[int, float] | None = None
    for plane in (payload.get("planes") or {}).get("items", []):
        if not plane.get("horizontal"):
            continue
        along = float(np.asarray(plane["normal"], dtype=np.float64) @ up)
        if abs(along) < 1e-6:
            continue
        height = -float(plane["offset"]) / along - float(origin)
        if height >= CEILING_MIN_HEIGHT_M and (best is None or int(plane["inliers"]) > best[0]):
            best = (int(plane["inliers"]), height)
    return None if best is None else best[1]


def up_vector(scene) -> np.ndarray:
    up = np.zeros(3)
    up[scene.up_index] = float(scene.up_sign)
    return up


def level_axes(up: np.ndarray) -> list[int]:
    axis = int(np.argmax(np.abs(up)))
    return [index for index in range(3) if index != axis]


def view_cover(sample: np.ndarray, camera: Camera) -> float:
    """The share of coarse image cells that hold any of the capture."""
    rel = sample - camera.eye
    depth = rel @ camera.forward
    front = depth > 0.1
    px = (camera.focal * (rel[front] @ camera.right) / depth[front] + 0.5 * camera.width).astype(np.int64)
    py = (0.5 * camera.height - camera.focal * (rel[front] @ camera.up) / depth[front]).astype(np.int64)
    inside = (px >= 0) & (px < camera.width) & (py >= 0) & (py < camera.height)
    columns = camera.width // VIEW_COVER_CELL_PX + 1
    rows = camera.height // VIEW_COVER_CELL_PX + 1
    cells = np.unique(py[inside] // VIEW_COVER_CELL_PX * columns + px[inside] // VIEW_COVER_CELL_PX)
    return cells.size / float(columns * rows)


def plan_views(xyz: np.ndarray, up: np.ndarray, floor: float) -> list[dict]:
    """Eye positions on a grid inside the room, clear of the capture, looking outward."""
    level = level_axes(up)
    heights = xyz @ up - floor
    low, high = np.percentile(xyz[:, level], [2, 98], axis=0)
    sample = xyz[(heights > 0.15) & (heights < 1.7)][::4]
    ground = xyz[heights < 0.15][::4][:, level]
    views: list[dict] = []
    for a in np.arange(low[0], high[0] + 1e-6, EYE_GRID_M):
        for b in np.arange(low[1], high[1] + 1e-6, EYE_GRID_M):
            if (np.linalg.norm(ground - np.array([a, b]), axis=1) < EYE_FLOOR_RADIUS_M).sum() < EYE_FLOOR_MIN_POINTS:
                continue
            for height in EYE_HEIGHTS_M:
                eye = np.zeros(3)
                eye[level[0]], eye[level[1]] = a, b
                eye += up * (floor + height)
                near = np.linalg.norm(sample - eye, axis=1)
                if near.min() < EYE_CLEARANCE_M or (near < 2.0).sum() < 200:
                    continue
                for yaw in range(YAWS):
                    angle = 2.0 * math.pi * yaw / YAWS
                    look = np.zeros(3)
                    look[level[0]], look[level[1]] = math.cos(angle), math.sin(angle)
                    camera = Camera.look_at(eye, eye + look, up, WIDTH, HEIGHT, fov_deg=FOV_DEG, near=0.1)
                    if view_cover(sample, camera) >= VIEW_MIN_COVER:
                        views.append({"eye": eye.tolist(), "target": (eye + look).tolist()})
    return views


def pick_trial(views: list[dict], count: int, focus: np.ndarray, level: list[int]) -> list[dict]:
    """Views that all look at one spot from different eyes, so a trial can test joining."""
    scored = []
    for view in views:
        eye, target = np.array(view["eye"])[level], np.array(view["target"])[level]
        rel = focus - eye
        distance = float(np.linalg.norm(rel))
        look = (target - eye) / float(np.linalg.norm(target - eye))
        if 0.8 <= distance <= 5.0:
            angle = math.degrees(math.acos(float(np.clip(rel @ look / distance, -1.0, 1.0))))
            if angle <= 0.4 * FOV_DEG:
                scored.append((angle, view))
    scored.sort(key=lambda item: item[0])
    chosen: list[dict] = []
    used: set[tuple[float, ...]] = set()
    for _, view in scored:
        key = tuple(view["eye"])
        if key not in used:
            used.add(key)
            chosen.append(view)
    for _, view in scored:
        if view not in chosen:
            chosen.append(view)
    return chosen[:count]


def report_coverage(views: list[dict], drawn_xyz: np.ndarray, up: np.ndarray) -> None:
    """How much of the capture the plan sees, overall and along the room."""
    level = level_axes(up)
    seen_by = np.zeros(drawn_xyz.shape[0], dtype=np.int32)
    for view in views:
        camera = Camera.look_at(view["eye"], view["target"], up, WIDTH, HEIGHT, fov_deg=FOV_DEG, near=0.1)
        np.add.at(seen_by, depth_buffer(drawn_xyz, camera)[0], 1)
    eyes = np.unique(np.array([view["eye"] for view in views]), axis=0)
    print(f"{len(views)} views from {eyes.shape[0]} eyes", flush=True)
    print(f"drawn gaussians seen by 2+ views: {(seen_by >= 2).mean():.3f}", flush=True)
    along = drawn_xyz[:, level[0]]
    for start in np.arange(math.floor(np.percentile(along, 2)), math.ceil(np.percentile(along, 98)), 1.0):
        band = (along >= start) & (along < start + 1.0)
        eye_count = int(((eyes[:, level[0]] >= start) & (eyes[:, level[0]] < start + 1.0)).sum())
        print(f"  axis {level[0]} {start:+.0f} to {start + 1:+.0f}: {eye_count} eyes, 2+ views {(seen_by[band] >= 2).mean():.3f}", flush=True)


def depth_buffer(xyz: np.ndarray, camera: Camera) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Which gaussians each view sees: (their indices, their pixels x and y)."""
    rel = xyz - camera.eye
    depth = rel @ camera.forward
    front = np.flatnonzero(depth > 0.1)
    px = (camera.focal * (rel[front] @ camera.right) / depth[front] + 0.5 * camera.width).astype(np.int64)
    py = (0.5 * camera.height - camera.focal * (rel[front] @ camera.up) / depth[front]).astype(np.int64)
    inside = (px >= 0) & (px < camera.width) & (py >= 0) & (py < camera.height)
    front, px, py = front[inside], px[inside], py[inside]
    columns = camera.width // DEPTH_CELL_PX + 1
    rows = camera.height // DEPTH_CELL_PX + 1
    buffer = np.full((rows, columns), np.inf)
    np.minimum.at(buffer, (py // DEPTH_CELL_PX, px // DEPTH_CELL_PX), depth[front])
    seen = depth[front] <= buffer[py // DEPTH_CELL_PX, px // DEPTH_CELL_PX] + DEPTH_TOLERANCE_M
    return front[seen], px[seen], py[seen]


def outline(generator, image: Image.Image) -> list[np.ndarray]:
    """Boolean masks of the plausible objects in one view."""
    result = generator(image, **OUTLINE_ARGS)
    total = float(image.width * image.height)
    dark = np.asarray(image.convert("L")) < DARK_LUMA
    masks = []
    for mask in result["masks"]:
        array = np.asarray(mask, dtype=bool)
        if MASK_MIN_AREA <= array.sum() / total <= MASK_MAX_AREA and dark[array].mean() <= MASK_MAX_DARK:
            masks.append(array)
    return masks


def lift(mask: np.ndarray, seen: np.ndarray, px: np.ndarray, py: np.ndarray) -> np.ndarray:
    """The gaussians an outline holds in the view it came from."""
    return seen[mask[py, px]]


def fuse(records: list[dict], voxel_of: np.ndarray) -> list[dict]:
    """Join outlines from different views that hold the same voxels."""
    count = len(records)
    sets = [np.unique(voxel_of[record["points"]]) for record in records]
    owner = list(range(count))

    def root(index: int) -> int:
        while owner[index] != index:
            owner[index] = owner[owner[index]]
            index = owner[index]
        return index

    # An inverted index: only outlines that share a voxel are ever compared.
    sizes = np.array([cells.size for cells in sets], dtype=np.int64)
    view_of = np.array([record["view"] for record in records], dtype=np.int64)
    flat_cells = np.concatenate(sets)
    flat_records = np.repeat(np.arange(count), sizes)
    _, cell_of, holders_per_cell = np.unique(flat_cells, return_inverse=True, return_counts=True)
    holders = flat_records[np.argsort(cell_of, kind="stable")]
    cell_start = np.concatenate(([0], np.cumsum(holders_per_cell)[:-1]))
    capped = holders_per_cell > MAX_VOXEL_HOLDERS
    print(
        f"voxels over the {MAX_VOXEL_HOLDERS} holder cap: {int(capped.sum())} of {capped.size}, "
        f"most held {int(holders_per_cell.max())}",
        flush=True,
    )
    record_start = np.concatenate(([0], np.cumsum(sizes)))
    for first in range(count):
        cells = cell_of[record_start[first] : record_start[first + 1]]
        cells = cells[~capped[cells]]
        lengths = holders_per_cell[cells]
        total = int(lengths.sum())
        positions = np.repeat(cell_start[cells], lengths) + np.arange(total) - np.repeat(np.cumsum(lengths) - lengths, lengths)
        shared = np.bincount(holders[positions], minlength=count)
        seconds = np.flatnonzero(shared)
        seconds = seconds[(seconds > first) & (view_of[seconds] != view_of[first])]
        common = shared[seconds]
        small = np.minimum(sizes[seconds], sizes[first])
        large = np.maximum(sizes[seconds], sizes[first])
        joined = (common / (small + large - common) >= JOIN_IOU) | ((common / small >= JOIN_CONTAINED) & (small / large >= 0.25))
        for second in seconds[joined].tolist():
            owner[root(first)] = root(second)

    groups: dict[int, list[int]] = {}
    for index in range(len(records)):
        groups.setdefault(root(index), []).append(index)
    fused = []
    for members in groups.values():
        views = {records[index]["view"] for index in members}
        if len(views) < MIN_VIEWS:
            continue
        votes = np.concatenate([records[index]["points"] for index in members])
        points, counts = np.unique(votes, return_counts=True)
        # A gaussian one stray outline claimed is not part of what the views agree on.
        fused.append({"points": points[counts >= max(2, 0.25 * len(views))], "views": len(views)})
    return fused


def boxes_from(fused: list[dict], xyz: np.ndarray, keep: np.ndarray, up: np.ndarray, floor: float, service: float) -> list[dict]:
    """One upright box per object, fitted without the walls and floor it touches."""
    boxes = []
    for group in sorted(fused, key=lambda item: -item["views"]):
        points = group["points"][keep[group["points"]]]
        if points.size < MIN_POINTS:
            continue
        cloud = xyz[points]
        centre, axes, extents = segment._extents(cloud, up=up)
        heights = cloud @ up - floor
        if float(extents.max()) > MAX_SIDE_M or float(np.percentile(heights, 50)) > service:
            continue
        boxes.append(
            {
                "centre": [round(float(v), 4) for v in centre],
                "axes": [[round(float(v), 5) for v in row] for row in axes],
                "extents": [round(float(v), 4) for v in extents],
                "points": int(points.size),
                "views": int(group["views"]),
                "members": points,
            }
        )
    # The same object fused twice: keep the one more views agree on.
    kept: list[dict] = []
    for box in boxes:
        duplicate = False
        for other in kept:
            common = np.intersect1d(box["members"], other["members"], assume_unique=True).size
            if common >= BOX_OVERLAP_DROP * min(box["members"].size, other["members"].size):
                duplicate = True
                break
        if not duplicate:
            kept.append(box)
    return kept


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--scene", type=Path, required=True)
    parser.add_argument("--objects", type=Path, required=True, help="only its planes and floor are read")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True, help="where renders and masks are cached")
    parser.add_argument("--limit-views", type=int, default=0, help="stop after this many views, for a trial")
    parser.add_argument("--focus", help="trial views look at this spot, as two level coordinates: --focus=-2.5,0")
    parser.add_argument("--plan-only", action="store_true", help="report the camera plan's coverage and stop")
    parser.add_argument("--device", default="cuda")
    args = parser.parse_args(argv)

    args.work.mkdir(parents=True, exist_ok=True)
    scene = load_scene(args.scene)
    up = up_vector(scene)
    payload = json.loads(args.objects.read_text(encoding="utf-8"))
    floor = classes.floor_origin(payload)
    ceiling = ceiling_height(payload, up, floor)
    if ceiling is None:
        raise SystemExit("this capture has no measured ceiling, so there is no service line to render below")
    service = SERVICE_LINE_SHARE * ceiling
    print(f"floor {floor:.3f}, ceiling {ceiling:.2f} m above it, service line {service:.2f} m", flush=True)

    xyz = scene.xyz.astype(np.float64)
    heights = xyz @ up - floor
    gaussians = from_scene(scene)
    below = np.flatnonzero(heights < service)
    room = type(gaussians)(
        xyz=gaussians.xyz[below],
        scale=gaussians.scale[below],
        rot=gaussians.rot[below],
        rgb=gaussians.rgb[below],
        alpha=gaussians.alpha[below],
    )
    drawn = (room.scale.mean(axis=1) < DRAWN_MAX_SIZE_M) & (room.alpha > DRAWN_MIN_ALPHA)
    drawn_xyz = room.xyz[drawn]
    drawn_ids = below[drawn]
    print(f"{below.size} gaussians below the service line, {drawn_ids.size} drawn", flush=True)
    views = plan_views(xyz, up, floor)
    if args.plan_only:
        report_coverage(views, drawn_xyz, up)
        return 0
    if args.limit_views:
        level = level_axes(up)
        focus = (
            np.array([float(value) for value in args.focus.split(",")])
            if args.focus
            else np.median(drawn_xyz[:, level], axis=0)
        )
        views = pick_trial(views, args.limit_views, focus, level)
        print(f"trial focus {focus.round(2).tolist()}", flush=True)
    print(f"{len(views)} views", flush=True)

    from transformers import pipeline

    generator = None
    records: list[dict] = []
    started = time.time()
    for number, view in enumerate(views):
        cache_path = lift_cache_path(args.work, view)
        if cache_path.exists():
            with np.load(cache_path) as cached:
                for part in np.split(cached["points"], cached["offsets"][1:-1]):
                    records.append({"view": number, "points": part})
            print(f"view {number + 1}/{len(views)}: lifted outlines from cache", flush=True)
            continue
        if generator is None:
            generator = pipeline("mask-generation", model=MODEL, device=args.device)
        camera = Camera.look_at(view["eye"], view["target"], up, WIDTH, HEIGHT, fov_deg=FOV_DEG, near=0.1)
        # Lossless: on the 8 centre trial views SAM found 337 outlines in fresh renders
        # and 232 in the same renders saved as JPEG, so a cache must not change the pixels.
        image_path = args.work / f"view_{view_key(view)}.png"
        tick = time.time()
        if image_path.exists():
            image = Image.open(image_path).convert("RGB")
        else:
            image = render(room, camera).convert("RGB")
            image.save(image_path)
        render_s = time.time() - tick
        tick = time.time()
        seen, px, py = depth_buffer(drawn_xyz, camera)
        masks = outline(generator, image)
        outline_s = time.time() - tick
        lifted = []
        for mask in masks:
            points = drawn_ids[lift(mask, seen, px, py)]
            if points.size >= MASK_MIN_POINTS:
                records.append({"view": number, "points": points})
                lifted.append(points)
        np.savez_compressed(
            cache_path,
            points=np.concatenate(lifted) if lifted else np.empty(0, dtype=np.int64),
            offsets=np.cumsum([0] + [part.size for part in lifted]),
        )
        print(
            f"view {number + 1}/{len(views)}: {len(masks)} outlines, render {render_s:.1f}s, "
            f"outline {outline_s:.1f}s, total {time.time() - started:.0f}s",
            flush=True,
        )
        if number < 4 or args.limit_views:
            overlay = np.asarray(image).astype(np.float32)
            rng = np.random.default_rng(number)
            for mask in sorted(masks, key=lambda m: -m.sum()):
                overlay[mask] = overlay[mask] * 0.45 + rng.integers(40, 255, 3) * 0.55
            Image.fromarray(overlay.astype(np.uint8)).save(args.work / f"masks_{view_key(view)}.jpg", quality=85)

    print(f"{len(records)} outlines lifted", flush=True)
    origin = xyz.min(axis=0)
    cells = np.floor((xyz - origin) / VOXEL_M).astype(np.int64)
    dims = cells.max(axis=0) + 1
    voxel_of = (cells[:, 0] * dims[1] + cells[:, 1]) * dims[2] + cells[:, 2]
    fused = fuse(records, voxel_of)
    print(f"{len(fused)} objects seen from at least {MIN_VIEWS} views", flush=True)

    normals = segment.gaussian_normals(scene)
    options = segment.DEFAULTS
    _, keep = segment.find_planes(
        xyz,
        up=up,
        threshold=float(options["plane_distance_m"]),
        max_planes=int(options["planes_max"]),
        min_fraction=float(options["plane_min_fraction"]),
        sample_points=int(options["plane_sample"]),
        iterations=int(options["plane_iterations"]),
        seed=int(options["seed"]),
        normals=normals,
    )
    boxes = boxes_from(fused, xyz, keep, up, floor, service)
    for index, box in enumerate(sorted(boxes, key=lambda item: tuple(item["centre"])), start=1):
        box["id"] = f"VB-{index:03d}"
    boxes.sort(key=lambda item: item["id"])
    # Exact membership, since a box alone lights up its surroundings in the viewer. The
    # gaussians of boxes[i] are indices[offsets[i]:offsets[i + 1]] into scene.npz.
    members = [box.pop("members") for box in boxes]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    members_path = args.out.with_name(args.out.stem + "_members.npz")
    np.savez_compressed(
        members_path,
        ids=np.array([box["id"] for box in boxes]),
        offsets=np.cumsum([0] + [m.size for m in members]).astype(np.int64),
        indices=(np.concatenate(members) if members else np.empty(0)).astype(np.int32),
    )
    document = {
        "artifact": "vision_boxes",
        "version": 1,
        "capture": scene.meta.get("source", {}).get("file"),
        "method": f"{MODEL} outlines on {len(views)} posed views, lifted through depth and fused across views",
        "note": "Where objects are, not what they are. The model outlines without naming.",
        "service_line_m": round(service, 3),
        "boxes": boxes,
    }
    args.out.write_text(json.dumps(document, indent=1) + "\n")
    print(f"wrote {len(boxes)} boxes to {args.out} in {time.time() - started:.0f}s", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
