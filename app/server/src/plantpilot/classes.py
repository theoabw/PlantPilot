"""Refine the geometric class proposals with context, and refuse what shape cannot support.

`segment.py` fits a box and proposes a class from the box's shape. Shape alone
cannot separate a valve from a chair seat: both are compact boxes standing off
the floor, and the supplied capture contains both. A framed scene carries two
more pieces of evidence, and this stage uses them.

- A valve is fitted into pipework, so a valve proposal needs a pipe or duct box
  touching or nearly touching it.
- A pump, motor, machine, drum, cabinet or pallet stands on something, so a
  standing proposal needs floor contact or a box underneath it.
- Where a proposal cannot be supported by either test, the class becomes
  `object`. A generic label that is true beats a specific one that is not, and
  `class_reason` says which test failed, so a reader can see why the label
  changed instead of having to trust it.

Structural classes are shape descriptions rather than identity claims and are
left alone. This stage rewrites `class`, `class_confidence` and `class_reason`
only: ids, boxes, counts by object and order are unchanged, so mapping, route
and viewer read the same geometry they read before. It is deterministic and
offline, and it reads and writes the objects artifact.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

# A standing object is on the floor when its lowest face is this close to it.
FLOOR_SUPPORT_M = 0.15
# A box supports the one above it when their faces are this close.
STACK_SUPPORT_M = 0.12
# A valve is fitted to pipework when a pipe or duct box is this close to it.
PIPEWORK_REACH_M = 0.50
# The shared ground share that makes two footprints the same ground patch.
FOOTPRINT_SHARE = 0.50
# A fused instance names an object when their centres agree this closely and
# their footprints share half the smaller one; the fusion box is fitted from
# rendered views, the object box from the capture's own components.
INSTANCE_MATCH_M = 0.40

UP_BY_NAME = {"x": 0, "y": 1, "z": 2}

STRUCTURAL = frozenset({"pipe", "duct", "beam", "panel", "surface", "structure", "ladder", "door", "tray", "unknown"})
STANDING = frozenset({"pump", "motor", "machine", "drum", "cabinet", "pallet"})
FITTED = frozenset({"valve"})
PIPEWORK = frozenset({"pipe", "duct"})


def up_vector(source: dict) -> np.ndarray:
    """The scene's up axis as a unit vector, from the objects artifact."""
    axis_name = str(source.get("up_axis", "+y"))
    sign = -1.0 if axis_name.startswith("-") else 1.0
    letter = axis_name[-1].lower()
    if letter not in UP_BY_NAME:
        raise ValueError(f"unreadable up axis {axis_name!r}")
    vector = np.zeros(3)
    vector[UP_BY_NAME[letter]] = sign
    return vector


def floor_origin(payload: dict) -> float:
    """The floor plane's position along the up axis, in the artifact's frame."""
    floor = payload.get("floor") or {}
    height = floor.get("height")
    if height is None:
        raise ValueError("the objects artifact has no usable floor plane")
    return float(height)


def vertical_span(box: dict, up: np.ndarray, origin: float) -> tuple[float, float]:
    """The lowest and highest height of an oriented box above the floor."""
    centre = np.asarray(box["centre"], dtype=np.float64)
    axes = np.asarray(box["axes"], dtype=np.float64)
    extents = np.asarray(box["extents"], dtype=np.float64)
    middle = float(centre @ up) - float(origin)
    half = 0.5 * float(np.sum(np.abs(axes @ up) * extents))
    return middle - half, middle + half


def footprint(box: dict, up: np.ndarray) -> tuple[float, float, float, float]:
    """The box's footprint on the floor plane as x0, x1, z0, z1.

    The captures are framed with the up axis on y, so the footprint axes are x
    and z. A box rotated about the up axis is enclosed by this rectangle, which
    is the right shape for "do these two stand on the same ground".
    """
    centre = np.asarray(box["centre"], dtype=np.float64)
    axes = np.asarray(box["axes"], dtype=np.float64)
    extents = np.asarray(box["extents"], dtype=np.float64)
    # axes holds one box axis per row, so projecting onto a world axis sums
    # the matching column over the rows: |axes.T| @ extents, never |axes| @ extents.
    reach = 0.5 * (np.abs(axes.T) @ extents)
    vertical = UP_BY_NAME["y"]
    horizontal = [axis for axis in range(3) if axis != vertical]
    return (
        float(centre[horizontal[0]] - reach[horizontal[0]]),
        float(centre[horizontal[0]] + reach[horizontal[0]]),
        float(centre[horizontal[1]] - reach[horizontal[1]]),
        float(centre[horizontal[1]] + reach[horizontal[1]]),
    )


