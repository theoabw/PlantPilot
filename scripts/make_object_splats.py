"""Write one gaussian splat asset per reviewed anchor.

The object atlas needs objects that stay recognizable when they move. A Poisson
surface loses that; the anchor's own gaussians keep the captured appearance. This
stage writes the owned rows of the scene artifact as a core-property 3DGS PLY,
the same layout the viewer's full-room asset uses, so Spark can render each one
as an independent SplatMesh.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import numpy as np

from plantpilot import splat

CORE_PROPERTIES = (
    "x", "y", "z",
    "scale_0", "scale_1", "scale_2",
    "rot_0", "rot_1", "rot_2", "rot_3",
    "f_dc_0", "f_dc_1", "f_dc_2",
    "opacity",
)


def owned_mask(xyz: np.ndarray, centre: np.ndarray, axes: np.ndarray, extents: np.ndarray) -> np.ndarray:
    local = (xyz - centre) @ axes.T
    return np.all(np.abs(local) <= extents / 2.0 + 1e-9, axis=1)


def core_rows(scene: splat.Scene, rows: np.ndarray) -> np.ndarray:
    """The 14 core properties for the selected scene rows."""
    xyz = scene.xyz[rows]
    scale = np.log(np.maximum(scene.size[rows], 1e-12))
    rot = scene.rot[rows] if scene.rot is not None else np.tile(np.array([1.0, 0.0, 0.0, 0.0]), (rows.size, 1))
    rot = np.asarray(rot, dtype=np.float64)
    rot = rot / np.maximum(np.linalg.norm(rot, axis=1, keepdims=True), 1e-12)
    colour = scene.rgb[rows].astype(np.float64) / 255.0
    f_dc = (colour - 0.5) / 0.28209479177387814
    alpha = np.clip(scene.alpha[rows].astype(np.float64), 1e-6, 1.0 - 1e-6)
    opacity = np.log(alpha / (1.0 - alpha))
    return np.column_stack([xyz, scale, rot, f_dc, opacity]).astype(np.float32)


def write_ply(path: Path, rows: np.ndarray) -> None:
    header = (
        "ply\n"
        "format binary_little_endian 1.0\n"
        f"element vertex {rows.shape[0]}\n"
        + "".join(f"property float {name}\n" for name in CORE_PROPERTIES)
        + "end_header\n"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        handle.write(header.encode("ascii"))
        handle.write(rows.tobytes(order="C"))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scene", required=True)
    parser.add_argument("--anchors", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()

    scene = splat.load_scene(Path(args.scene))
    anchors = json.loads(Path(args.anchors).read_text())["anchors"]
    out = Path(args.out)
    capture = Path(args.scene).parent.name
    entries = []
    for anchor in anchors:
        centre = np.asarray(anchor["centre"], dtype=float)
        axes = np.asarray(anchor["axes"], dtype=float)
        extents = np.asarray(anchor["extents"], dtype=float)
        owned = owned_mask(scene.xyz, centre, axes, extents)
        # drop the capture's fog and nearly invisible gaussians so an object does
        # not carry a grey halo when it is lifted out of the room
        keep = owned & (scene.alpha > 0.05) & (scene.size.mean(axis=1) < 0.12)
        rows = np.flatnonzero(keep)
        if rows.size == 0:
            raise SystemExit(f"{anchor['id']}: no gaussians inside the anchor box")
        rows_core = core_rows(scene, rows)
        name = f"{anchor['id']}.ply"
        write_ply(out / capture / name, rows_core)
        centre_bbox = scene.xyz[rows].min(axis=0), scene.xyz[rows].max(axis=0)
        entries.append({
            "anchor_id": anchor["id"],
            "label": anchor["label"],
            "class": anchor.get("class"),
            "file": f"{capture}/{name}",
            "gaussians": int(rows.size),
            "world_bbox": {
                "min": np.round(centre_bbox[0], 4).tolist(),
                "max": np.round(centre_bbox[1], 4).tolist(),
            },
        })
        print(f"  {anchor['id']} {anchor['label']:<24} {rows.size:6d} gaussians")
    manifest = {
        "artifact": "object_splats",
        "version": 1,
        "capture": capture,
        "source": {"scene": args.scene, "anchors": args.anchors},
        "counts": {"objects": len(entries), "gaussians": int(sum(entry["gaussians"] for entry in entries))},
        "objects": entries,
    }
    manifest_path = out / capture / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    digest = hashlib.sha1(manifest_path.read_bytes()).hexdigest()[:12]
    print(f"wrote {len(entries)} object splats to {out / capture} (manifest {digest})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
