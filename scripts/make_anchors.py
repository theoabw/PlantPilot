"""Build the reviewed anchor artifact from the fixture and the scene.

Scratch-to-product bridge for the demo layer: the fixture holds the boxes a
human review accepted, and this stage validates them against the capture and
adds the evidence the viewer shows (owned gaussians, mean colour, provenance).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from plantpilot import splat


def points_in_box(xyz: np.ndarray, centre: np.ndarray, axes: np.ndarray, extents: np.ndarray) -> np.ndarray:
    """Boolean mask for the points inside an oriented box."""
    local = (xyz - centre) @ axes.T
    return np.all(np.abs(local) <= extents / 2.0 + 1e-9, axis=1)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scene", required=True)
    parser.add_argument("--fixture", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    scene = splat.load_scene(Path(args.scene))
    fixture = json.loads(Path(args.fixture).read_text())
    anchors = []
    for entry in fixture["anchors"]:
        centre = np.asarray(entry["centre"], dtype=float)
        axes = np.asarray(entry["axes"], dtype=float)
        extents = np.asarray(entry["extents"], dtype=float)
        inside = points_in_box(scene.xyz, centre, axes, extents)
        count = int(inside.sum())
        if count == 0:
            raise SystemExit(f"{entry['id']}: no gaussians inside the reviewed box")
        mean_rgb = scene.rgb[inside].mean(axis=0).round().astype(int).tolist()
        anchors.append({
            **entry,
            "points": count,
            "mean_rgb": mean_rgb,
        })
    payload = {
        "artifact": "anchors",
        "version": 1,
        "source": {"scene": args.scene, "fixture": args.fixture},
        "counts": {"anchors": len(anchors)},
        "anchors": anchors,
    }
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(payload, indent=2) + "\n")
    total = sum(anchor["points"] for anchor in anchors)
    print(f"anchors {len(anchors)}, gaussians in reviewed boxes {total}")
    for anchor in anchors:
        print(f"  {anchor['id']} {anchor['label']:<24} {anchor['points']:6d} pts  rgb {anchor['mean_rgb']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