def footprint_overlap(first: tuple[float, float, float, float], second: tuple[float, float, float, float]) -> float:
    """The share of the smaller footprint covered by the other, in [0, 1]."""
    width = min(first[1], second[1]) - max(first[0], second[0])
    depth = min(first[3], second[3]) - max(first[2], second[2])
    if width <= 0.0 or depth <= 0.0:
        return 0.0
    smaller = min(
        (first[1] - first[0]) * (first[3] - first[2]),
        (second[1] - second[0]) * (second[3] - second[2]),
    )
    return float(width * depth / max(smaller, 1e-9))


def box_gap(first: dict, second: dict) -> float:
    """The distance between two oriented boxes along their best separating axis.

    Each axis of both boxes is tried; the largest per-axis separation is the
    distance between the boxes when they do not overlap, and a negative number
    when they do. This is the separating axis test for near-parallel boxes, which
    is what industrial frames are.
    """
    centre_first = np.asarray(first["centre"], dtype=np.float64)
    centre_second = np.asarray(second["centre"], dtype=np.float64)
    axes_first = np.asarray(first["axes"], dtype=np.float64)
    axes_second = np.asarray(second["axes"], dtype=np.float64)
    extents_first = np.asarray(first["extents"], dtype=np.float64)
    extents_second = np.asarray(second["extents"], dtype=np.float64)
    delta = centre_second - centre_first
    separation = -np.inf
    for axis in np.vstack([axes_first, axes_second]):
        axis = axis / max(float(np.linalg.norm(axis)), 1e-12)
        reach_first = 0.5 * float(np.sum(np.abs(axes_first @ axis) * extents_first))
        reach_second = 0.5 * float(np.sum(np.abs(axes_second @ axis) * extents_second))
        separation = max(separation, abs(float(delta @ axis)) - reach_first - reach_second)
    return float(separation)


def standing_supported(obj: dict, objects: list[dict], up: np.ndarray, origin: float) -> tuple[bool, str]:
    """Whether a standing proposal has the floor or another box under it."""
    low, _ = vertical_span(obj, up, origin)
    if low <= FLOOR_SUPPORT_M:
        return True, f"rests on the floor, lowest face {low:.2f} m above it"
    own = footprint(obj, up)
    for other in objects:
        if other["id"] == obj["id"]:
            continue
        _, other_high = vertical_span(other, up, origin)
        if abs(other_high - low) > STACK_SUPPORT_M:
            continue
        if footprint_overlap(own, footprint(other, up)) < FOOTPRINT_SHARE:
            continue
        return True, f"stands on {other['id']} at {other_high:.2f} m"
    return False, f"nothing under it: lowest face {low:.2f} m above the floor and no box reaches it"


def fitted_supported(obj: dict, objects: list[dict]) -> tuple[bool, str]:
    """Whether a valve proposal has pipework to be fitted into."""
    best: tuple[float, str] | None = None
    for other in objects:
        if other["id"] == obj["id"] or other["class"] not in PIPEWORK:
            continue
        gap = box_gap(obj, other)
        if gap <= PIPEWORK_REACH_M and (best is None or gap < best[0]):
            best = (gap, other["id"])
    if best is None:
        return False, f"no pipe or duct box within {PIPEWORK_REACH_M:.2f} m to fit into"
    return True, f"fitted to {best[1]} at {best[0]:.2f} m"


def instance_label(obj: dict, instances: list[dict], up: np.ndarray) -> dict | None:
    """The fused instance that sits on the same object, if one does."""
    centre = np.asarray(obj["centre"], dtype=np.float64)
    own = footprint(obj, up)
    best: tuple[float, dict] | None = None
    for instance in instances:
        distance = float(np.linalg.norm(np.asarray(instance["centre"], dtype=np.float64) - centre))
        if distance > INSTANCE_MATCH_M:
            continue
        if footprint_overlap(own, footprint(instance, up)) < FOOTPRINT_SHARE:
            continue
        if best is None or distance < best[0]:
            best = (distance, instance)
    return None if best is None else {**best[1], "centre_distance_m": round(best[0], 3)}


