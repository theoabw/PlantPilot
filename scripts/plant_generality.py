"""Score the extraction against the reference plant's ground truth.

The same `plantpilot.segment` command that framed the supplied boiler room is
run on the reference plant, and this script asks the honest question: did a box
land on each of the ten known assets, and is that box a box around the asset
rather than around half the room?

The pass rule is the one docs/acceptance.md fixes for the scene-agnostic claim:
at least 8 of the 10 assets framed with a box that contains the asset's true
position, and no such box more than three times the asset's footprint.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "fixtures" / "plant" / "plant.json"
OBJECTS = ROOT / "data" / "plant" / "objects.json"

FOOTPRINT_FACTOR = 3.0
PASS_MARK = 8


def corners(box: dict) -> np.ndarray:
    """The eight world corners of an object box."""
    centre = np.asarray(box["centre"], dtype=np.float64)
    axes = np.asarray(box["axes"], dtype=np.float64)
    half = np.asarray(box["extents"], dtype=np.float64) / 2.0
    offsets = np.array([[sx, sy, sz] for sx in (-1.0, 1.0) for sy in (-1.0, 1.0) for sz in (-1.0, 1.0)])
    return centre[None, :] + (offsets * half[None, :]) @ axes


def contains(box: dict, point, slack: float = 0.05) -> bool:
    """True when the point is inside the oriented box."""
    axes = np.asarray(box["axes"], dtype=np.float64)
    extents = np.asarray(box["extents"], dtype=np.float64)
    local = (np.asarray(point, dtype=np.float64) - np.asarray(box["centre"], dtype=np.float64)) @ axes.T
    return bool(np.all(np.abs(local) <= extents / 2.0 + slack))


def horizontal_extents(box: dict) -> tuple[float, float]:
    """The box footprint measured along the world x and z axes."""
    world = corners(box)
    return float(np.ptp(world[:, 0])), float(np.ptp(world[:, 2]))


def asset_centre(asset: dict) -> np.ndarray:
    """The centre of the asset volume. `pos` is its footprint centre on the floor."""
    x, y, z = asset["pos"]
    return np.array([x, y + asset["size"][1] / 2.0, z], dtype=np.float64)


def score(objects: list[dict], assets: list[dict]) -> list[dict]:
    """One record per ground truth asset: the smallest box that frames it, or None."""
    results = []
    for asset in assets:
        centre = asset_centre(asset)
        sx, _, sz = asset["size"]
        candidates = [obj for obj in objects if contains(obj, centre)]
        candidates.sort(key=lambda obj: float(obj["volume_m3"]))
        framed = None
        for candidate in candidates:
            ex, ez = horizontal_extents(candidate)
            if ex <= FOOTPRINT_FACTOR * max(sx, 0.2) and ez <= FOOTPRINT_FACTOR * max(sz, 0.2):
                framed = candidate
                break
        results.append({
            "id": asset["id"],
            "kind": asset["kind"],
            "centre": [round(float(value), 3) for value in centre],
            "size": list(asset["size"]),
            "contained_by": None if not candidates else candidates[0]["id"],
            "framed_by": None if framed is None else framed["id"],
            "class": None if framed is None else framed["class"],
            "extents": None if framed is None else framed["extents"],
            "framed": framed is not None,
        })
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python scripts/plant_generality.py",
        description="Compare the extracted boxes on the reference plant with its ground truth.",
    )
    parser.add_argument("--objects", default=OBJECTS, type=Path)
    parser.add_argument("--spec", default=SPEC, type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    objects_path = Path(args.objects)
    if not objects_path.exists():
        raise SystemExit(f"no objects artifact at {objects_path}; run the pipeline on the plant first")
    payload = json.loads(objects_path.read_text())
    spec = json.loads(Path(args.spec).read_text())
    results = score(payload["objects"], spec["assets"])
    framed = sum(1 for record in results if record["framed"])
    report = {
        "scene": payload.get("source", {}).get("scene"),
        "objects_framed": payload.get("counts", {}).get("objects"),
        "ground_truth_assets": len(results),
        "assets_framed": framed,
        "pass_mark": PASS_MARK,
        "pass": framed >= PASS_MARK,
        "footprint_factor": FOOTPRINT_FACTOR,
        "assets": results,
    }

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        for record in results:
            if record["framed"]:
                print(f"framed      {record['id']:6s} {record['kind']:8s} by {record['framed_by']} {record['class']:8s} "
                      f"extents {record['extents']}")
            else:
                contained = record["contained_by"] or "nothing"
                print(f"not framed  {record['id']:6s} {record['kind']:8s} asset {record['size']} contained by {contained}")
        print(f"assets framed {framed} of {len(results)} against ground truth, pass mark {PASS_MARK}")
        print(f"objects framed on this scene {report['objects_framed']}")
        print("PASS" if report["pass"] else "FAIL")
    return 0 if report["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
