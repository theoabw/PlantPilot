"""Measure whether the framed objects are whole instances or sliced fragments.

The extraction stage fits one box per connected component, and this script is
the check on what those boxes actually cover. It answers three questions from
the artifacts alone, so it can be run before and after a change:

- For each reviewed anchor: how many object boxes stand in that anchor's own
  column above the floor, and does one box span it. A washing machine framed as
  three stacked bands is the defect this counts.
- How many framed objects float in mid air with nothing under them: a box whose
  bottom sits well above the floor and whose footprint holds no box below it is
  a band of a larger shape, not an object.
- How much of the capture the boxes cover, and how much of it is covered twice:
  a box count is only useful if the boxes land on the points.

The output is a JSON artifact plus an optional Markdown table, so a number in
the README can be traced to a command. Nothing here changes an artifact.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

UP_BY_NAME = {"x": 0, "y": 1, "z": 2}


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
    """The floor plane's position along the up axis, in the artifact's frame.

    `objects.json` stores the floor as a plane normal and a signed height, and
    the extraction stage measures a box's `height_above_floor` as
    `p @ normal - height`. With the normal within a few degrees of the up axis,
    `p @ up - height` is the same quantity, so a box span can be reported in
    metres above the floor.
    """
    floor = payload.get("floor") or {}
    height = floor.get("height")
    if height is None:
        raise ValueError("the objects artifact has no usable floor plane")
    return float(height)


def box_vertical_span(box: dict, up: np.ndarray, origin: float = 0.0) -> tuple[float, float]:
    """The lowest and highest height of an oriented box above the floor plane.

    `origin` is the floor plane's position on the up axis, so the result is in
    metres above the floor. The span is the projection of the eight corners.
    """
    centre = np.asarray(box["centre"], dtype=np.float64)
    axes = np.asarray(box["axes"], dtype=np.float64)
    extents = np.asarray(box["extents"], dtype=np.float64)
    middle = float(centre @ up) - float(origin)
    half = 0.5 * float(np.sum(np.abs(axes @ up) * extents))
    return middle - half, middle + half


def box_footprint(box: dict, up: np.ndarray) -> tuple[float, float, float, float]:
    """The box's world-aligned footprint on the floor plane: x0, x1, z0, z1.

    The captures are framed with the up axis on y, so the footprint axes are x
    and z. A box that is rotated about the up axis is enclosed by its footprint
    rectangle, which is what the column test wants: does this box stand over
    that floor patch.
    """
    centre = np.asarray(box["centre"], dtype=np.float64)
    axes = np.asarray(box["axes"], dtype=np.float64)
    extents = np.asarray(box["extents"], dtype=np.float64)
    # axes holds one box axis per row: project the matching column, not the row.
    reach = 0.5 * (np.abs(axes.T) @ extents)
    vertical = UP_BY_NAME["y"]
    horizontal = [axis for axis in range(3) if axis != vertical]
    return (
        float(centre[horizontal[0]] - reach[horizontal[0]]),
        float(centre[horizontal[0]] + reach[horizontal[0]]),
        float(centre[horizontal[1]] - reach[horizontal[1]]),
        float(centre[horizontal[1]] + reach[horizontal[1]]),
    )


def footprint_overlap(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
    *,
    by_smaller: bool = False,
) -> float:
    """The share of the first footprint covered by the second, in [0, 1].

    `by_smaller` divides by the smaller of the two areas instead. That is the
    right denominator for asking whether two boxes describe the same ground
    patch: a small box inside a large one is the same object seen twice, while
    dividing by the large box would call it a different object.
    """
    width = min(first[1], second[1]) - max(first[0], second[0])
    depth = min(first[3], second[3]) - max(first[2], second[2])
    if width <= 0.0 or depth <= 0.0:
        return 0.0
    own = max((first[1] - first[0]) * (first[3] - first[2]), 1e-9)
    other = max((second[1] - second[0]) * (second[3] - second[2]), 1e-9)
    area = min(own, other) if by_smaller else own
    return float(width * depth / area)


def points_inside_box(points: np.ndarray, box: dict, margin: float = 0.0) -> np.ndarray:
    """A mask of the points inside an oriented box, grown by `margin`."""
    centre = np.asarray(box["centre"], dtype=np.float64)
    axes = np.asarray(box["axes"], dtype=np.float64)
    extents = np.asarray(box["extents"], dtype=np.float64)
    local = (points - centre) @ axes.T
    return np.all(np.abs(local) <= extents / 2.0 + margin, axis=1)


def column_boxes(anchor: dict, objects: list[dict], up: np.ndarray, origin: float, floor_gap: float = 0.10) -> list[dict]:
    """The objects that stand in an anchor's own column above the floor.

    A box belongs to the column when the two footprints agree on the ground: the
    overlap is at least 60 percent of the smaller footprint, so a small box
    inside a larger one counts and so does a larger box that contains the
    anchor. Its vertical span must reach above the floor.
    The anchor's top bounds the column, so a box that merely hangs overhead is
    not counted, and a box that sits beside the anchor is not counted either.
    """
    anchor_low, anchor_high = box_vertical_span(anchor, up, origin)
    anchor_foot = box_footprint(anchor, up)
    found = []
    for obj in objects:
        low, high = box_vertical_span(obj, up, origin)
        if high < anchor_low - floor_gap or low > anchor_high + 2 * floor_gap:
            continue
        share = footprint_overlap(box_footprint(obj, up), anchor_foot, by_smaller=True)
        if share < 0.6:
            continue
        found.append({"id": obj["id"], "class": obj["class"], "low": low, "high": high, "footprint_share": share})
    found.sort(key=lambda row: row["low"])
    return found


def floating_objects(objects: list[dict], up: np.ndarray, origin: float, *, floor_clearance: float = 0.15, support_gap: float = 0.12) -> list[dict]:
    """Objects whose bottom is in mid air with nothing under them.

    A box that starts `floor_clearance` above the floor is only a whole object
    when something supports it: a box underneath whose top reaches within
    `support_gap` of this box's bottom and whose footprint covers half of it.
    Anything else is a band cut out of a larger shape.
    """
    spans = {obj["id"]: box_vertical_span(obj, up, origin) for obj in objects}
    feet = {obj["id"]: box_footprint(obj, up) for obj in objects}
    floating = []
    for obj in objects:
        low, high = spans[obj["id"]]
        if low < floor_clearance:
            continue
        supported = False
        for other in objects:
            if other["id"] == obj["id"]:
                continue
            other_low, other_high = spans[other["id"]]
            if other_high > low + support_gap or other_high < low - 4 * support_gap:
                continue
            if other_high < low - support_gap:
                continue
            if footprint_overlap(feet[obj["id"]], feet[other["id"]]) < 0.5:
                continue
            supported = True
            break
        if not supported:
            floating.append({"id": obj["id"], "class": obj["class"], "low": low, "high": high})
    floating.sort(key=lambda row: row["low"], reverse=True)
    return floating


def coverage(points: np.ndarray, objects: list[dict]) -> dict:
    """How many boxes each point falls inside, as a histogram."""
    counts = np.zeros(points.shape[0], dtype=np.int16)
    for obj in objects:
        counts += points_inside_box(points, obj).astype(np.int16)
    total = int(points.shape[0])
    return {
        "points": total,
        "inside_one": int(np.count_nonzero(counts == 1)),
        "inside_two": int(np.count_nonzero(counts == 2)),
        "inside_three_or_more": int(np.count_nonzero(counts >= 3)),
        "inside_none": int(np.count_nonzero(counts == 0)),
    }


def audit(payload: dict, anchors: list[dict] | None, points: np.ndarray | None) -> dict:
    up = up_vector(payload.get("source", {}))
    origin = floor_origin(payload)
    objects = payload.get("objects", [])
    result: dict = {
        "artifact": "object-audit",
        "version": 1,
        "capture": payload.get("source", {}).get("capture"),
        "counts": payload.get("counts", {}),
        "objects": len(objects),
        "floor_plane": payload.get("floor"),
        "anchors": [],
        "floating": [],
    }
    # A box's height above the floor: the artifacts store the floor plane, and
    # the vertical span is measured against the same origin.
    spans = {obj["id"]: box_vertical_span(obj, up, origin) for obj in objects}
    result["object_shapes"] = {
        "under_0m4": sum(1 for obj in objects if spans[obj["id"]][1] - spans[obj["id"]][0] < 0.4),
        "under_0m25": sum(1 for obj in objects if spans[obj["id"]][1] - spans[obj["id"]][0] < 0.25),
        "total": len(objects),
    }
    for anchor in anchors or []:
        # The column test uses the tight box a visual review accepted, not a box
        # that was later completed: otherwise the same anchor measures a
        # different ground patch before and after a completion change.
        column_anchor = dict(anchor.get("reviewed_box") or anchor)
        column = column_boxes(column_anchor, objects, up, origin)
        anchor_low, anchor_high = box_vertical_span(column_anchor, up, origin)
        tallest = max(column, key=lambda row: row["high"] - row["low"]) if column else None
        result["anchors"].append(
            {
                "id": anchor.get("id"),
                "label": anchor.get("label"),
                "anchor_low": anchor_low,
                "anchor_high": anchor_high,
                "anchor_height": anchor_high - anchor_low,
                "column_objects": len(column),
                "column": column,
                "tallest": tallest,
                "tallest_height": None if tallest is None else tallest["high"] - tallest["low"],
                "tallest_low": None if tallest is None else tallest["low"],
                "span_is_one_box": len(column) == 1,
                "sam3_extent_ratio": (anchor.get("sam3") or {}).get("extent_ratio"),
            }
        )
    result["floating"] = floating_objects(objects, up, origin)
    by_class: dict[str, int] = {}
    for row in result["floating"]:
        by_class[row["class"]] = by_class.get(row["class"], 0) + 1
    result["floating_by_class"] = dict(sorted(by_class.items()))
    if points is not None:
        result["coverage"] = coverage(points, objects)
    return result


def summary(result: dict) -> str:
    """The audit as a short Markdown table for a document."""
    lines = [
        f"Capture: {result['capture']}",
        "",
        f"Objects: {result['objects']}, clusters: {result['counts'].get('clusters')}, "
        f"capped: {result['counts'].get('capped')}",
        f"Objects under 0.40 m tall: {result['object_shapes']['under_0m4']} of {result['object_shapes']['total']}",
        f"Objects floating with nothing under them: {len(result['floating'])} "
        f"({', '.join(f'{name} {count}' for name, count in result.get('floating_by_class', {}).items())})",
        "",
    ]
    if result["anchors"]:
        lines.append("| Anchor | Label | Boxes in the column | Tallest box height | Tallest box floor gap |")
        lines.append("| --- | --- | --- | --- | --- |")
        for row in result["anchors"]:
            height = "n/a" if row["tallest_height"] is None else f"{row['tallest_height']:.2f} m"
            gap = "n/a" if row["tallest_low"] is None else f"{row['tallest_low']:.2f} m"
            lines.append(f"| {row['id']} | {row['label']} | {row['column_objects']} | {height} | {gap} |")
        lines.append("")
    if "coverage" in result:
        covered = result["coverage"]
        total = max(covered["points"], 1)
        lines.append(
            f"Point coverage: {covered['inside_one'] / total:.1%} in one box, "
            f"{covered['inside_two'] / total:.1%} in two, "
            f"{covered['inside_three_or_more'] / total:.1%} in three or more, "
            f"{covered['inside_none'] / total:.1%} in none"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python scripts/object_audit.py",
        description="Measure whether the framed objects are whole instances or sliced fragments.",
    )
    parser.add_argument("--objects", default=Path("data/equipment/objects.json"), type=Path)
    parser.add_argument("--anchors", default=Path("fixtures/scene/anchors_equipment.json"), type=Path,
                        help="reviewed anchors to test the columns of; skip with --no-anchors")
    parser.add_argument("--scene", default=None, type=Path,
                        help="scene artifact, to measure how much of the capture the boxes cover")
    parser.add_argument("--out", default=None, type=Path)
    parser.add_argument("--markdown", action="store_true", help="print the summary table instead of the JSON")
    parser.add_argument("--no-anchors", action="store_true")
    args = parser.parse_args(argv)

    payload = json.loads(args.objects.read_text())
    anchors = None
    if not args.no_anchors and args.anchors.exists():
        anchors = json.loads(args.anchors.read_text()).get("anchors", [])
    points = None
    if args.scene is not None:
        sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "server" / "src"))
        from plantpilot.splat import load_scene  # local import: only needed for coverage

        points = load_scene(args.scene).xyz.astype(np.float64)
    result = audit(payload, anchors, points)
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=1) + "\n")
    print(summary(result) if args.markdown else json.dumps(result, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