def refine(payload: dict, instances: list[dict] | None = None) -> dict:
    """Name what the fusion measured, then rewrite what shape alone cannot support."""
    up = up_vector(payload.get("source", {}))
    origin = floor_origin(payload)
    objects = payload.get("objects", [])
    rewritten = 0
    generic = 0
    named = 0
    decisions: list[dict] = []
    for obj in objects:
        instance = instance_label(obj, instances or [], up)
        if instance is not None:
            previous = obj.get("class")
            obj["class"] = str(instance["object_class"])
            obj["class_confidence"] = 0.9
            obj["class_reason"] = (
                f"matches the multi-view fused instance {instance['label']} "
                f"({instance.get('views') or '?'} views, score {instance.get('score')}); "
                f"the centre agrees within {instance['centre_distance_m']:.2f} m"
            )
            obj["class_source"] = "multi_view_instance_fusion"
            named += 1
            if previous != obj["class"]:
                decisions.append({"id": obj["id"], "from": previous, "to": obj["class"], "reason": "named by fusion"})
            continue
        class_name = obj.get("class")
        if class_name in STRUCTURAL:
            continue
        if class_name in STANDING:
            supported, reason = standing_supported(obj, objects, up, origin)
        elif class_name in FITTED:
            supported, reason = fitted_supported(obj, objects)
        else:
            continue
        if supported:
            obj["class_confidence"] = round(min(float(obj.get("class_confidence", 0.3)), 0.5), 2)
            obj["class_reason"] = f"{class_name}: {reason}"
            continue
        decisions.append({"id": obj["id"], "from": class_name, "reason": reason})
        obj["class"] = "object"
        obj["class_confidence"] = round(min(float(obj.get("class_confidence", 0.3)), 0.2), 2)
        obj["class_reason"] = f"kept generic: the {class_name} proposal cannot be supported, {reason}"
        rewritten += 1
        if obj["class"] == "object":
            generic += 1

    counts = payload.setdefault("counts", {})
    histogram: dict[str, int] = {}
    for obj in objects:
        histogram[obj["class"]] = histogram.get(obj["class"], 0) + 1
    counts["objects_by_class"] = dict(sorted(histogram.items()))
    counts["labels_generic"] = generic
    counts["labels_fused"] = named
    payload["classes"] = {
        "stage": "context",
        "rules": {
            "floor_support_m": FLOOR_SUPPORT_M,
            "stack_support_m": STACK_SUPPORT_M,
            "pipework_reach_m": PIPEWORK_REACH_M,
            "footprint_share": FOOTPRINT_SHARE,
        },
        "structural_classes": sorted(STRUCTURAL),
        "standing_classes": sorted(STANDING),
        "fitted_classes": sorted(FITTED),
        "rewritten": rewritten,
        "named_by_fusion": named,
        "decisions": decisions,
    }
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m plantpilot.classes",
        description="Refine the geometric class proposals with context and an honest fallback.",
    )
    parser.add_argument("--objects", default=Path("data/scene/objects.json"), type=Path)
    parser.add_argument("--out", default=None, type=Path)
    parser.add_argument("--instances", default=None, type=Path,
                        help="fused instances fixture; when absent, only the context rules run")
    args = parser.parse_args(argv)

    payload = json.loads(args.objects.read_text())
    instances = None
    if args.instances is not None and args.instances.exists():
        instances = json.loads(args.instances.read_text()).get("instances", [])
    refined = refine(payload, instances)
    out = args.out or args.objects
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(refined, indent=1) + "\n")
    record = refined["classes"]
    print(
        f"classes {len(refined['objects'])} objects, {record['named_by_fusion']} named by fusion, "
        f"{record['rewritten']} generic after context"
    )
    for entry in record["decisions"][:20]:
        print(f"  {entry['id']} {entry['from']:<10} -> object: {entry['reason']}")
    if len(record["decisions"]) > 20:
        print(f"  and {len(record['decisions']) - 20} more")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
