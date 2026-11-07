"""Two-view contact sheets of box results, for grading by eye.

Each cell shows one result from two sides chosen to have the least in the way. The
result's own gaussians keep their colour and everything else is dimmed, so what the
result actually holds is visible, with its box drawn on top. A label gives the sizes
and the other results that share the most gaussians with it, which is what a grader
needs to spot splits and duplicates.

Without --members, everything inside each box counts as its membership: that is how
the viewer lights up a box, and it is the only option for the old objects.json boxes.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "server" / "src"))

from make_vision_boxes import DRAWN_MAX_SIZE_M, DRAWN_MIN_ALPHA, SERVICE_LINE_SHARE, ceiling_height, up_vector  # noqa: E402
from plantpilot import classes  # noqa: E402
from plantpilot.splat import load_scene  # noqa: E402
from plantpilot.splat_render import Camera, Gaussians, from_scene, render  # noqa: E402

CELL_W, CELL_H = 340, 255
LABEL_H = 20
COLUMNS, ROWS = 3, 3
FOV_DEG = 55.0
AZIMUTHS = 8
MIN_DISTANCE_M = 1.0
CONTEXT_RADIUS_M = 4.0
DIM = 0.5
KEEP_COLOUR = 0.35
EYE_FLOOR_RADIUS_M = 0.5
EYE_FLOOR_MIN_POINTS = 60


def box_corners(box: dict) -> np.ndarray:
    centre = np.asarray(box["centre"], dtype=np.float64)
    axes = np.asarray(box["axes"], dtype=np.float64)
    half = 0.5 * np.asarray(box["extents"], dtype=np.float64)
    signs = np.array([[x, y, z] for x in (-1, 1) for y in (-1, 1) for z in (-1, 1)], dtype=np.float64)
    return centre + (signs * half) @ axes


EDGES = [(a, b) for a in range(8) for b in range(a + 1, 8) if bin(a ^ b).count("1") == 1]


def inside_box(box: dict, xyz: np.ndarray) -> np.ndarray:
    axes = np.asarray(box["axes"], dtype=np.float64)
    local = (xyz - np.asarray(box["centre"], dtype=np.float64)) @ axes.T
    return np.flatnonzero((np.abs(local) <= 0.5 * np.asarray(box["extents"], dtype=np.float64)).all(axis=1))


def choose_eyes(box: dict, xyz: np.ndarray, members: np.ndarray, up: np.ndarray, floor: float, service: float) -> list[tuple[np.ndarray, float]]:
    """Two sides of the box, at least 90 degrees apart, with the least in the way."""
    centre = np.asarray(box["centre"], dtype=np.float64)
    diagonal = float(np.linalg.norm(box["extents"]))
    distance = max(MIN_DISTANCE_M, 0.75 * diagonal / math.tan(math.radians(FOV_DEG) / 2.0))
    axis = int(np.argmax(np.abs(up)))
    level = [index for index in range(3) if index != axis]
    height = min(float(centre @ up) - floor + 0.3, service - 0.05)
    base = centre - up * (float(centre @ up) - floor) + up * height
    others = np.ones(xyz.shape[0], dtype=bool)
    others[members] = False
    # Prefer eyes over captured floor: from outside the room the capture is only blur.
    ground = xyz[np.abs(xyz @ up - floor) < 0.15][::4][:, level]
    cloud = xyz[others]
    cloud = cloud[np.linalg.norm(cloud - centre, axis=1) < distance + 0.5][::3]
    scored = []
    for step in range(AZIMUTHS):
        angle = 2.0 * math.pi * step / AZIMUTHS
        eye = base.copy()
        eye[level[0]] += distance * math.cos(angle)
        eye[level[1]] += distance * math.sin(angle)
        ray = centre - eye
        length = float(np.linalg.norm(ray))
        ray /= length
        rel = cloud - eye
        along = rel @ ray
        off = np.linalg.norm(rel - along[:, None] * ray, axis=1)
        # The near half of the way is clipped away when rendering, so only what lies
        # between the clip and the box can hide it.
        blocking = int(((along > 0.5 * length) & (along < length - 0.5 * diagonal) & (off < 0.25 * max(diagonal, 0.4))).sum())
        over_floor = (np.linalg.norm(ground - eye[level], axis=1) < EYE_FLOOR_RADIUS_M).sum() >= EYE_FLOOR_MIN_POINTS
        scored.append((not over_floor, blocking, step, eye))
    scored.sort(key=lambda item: item[:2])
    first = scored[0]
    second = next(
        item for item in scored[1:] if min((item[2] - first[2]) % AZIMUTHS, (first[2] - item[2]) % AZIMUTHS) >= 2
    )
    return [(first[3], distance), (second[3], distance)]


def draw_view(room: Gaussians, room_ids: np.ndarray, members: np.ndarray, box: dict, eye: np.ndarray, distance: float, up: np.ndarray) -> Image.Image:
    centre = np.asarray(box["centre"], dtype=np.float64)
    near = np.linalg.norm(room.xyz - centre, axis=1) < max(CONTEXT_RADIUS_M, 1.5 * distance)
    local = room.subset(np.flatnonzero(near))
    held = np.isin(room_ids[near], members)
    rgb = local.rgb.copy()
    grey = rgb[~held].mean(axis=1, keepdims=True)
    rgb[~held] = (KEEP_COLOUR * rgb[~held] + (1.0 - KEEP_COLOUR) * grey) * DIM
    shown = Gaussians(xyz=local.xyz, scale=local.scale, rot=local.rot, rgb=rgb, alpha=local.alpha)
    camera = Camera.look_at(eye, centre, up, CELL_W, CELL_H, fov_deg=FOV_DEG, near=0.5 * distance)
    image = render(shown, camera).convert("RGB")
    projected = camera.project(box_corners(box))
    pen = ImageDraw.Draw(image)
    for a, b in EDGES:
        if projected["visible"][a] and projected["visible"][b]:
            pen.line(
                [(projected["px"][a], projected["py"][a]), (projected["px"][b], projected["py"][b])],
                fill=(255, 230, 0),
                width=1,
            )
    return image


def overlaps(boxes: list[dict], offsets: np.ndarray, indices: np.ndarray) -> dict[str, list[tuple[str, float]]]:
    """For each result, the others sharing the largest share of the smaller one."""
    owners = np.repeat(np.arange(len(boxes)), np.diff(offsets))
    order = np.argsort(indices, kind="stable")
    sorted_ids, sorted_owners = indices[order], owners[order]
    starts = np.flatnonzero(np.r_[True, sorted_ids[1:] != sorted_ids[:-1]])
    ends = np.r_[starts[1:], sorted_ids.size]
    shared: dict[tuple[int, int], int] = {}
    for start in starts[ends - starts > 1]:
        stop = int(np.searchsorted(sorted_ids, sorted_ids[start], side="right"))
        holders = sorted_owners[start:stop].tolist()
        for position, first in enumerate(holders):
            for second in holders[position + 1 :]:
                key = (min(first, second), max(first, second))
                shared[key] = shared.get(key, 0) + 1
    sizes = np.diff(offsets)
    result: dict[str, list[tuple[str, float]]] = {box["id"]: [] for box in boxes}
    for (first, second), count in shared.items():
        share = count / float(min(sizes[first], sizes[second]))
        result[boxes[first]["id"]].append((boxes[second]["id"], share))
        result[boxes[second]["id"]].append((boxes[first]["id"], share))
    for items in result.values():
        items.sort(key=lambda item: -item[1])
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--scene", type=Path, required=True)
    parser.add_argument("--objects", type=Path, required=True, help="for the floor and ceiling")
    parser.add_argument("--boxes", type=Path, required=True, help="a results file, or objects.json with --ids")
    parser.add_argument("--members", type=Path, help="the membership file of the results")
    parser.add_argument("--ids", help="only these ids, comma separated, or a visual review fixture's path")
    parser.add_argument("--out", type=Path, required=True, help="folder for cells and pages")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--part", help="render only this share of the cells and no pages, as i/n, to run in parallel")
    args = parser.parse_args(argv)

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "cells").mkdir(exist_ok=True)
    scene = load_scene(args.scene)
    up = up_vector(scene)
    payload = json.loads(args.objects.read_text(encoding="utf-8"))
    floor = classes.floor_origin(payload)
    service = SERVICE_LINE_SHARE * ceiling_height(payload, up, floor)
    xyz = scene.xyz.astype(np.float64)
    gaussians = from_scene(scene)
    drawn = np.flatnonzero(
        (xyz @ up - floor < service) & (gaussians.scale.mean(axis=1) < DRAWN_MAX_SIZE_M) & (gaussians.alpha > DRAWN_MIN_ALPHA)
    )
    room = gaussians.subset(drawn)

    document = json.loads(args.boxes.read_text(encoding="utf-8"))
    boxes = document.get("boxes") or document["objects"]
    offsets = indices = None
    shared: dict[str, list[tuple[str, float]]] = {}
    if args.members:
        with np.load(args.members) as data:
            offsets, indices = data["offsets"], data["indices"]
        if [str(value) for value in data_ids(args.members)] != [box["id"] for box in boxes]:
            raise SystemExit("the membership file does not match the results file")
        shared = overlaps(boxes, offsets, indices)
        (args.out / "overlaps.json").write_text(json.dumps(shared, indent=0))
    wanted = list(range(len(boxes)))
    if args.ids:
        path = Path(args.ids)
        names = list(json.loads(path.read_text(encoding="utf-8"))["labels"]) if path.exists() else args.ids.split(",")
        wanted = [index for index, box in enumerate(boxes) if box["id"] in names]
    if args.limit:
        wanted = wanted[: args.limit]

    started = time.time()
    cells: list[Path] = []
    part, parts = (int(value) for value in args.part.split("/")) if args.part else (0, 1)
    for count, index in enumerate(wanted, start=1):
        if count % parts != part:
            continue
        box = boxes[index]
        path = args.out / "cells" / f"{box['id']}.png"
        cells.append(path)
        if path.exists():
            continue
        members = indices[offsets[index] : offsets[index + 1]].astype(np.int64) if indices is not None else inside_box(box, xyz)
        cell = Image.new("RGB", (2 * CELL_W, CELL_H + LABEL_H), (24, 24, 24))
        for side, (eye, distance) in enumerate(choose_eyes(box, xyz, members, up, floor, service)):
            cell.paste(draw_view(room, drawn, members, box, eye, distance, up), (side * CELL_W, LABEL_H))
        extents = "x".join(f"{value:.2f}" for value in box["extents"])
        text = f"{box['id']} {extents} p{box.get('points', members.size)} v{box.get('views', '-')}"
        near = [f"{name[3:]}:{share:.0%}" for name, share in shared.get(box["id"], [])[:3] if share >= 0.1]
        if near:
            text += "  ov " + " ".join(near)
        ImageDraw.Draw(cell).text((4, 4), text, fill=(255, 255, 255))
        cell.save(path)
        if count % 20 == 0 or count == len(wanted):
            print(f"{count}/{len(wanted)} {time.time() - started:.0f}s", flush=True)

    if args.part:
        return 0
    per_page = COLUMNS * ROWS
    for page in range(0, len(cells), per_page):
        sheet = Image.new("RGB", (COLUMNS * 2 * CELL_W, ROWS * (CELL_H + LABEL_H)), (0, 0, 0))
        for slot, path in enumerate(cells[page : page + per_page]):
            sheet.paste(Image.open(path), ((slot % COLUMNS) * 2 * CELL_W, (slot // COLUMNS) * (CELL_H + LABEL_H)))
        sheet.save(args.out / f"page_{page // per_page + 1:03d}.jpg", quality=88)
    print(f"{len(cells)} cells on {math.ceil(len(cells) / per_page)} pages in {time.time() - started:.0f}s", flush=True)
    return 0


def data_ids(path: Path) -> list[str]:
    with np.load(path) as data:
        return data["ids"].tolist()


if __name__ == "__main__":
    raise SystemExit(main())
