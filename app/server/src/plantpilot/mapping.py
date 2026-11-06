"""Map builder-pack assets to extracted scene objects."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path


CLASS_COMPATIBILITY = {
    "CONTROL_VALVE": {"valve", "pipe", "machine", "panel", "unknown"},
    "PROCESS_PUMP": {"pump", "motor", "machine", "drum"},
    "MOTOR": {"motor", "pump", "machine"},
    "PRESSURE_TRANSMITTER": {"panel", "pipe", "machine", "unknown"},
    "VIBRATION_SENSOR": {"panel", "motor", "pump", "machine", "unknown"},
}


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


def _class_score(asset_class: str, object_class: str) -> float:
    allowed = CLASS_COMPATIBILITY.get(asset_class, set())
    if object_class == asset_class.lower():
        return 1.0
    if object_class in allowed:
        return 0.72
    return 0.08


def _size_score(asset: dict, obj: dict) -> float:
    asset_dims = _asset_dimensions(asset)
    object_dims = _dimensions(obj)
    errors = [
        abs(math.log(asset_dim / object_dim))
        for asset_dim, object_dim in zip(asset_dims, object_dims)
    ]
    return max(0.0, 1.0 - sum(errors) / (len(errors) * 2.5))


def _score(asset: dict, obj: dict) -> tuple[float, str]:
    asset_class = str(asset.get("asset_class", ""))
    object_class = str(obj.get("class", obj.get("class_proposal", "unknown"))).lower()
    class_score = _class_score(asset_class, object_class)
    size_score = _size_score(asset, obj)
    score = 0.7 * class_score + 0.3 * size_score
    method = "class_and_size_prior" if class_score >= 0.7 else "size_prior"
    return score, method


def map_assets(pack: dict, objects_payload: dict, output: Path) -> dict:
    assets = list(pack.get("assets", []))
    objects = list(objects_payload.get("objects", []))
    if not assets:
        raise MappingError("pack contains no assets")
    if not objects:
        raise MappingError("objects artifact contains no objects")
    if len(objects) < len(assets):
        raise MappingError(f"{len(objects)} objects cannot hold {len(assets)} assets distinctly")

    unused = {str(obj["id"]): obj for obj in objects}
    mappings = []
    for asset in assets:
        candidates = [
            (_score(asset, obj), obj)
            for obj in unused.values()
        ]
        if not candidates:
            raise MappingError(f"no object remains for {asset.get('tag', asset.get('asset_id'))}")
        (score, method), obj = max(
            candidates,
            key=lambda item: (item[0][0], -int(item[1].get("points", 0)), str(item[1]["id"])),
        )
        object_id = str(obj["id"])
        unused.pop(object_id)
        mappings.append({
            "asset_id": asset.get("asset_id"),
            "tag": asset.get("tag"),
            "object_id": object_id,
            "class": asset.get("asset_class"),
            "state": asset.get("condition_state", "unknown"),
            "issue_code": asset.get("issue_code"),
            "method": method,
            "confidence": round(float(score), 3),
            "object_class_proposal": obj.get("class", obj.get("class_proposal", "unknown")),
        })

    target = pack.get("target", {})
    target_mapping = next(
        (mapping for mapping in mappings if mapping["asset_id"] == target.get("asset_id")),
        None,
    )
    if target_mapping is None:
        raise MappingError(f"target asset {target.get('asset_id')} was not mapped")
    payload = {
        "artifact": "mapped",
        "version": 1,
        "source": {
            "pack": str(pack.get("source", {}).get("file", "pack.json")),
            "objects": str(objects_payload.get("source", {}).get("scene", "objects.json")),
        },
        "counts": {
            "assets": len(assets),
            "mapped": len(mappings),
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
    print(f"target             {payload['target_tag']} ({payload['target_object_id']})")
    print(f"unmapped objects   {payload['counts']['unmapped_objects']}")
    print(f"wrote              {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
