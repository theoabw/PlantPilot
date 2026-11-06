"""Map builder-pack assets to extracted scene objects.

Every workbook asset becomes exactly one mapping record. A record is either
``proposed``, meaning an extracted object cleared the match rule, or
``unresolved``, meaning none did. An unresolved record keeps its workbook
fields (``asset_id``, ``tag``, ``class``, ``state``, ``issue_code``) and carries
``object_id`` null, ``confidence`` null and a ``reason`` string.

The match rule is a class-and-size prior with two hard gates: a candidate must
reach ``MIN_MATCH_SCORE`` and its size compatibility must reach
``MIN_SIZE_COMPATIBILITY``. The constants below define the whole rule, so a
record can be explained from this file alone.

``confidence`` and ``match_score`` carry the same value. Neither is a
calibrated probability: both are the uncalibrated prior score, and
``confidence`` is kept only because the API and the web viewer already read it.

A record has this shape::

    {
      "asset_id": str,
      "tag": str,
      "object_id": str | null,
      "class": str,
      "state": str,
      "issue_code": str | null,
      "status": "proposed" | "unresolved",
      "method": str,
      "confidence": float | null,
      "match_score": float | null,
      "object_class_proposal": str | null,
      "reason": str | null,
    }
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path


# Workbook asset classes and the extracted object classes that can plausibly
# host them. An object class missing from this table scores as unrelated.
CLASS_COMPATIBILITY = {
    "CONTROL_VALVE": {"valve", "pipe", "machine", "panel", "unknown"},
    "PROCESS_PUMP": {"pump", "motor", "machine", "drum"},
    "ELECTRIC_MOTOR": {"motor", "pump", "machine"},
    # Older pack exports write MOTOR; keep the alias so a renamed column does
    # not silently drop six assets to the unrelated class prior.
    "MOTOR": {"motor", "pump", "machine"},
    "PRESSURE_TRANSMITTER": {"panel", "pipe", "machine", "unknown"},
    "VIBRATION_SENSOR": {"panel", "motor", "pump", "machine", "unknown"},
}

# Prior weights. A class match is stronger evidence than a bounding-box match,
# so the class prior carries most of the score.
CLASS_WEIGHT = 0.7
SIZE_WEIGHT = 0.3

# A candidate is proposed only when its combined prior reaches this score.
# Below it the class and size evidence together are too weak to claim a match.
MIN_MATCH_SCORE = 0.6

# A candidate is proposed only when its bounding-box sizes agree at least this
# well. The size gate is separate from the score so a class match alone can
# never carry an object whose size is clearly wrong.
MIN_SIZE_COMPATIBILITY = 0.5

# Class prior values: the same class, a related class from
# CLASS_COMPATIBILITY, and an unrelated class.
CLASS_EXACT = 1.0
CLASS_RELATED = 0.72
CLASS_UNRELATED = 0.08

# Log-ratio error scale for size compatibility. A summed error of 2.5 over the
# three axes scores 0.0, so the score reaches 1.0 only for equal extents.
SIZE_ERROR_SCALE = 2.5


class MappingError(ValueError):
    """The mapping inputs cannot produce the required artifact."""


def _dimensions(row: dict) -> tuple[float, float, float]:
    values = row.get("extents") or row.get("size") or [1.0, 1.0, 1.0]
    return tuple(max(float(value), 0.001) for value in values[:3])


def _asset_dimensions(asset: dict) -> tuple[float, float, float]:
    return tuple(
        max(float(asset.get(key, 1.0)), 0.001)
        for key in ("bbox_x_m", "bbox_y_m", "bbox_z_m")
    )


def _class_prior(asset_class: str, object_class: str) -> float:
    """Class evidence for one pair, from the compatibility table."""
    if object_class == asset_class.lower():
        return CLASS_EXACT
    if object_class in CLASS_COMPATIBILITY.get(asset_class, set()):
        return CLASS_RELATED
    return CLASS_UNRELATED


def _size_compatibility(asset: dict, obj: dict) -> float:
    """Bounding-box agreement: 1.0 for equal extents, 0.0 at the error scale."""
    asset_dims = _asset_dimensions(asset)
    object_dims = _dimensions(obj)
    errors = [
        abs(math.log(asset_dim / object_dim))
        for asset_dim, object_dim in zip(asset_dims, object_dims)
    ]
    return max(0.0, 1.0 - sum(errors) / (len(errors) * SIZE_ERROR_SCALE))


def _match_score(asset: dict, obj: dict) -> tuple[float, float, str]:
    """Return (prior score, size compatibility, method) for one candidate pair."""
    asset_class = str(asset.get("asset_class", ""))
    object_class = str(obj.get("class", obj.get("class_proposal", "unknown"))).lower()
    class_prior = _class_prior(asset_class, object_class)
    size_compatibility = _size_compatibility(asset, obj)
    score = CLASS_WEIGHT * class_prior + SIZE_WEIGHT * size_compatibility
    method = "class_and_size_prior" if class_prior >= CLASS_RELATED else "size_prior"
    return score, size_compatibility, method


def _clears_match_rule(score: float, size_compatibility: float) -> bool:
    return score >= MIN_MATCH_SCORE and size_compatibility >= MIN_SIZE_COMPATIBILITY


def _base_record(asset: dict) -> dict:
    """The workbook fields every record keeps, proposed or unresolved."""
    return {
        "asset_id": asset.get("asset_id"),
        "tag": asset.get("tag"),
        "class": asset.get("asset_class"),
        "state": asset.get("condition_state", "unknown"),
        "issue_code": asset.get("issue_code"),
    }


def map_assets(pack: dict, objects_payload: dict, output: Path) -> dict:
    assets = list(pack.get("assets", []))
    objects = list(objects_payload.get("objects", []))
    if not assets:
        raise MappingError("pack contains no assets")
    if not objects:
        raise MappingError("objects artifact contains no objects")
    if len(objects) < len(assets):
        raise MappingError(f"{len(objects)} objects cannot hold {len(assets)} assets distinctly")

    # Each proposed object is removed from `unused`, so one object is never
    # offered to a second tag and a record is never re-pointed after it is set.
    unused = {str(obj["id"]): obj for obj in objects}
    mappings = []
    for asset in assets:
        scored = [
            (_match_score(asset, obj), obj)
            for obj in unused.values()
        ]
        if not scored:
            raise MappingError(f"no object remains for {asset.get('tag', asset.get('asset_id'))}")
        (best_score, _, _), _ = max(
            scored,
            key=lambda item: (item[0][0], -int(item[1].get("points", 0)), str(item[1]["id"])),
        )
        candidates = [
            (pair, obj)
            for pair, obj in scored
            if _clears_match_rule(pair[0], pair[1])
        ]
        if not candidates:
            mappings.append({
                **_base_record(asset),
                "object_id": None,
                "status": "unresolved",
                "method": "unresolved",
                "confidence": None,
                "match_score": None,
                "object_class_proposal": None,
                "reason": (
                    f"no object cleared match score {MIN_MATCH_SCORE:.2f} "
                    f"and size compatibility {MIN_SIZE_COMPATIBILITY:.2f}; "
                    f"best match score {best_score:.3f}"
                ),
            })
            continue

        (score, _, method), obj = max(
            candidates,
            key=lambda item: (item[0][0], -int(item[1].get("points", 0)), str(item[1]["id"])),
        )
        object_id = str(obj["id"])
        unused.pop(object_id)
        score = round(float(score), 3)
        mappings.append({
            **_base_record(asset),
            "object_id": object_id,
            "status": "proposed",
            "method": method,
            "confidence": score,
            "match_score": score,
            "object_class_proposal": obj.get("class", obj.get("class_proposal", "unknown")),
            "reason": None,
        })

    proposed = sum(1 for mapping in mappings if mapping["status"] == "proposed")
    unresolved = sum(1 for mapping in mappings if mapping["status"] == "unresolved")
    target = pack.get("target", {})
    target_mapping = next(
        (mapping for mapping in mappings if mapping["asset_id"] == target.get("asset_id")),
        None,
    )
    if target_mapping is None:
        raise MappingError(f"target asset {target.get('asset_id')} is not in the pack")
    payload = {
        "artifact": "mapped",
        "version": 1,
        "source": {
            "pack": str(pack.get("source", {}).get("file", "pack.json")),
            "objects": str(objects_payload.get("source", {}).get("scene", "objects.json")),
        },
        "counts": {
            "assets": len(assets),
            "mapped": proposed,
            "unresolved": unresolved,
            "unmapped_objects": len(unused),
        },
        "target_asset_id": target_mapping["asset_id"],
        "target_tag": target_mapping["tag"],
        "target_object_id": target_mapping["object_id"],
        "mappings": mappings,
        "unmapped_object_ids": sorted(unused),
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Map builder-pack assets to scene objects.")
    parser.add_argument("--pack", type=Path, default=Path("data/scene/pack.json"))
    parser.add_argument("--objects", type=Path, default=Path("data/scene/objects.json"))
    parser.add_argument("--out", type=Path, default=Path("data/scene/mapped.json"))
    args = parser.parse_args(argv)
    try:
        payload = map_assets(
            json.loads(args.pack.read_text()),
            json.loads(args.objects.read_text()),
            args.out,
        )
    except (OSError, json.JSONDecodeError, KeyError, MappingError) as exc:
        print(f"mapping failed: {exc}", file=sys.stderr)
        return 1
    print(f"assets             {payload['counts']['assets']}")
    print(f"mapped             {payload['counts']['mapped']}")
    print(f"unresolved         {payload['counts']['unresolved']}")
    print(f"target             {payload['target_tag']} ({payload['target_object_id']})")
    print(f"unmapped objects   {payload['counts']['unmapped_objects']}")
    print(f"wrote              {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
