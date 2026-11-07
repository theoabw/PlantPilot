"""Sweep the join and filter settings of make_vision_boxes on its saved outlines.

Needs no model: the lifted outlines of every view are cached by the full run. Each
setting is scored against the hand grades of the first full run
by membership. The grades are fixtures/scene/vision_review_equipment.txt, and the first
run is rebuilt from the cache with the settings in docs/vision-boxes.md. A new result that holds at least half of an old result, and whose own
gaussians are mostly that result, inherits its grade. This is a proxy for planning a
change. It cannot see new mistakes the old results did not have, so a chosen setting
still needs its changed results graded by eye.

Scores per setting:
  results          how many results it writes
  whole kept       old whole results it still has as one result (of the graded whole ones)
  clutter kept     old clutter results it still writes
  splits joined    split groups (one real object in several old results) now one result
  new merges       results that hold most of two or more old results graded as different objects
"""

from __future__ import annotations

import argparse
import itertools
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "server" / "src"))

import make_vision_boxes as m  # noqa: E402
from plantpilot import classes, segment  # noqa: E402
from plantpilot.splat import load_scene  # noqa: E402

GRID = {
    "MIN_VIEWS": [2, 3, 4, 6],
    "JOIN_IOU": [0.35, 0.2],
    "JOIN_CONTAINED": [0.7, 0.5],
    "MIN_POINTS": [150, 400],
    "MAX_SIDE_M": [3.2, 2.0],
    "BOX_OVERLAP_DROP": [0.8, 0.5],
}


def load_grades(path: Path) -> tuple[dict[int, str], dict[int, str]]:
    grades, groups = {}, {}
    for line in path.read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split()
        grades[int(parts[0])] = parts[1]
        if len(parts) > 2:
            groups[int(parts[0])] = parts[2]
    return grades, groups


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--scene", type=Path, default=Path("data/equipment/scene.npz"))
    parser.add_argument("--objects", type=Path, default=Path("data/equipment/objects.json"))
    parser.add_argument("--work", type=Path, default=Path("data/equipment/vision_work"))
    parser.add_argument("--graded", type=Path, default=Path("data/equipment/vision_run1_members.npz"))
    parser.add_argument("--grades", type=Path, default=Path("fixtures/scene/vision_review_equipment.txt"))
    parser.add_argument("--out", type=Path, default=Path("data/equipment/vision_tuning.json"))
    parser.add_argument("--only", help="one setting as JSON instead of the grid")
    args = parser.parse_args(argv)

    scene = load_scene(args.scene)
    up = m.up_vector(scene)
    payload = json.loads(args.objects.read_text(encoding="utf-8"))
    floor = classes.floor_origin(payload)
    service = m.SERVICE_LINE_SHARE * m.ceiling_height(payload, up, floor)
    xyz = scene.xyz.astype(np.float64)

    views = m.plan_views(xyz, up, floor)
    records = []
    for number, view in enumerate(views):
        with np.load(m.lift_cache_path(args.work, view)) as cached:
            for part in np.split(cached["points"], cached["offsets"][1:-1]):
                records.append({"view": number, "points": part})
    print(f"{len(views)} views, {len(records)} outlines from cache", flush=True)

    origin = xyz.min(axis=0)
    cells = np.floor((xyz - origin) / m.VOXEL_M).astype(np.int64)
    dims = cells.max(axis=0) + 1
    voxel_of = (cells[:, 0] * dims[1] + cells[:, 1]) * dims[2] + cells[:, 2]
    options = segment.DEFAULTS
    _, keep = segment.find_planes(
        xyz, up=up, threshold=float(options["plane_distance_m"]), max_planes=int(options["planes_max"]),
        min_fraction=float(options["plane_min_fraction"]), sample_points=int(options["plane_sample"]),
        iterations=int(options["plane_iterations"]), seed=int(options["seed"]), normals=segment.gaussian_normals(scene),
    )

    grades, groups = load_grades(args.grades)
    with np.load(args.graded) as data:
        old_offsets, old_indices = data["offsets"], data["indices"].astype(np.int64)
    old_sizes = np.diff(old_offsets)
    old_owner = np.repeat(np.arange(old_sizes.size), old_sizes)
    old_grade = np.array([grades[index + 1] for index in range(old_sizes.size)])
    # Each old result is one object, or one piece of an object shared with its group.
    old_object = [groups.get(index + 1, f"#{index + 1}") for index in range(old_sizes.size)]
    split_groups = {name for name in groups.values() if sum(1 for value in groups.values() if value == name) > 1}

    settings = [json.loads(args.only)] if args.only else [dict(zip(GRID, values)) for values in itertools.product(*GRID.values())]
    results = []
    cache: dict[tuple, list[dict]] = {}
    for setting in settings:
        started = time.time()
        for name, value in setting.items():
            setattr(m, name, value)
        join_key = (setting["MIN_VIEWS"], setting["JOIN_IOU"], setting["JOIN_CONTAINED"])
        if join_key not in cache:
            cache[join_key] = m.fuse(records, voxel_of)
        boxes = m.boxes_from(cache[join_key], xyz, keep, up, floor, service)

        whole_kept = clutter_kept = merges = 0
        joined: set[str] = set()
        seen_whole: set[int] = set()
        for box in boxes:
            members = box["members"]
            shared = np.bincount(old_owner[np.isin(old_indices, members, assume_unique=False)], minlength=old_sizes.size)
            covers = np.flatnonzero(shared >= 0.5 * old_sizes)
            objects = {old_object[index] for index in covers if old_grade[index] in "wp"}
            if len(objects) >= 2:
                merges += 1
            for name in objects & split_groups:
                pieces = [index for index in range(old_sizes.size) if old_object[index] == name]
                if all(shared[index] >= 0.5 * old_sizes[index] for index in pieces):
                    joined.add(name)
            best = int(np.argmax(shared))
            if shared[best] >= 0.5 * old_sizes[best] and shared[best] >= 0.5 * members.size:
                if old_grade[best] == "w" and best not in seen_whole and len(objects) <= 1:
                    whole_kept += 1
                    seen_whole.add(best)
                if old_grade[best] == "c":
                    clutter_kept += 1
        row = dict(setting, results=len(boxes), whole_kept=whole_kept, clutter_kept=clutter_kept,
                   splits_joined=len(joined), new_merges=merges, seconds=round(time.time() - started, 1))
        results.append(row)
        print(json.dumps(row), flush=True)
    args.out.write_text(json.dumps(results, indent=1))
    print(f"graded whole {int((old_grade == 'w').sum())}, clutter {int((old_grade == 'c').sum())}, split groups {len(split_groups)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
