"""Bake derived information channels of a capture as viewer PLY variants.

The browser room toggles between the photo and four derived views of the same
room: height, normals, edges and semantics. Each variant is a complete 3DGS PLY
carrying the capture's own position, scale, rotation and opacity, so the
silhouette is identical to the photo asset in the viewer; only the DC colour
changes. The variants are produced from the scene artifact and the object and
asset documents, never from the delivered capture, and the source data is not
modified.

Conventions, chosen here once:

- Height is the position along the scene's own up axis from `Scene.height()`,
  normalised between the 2nd and 98th percentile, and drawn with a fixed
  warm-to-cool palette: warm amber low, cool blue high. Values outside the
  percentiles are clamped, so a stray point cannot flatten the scale.
- A gaussian's normal is the rotation applied to the ellipsoid axis with the
  smallest scale. The rotation encodes the covariance's columns, so the normal
  is the column of that index. RGB is 0.5 + 0.5 n, so opposite signs map to
  opposite colours, which is an accepted ambiguity: an ellipsoid has no
  outward face. An artifact without rotations falls back to the up axis.
- Edges compare each normal with the mean unit normal of its 0.08 m voxel:
  score = clip(1 - dot, 0, 1). A flat surface scores zero and a crease or pipe
  end scores high. Colour is near black at zero and white-hot at one, after
  raising the score to 0.7 to lift the weak creases.
- Semantics assign each gaussian to the smallest covering box from the asset
  document, and only unassigned gaussians fall back to the raw object boxes.
  Checks are point-in-oriented-box with a bounding-sphere prefilter, and the
  smallest volume wins because boxes are visited in ascending volume order.
  Each id gets a deterministic hue from its SHA-1, and unassigned gaussians are
  dark grey.

The output is byte-identical for the same inputs: no timestamp or machine state
reaches a PLY or the JSON documents. The four PLYs are written first and the
previews render last, all under `data/`, which is never committed.
"""

from __future__ import annotations

import argparse
import colorsys
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np

from plantpilot import splat, splat_render
from plantpilot.splat import CORE_PROPERTIES, Scene, load_scene

ROOT = Path(__file__).resolve().parents[1]

# The same fog cull the photo asset applies in `scripts/make_splat_asset.py`.
# A filter view that kept the metre-wide faint gaussians would wash out in the
# browser exactly as they do in the CPU renderer, so the variants are culled to
# the same rows as the photo PLY and the toggle changes colour only.
FOG_MEAN_SIZE_M = 0.12
FOG_ALPHA_MIN = 0.03

# The standard 3DGS DC convention. `scene.rgb` is the display colour, so the
# baked f_dc is the inverse of `0.5 + SH_DC * f_dc`.
SH_DC = splat.SH_DC

HEIGHT_PERCENTILES = (2.0, 98.0)
HEIGHT_PALETTE = np.array(
    [(255, 150, 64), (238, 208, 120), (120, 205, 185), (90, 140, 230)],
    dtype=np.float64,
)

EDGE_VOXEL_M = 0.08
EDGE_POWER = 0.7
EDGE_PALETTE = np.array([(8, 8, 12), (220, 70, 20), (255, 255, 240)], dtype=np.float64)

SEMANTICS_UNASSIGNED = (40, 40, 44)
SEMANTICS_SATURATION = 0.62
SEMANTICS_VALUE = 0.95

PREVIEW_WIDTH, PREVIEW_HEIGHT = 960, 600
PREVIEW_MAX_GAUSSIANS = 400_000

VARIANTS = ("height", "normals", "edges", "semantics")

VARIANT_DESCRIPTIONS = {
    "height": "height above the floor, 2nd to 98th percentile, warm amber to cool blue",
    "normals": "gaussian normal (thinnest ellipsoid axis) as 0.5 + 0.5 n, so sign flips invert the colour",
    "edges": "normal disagreement with the 0.08 m voxel mean, 1 - dot, near black to white-hot",
    "semantics": "smallest covering asset box, objects.json fallback, hue per id, dark grey unassigned",
}


# ---------------------------------------------------------------------------
# Palettes and the four channels


def ramp(values: np.ndarray, stops: np.ndarray) -> np.ndarray:
    """Map values in [0, 1] through evenly spaced colour stops, as uint8."""
    values = np.clip(np.asarray(values, dtype=np.float64), 0.0, 1.0)
    positions = np.linspace(0.0, 1.0, stops.shape[0])
    channels = [np.interp(values, positions, stops[:, channel]) for channel in range(3)]
    return np.rint(np.stack(channels, axis=-1)).astype(np.uint8)


def height_fraction(scene: Scene) -> np.ndarray:
    """Height along the scene up axis, clamped between the 2nd and 98th percentile."""
    height = scene.height()
    low, high = np.percentile(height, HEIGHT_PERCENTILES)
    if not np.isfinite(low) or not np.isfinite(high) or high <= low:
        return np.zeros(height.shape[0], dtype=np.float64)
    return np.clip((height - low) / (high - low), 0.0, 1.0)


def height_colours(scene: Scene) -> np.ndarray:
    """Warm-to-cool palette over the normalised height."""
    return ramp(height_fraction(scene), HEIGHT_PALETTE)


def gaussian_normals(scene: Scene) -> np.ndarray:
    """Unit normal per gaussian: the rotated thinnest ellipsoid axis.

    The rotation matrix's columns are the ellipsoid axes, so the normal is the
    column at the index of the smallest scale. An artifact without rotations
    uses the scene's up axis instead.
    """
    count = scene.xyz.shape[0]
    if scene.rot is None:
        up = np.zeros(3, dtype=np.float64)
        up[scene.up_index] = float(scene.up_sign)
        return np.tile(up, (count, 1))
    matrices = splat_render.quat_to_matrix(np.asarray(scene.rot, dtype=np.float64))
    thin = np.argmin(np.asarray(scene.size, dtype=np.float64), axis=1)
    normals = matrices[np.arange(count), :, thin]
    length = np.linalg.norm(normals, axis=1, keepdims=True)
    return normals / np.maximum(length, 1e-12)


def normal_colours(scene: Scene) -> np.ndarray:
    """Encode normals as 0.5 + 0.5 n, the conventional normal map."""
    encoded = 0.5 + 0.5 * gaussian_normals(scene)
    return np.rint(np.clip(encoded, 0.0, 1.0) * 255.0).astype(np.uint8)


def voxel_mean_normals(xyz: np.ndarray, normals: np.ndarray, voxel: float = EDGE_VOXEL_M) -> np.ndarray:
    """Mean unit normal of each gaussian's voxel, broadcast back to gaussians."""
    xyz = np.asarray(xyz, dtype=np.float64)
    normals = np.asarray(normals, dtype=np.float64)
    indices = np.floor((xyz - xyz.min(axis=0)) / voxel).astype(np.int64)
    dims = indices.max(axis=0) + 1
    keys = (indices[:, 0] * dims[1] + indices[:, 1]) * dims[2] + indices[:, 2]
    _, inverse = np.unique(keys, return_inverse=True)
    inverse = inverse.reshape(-1).astype(np.int64)
    sums = np.stack(
        [np.bincount(inverse, weights=normals[:, axis], minlength=int(inverse.max()) + 1) for axis in range(3)],
        axis=1,
    )
    means = sums[inverse]
    length = np.linalg.norm(means, axis=1, keepdims=True)
    return means / np.maximum(length, 1e-12)


def edge_scores(xyz: np.ndarray, normals: np.ndarray, voxel: float = EDGE_VOXEL_M) -> np.ndarray:
    """1 - dot of each normal with its voxel mean, clipped to [0, 1]."""
    means = voxel_mean_normals(xyz, normals, voxel=voxel)
    return np.clip(1.0 - np.einsum("ij,ij->i", normals, means), 0.0, 1.0)


def edge_colours(scores: np.ndarray) -> np.ndarray:
    """Near black at zero, white-hot at one, after the 0.7 lift."""
    return ramp(np.clip(np.asarray(scores, dtype=np.float64), 0.0, 1.0) ** EDGE_POWER, EDGE_PALETTE)


def id_colour(identifier: str) -> tuple[int, int, int]:
    """A deterministic, readable hue for an asset or object id."""
    digest = hashlib.sha1(str(identifier).encode("utf-8")).hexdigest()
    hue = int(digest[:8], 16) / 0xFFFFFFFF
    red, green, blue = colorsys.hsv_to_rgb(hue, SEMANTICS_SATURATION, SEMANTICS_VALUE)
    return int(round(red * 255)), int(round(green * 255)), int(round(blue * 255))


def _box_volume(record: dict) -> float:
    return float(np.prod(np.asarray(record["extents"], dtype=np.float64)))


def _box_owner(record: dict, source: str) -> dict:
    """The legend entry for one candidate box."""
    label = record.get("label") or record.get("class") or record.get("id")
    entry = {
        "source": source,
        "id": str(record["id"]),
        "label": str(label),
        "class": str(record.get("class", "unknown")),
        "confidence": float(record.get("confidence", record.get("class_confidence", 0.0))),
        "colour": list(id_colour(record["id"])),
        "gaussians": 0,
    }
    if "verified" in record:
        entry["verified"] = bool(record["verified"])
    return entry


def semantic_assignment(
    xyz: np.ndarray,
    assets: list[dict],
    objects: list[dict],
) -> tuple[np.ndarray, list[dict]]:
    """Assign each gaussian to the smallest covering asset box, then object box.

    Candidates are visited in ascending volume, so the first box to claim a
    gaussian is the smallest covering one. Assets are offered before objects, so
    an asset box always wins an overlap with a raw object box. Returns the entry
    index per gaussian (-1 unassigned) and the legend entries that own at least
    one gaussian, in deterministic order.
    """
    xyz = np.asarray(xyz, dtype=np.float64)
    count = xyz.shape[0]
    labels = np.full(count, -1, dtype=np.int32)
    entries: list[dict] = []

    def offer(records: list[dict], source: str) -> None:
        ordered = sorted(records, key=lambda record: (_box_volume(record), str(record["id"])))
        for record in ordered:
            centre = np.asarray(record["centre"], dtype=np.float64)
            axes = np.asarray(record["axes"], dtype=np.float64).reshape(3, 3)
            extents = np.asarray(record["extents"], dtype=np.float64)
            entry_index = len(entries)
            entries.append(_box_owner(record, source))
            radius = float(np.linalg.norm(extents / 2.0))
            offset = xyz - centre
            near = np.einsum("ij,ij->i", offset, offset) <= radius * radius
            candidates = np.flatnonzero(near & (labels < 0))
            if candidates.size == 0:
                continue
            local = offset[candidates] @ axes.T
            inside = np.abs(local) <= extents / 2.0 + 1e-9
            chosen = candidates[inside.all(axis=1)]
            if chosen.size == 0:
                continue
            labels[chosen] = entry_index
            entries[entry_index]["gaussians"] = int(chosen.size)

    offer(assets, "asset")
    offer(objects, "object")
    used = [
        entry for entry in entries if entry["gaussians"] > 0
    ]
    remap = {old: new for new, old in enumerate(
        [index for index, entry in enumerate(entries) if entry["gaussians"] > 0]
    )}
    if len(remap) != len(entries):
        for index in np.flatnonzero(labels >= 0):
            labels[index] = remap[int(labels[index])]
    return labels, used


def semantic_colours(labels: np.ndarray, entries: list[dict]) -> np.ndarray:
    """Palette colour per gaussian, dark grey where unassigned."""
    colours = np.tile(np.array(SEMANTICS_UNASSIGNED, dtype=np.uint8), (labels.shape[0], 1))
    for index, entry in enumerate(entries):
        colours[labels == index] = np.asarray(entry["colour"], dtype=np.uint8)
    return colours


# ---------------------------------------------------------------------------
# The PLY writer and the bake


def write_ply(rows: np.ndarray, out: Path, comment: str) -> dict:
    """Write core-property rows as a binary little endian 3DGS PLY."""
    out.parent.mkdir(parents=True, exist_ok=True)
    header = "\n".join([
        "ply",
        "format binary_little_endian 1.0",
        f"comment {comment}",
        f"element vertex {rows.shape[0]}",
        *[f"property float {name}" for name in CORE_PROPERTIES],
        "end_header",
        "",
    ]).encode("ascii")
    with out.open("wb") as handle:
        handle.write(header)
        handle.write(np.ascontiguousarray(rows, dtype=np.float32).tobytes())
    return {"file": out.name, "vertices": int(rows.shape[0]), "bytes": int(out.stat().st_size)}


def geometry_rows(scene: Scene) -> np.ndarray:
    """The 14 core columns with the scene's own geometry and an empty colour.

    Scale and opacity are stored in the artifact as standard deviation and
    sigmoid opacity, so they are inverted back to the 3DGS log scale and logit
    that the viewer expects. The inversion is exact wherever the ingest clipped,
    which is why the silhouettes match the photo asset. The artifact stores a
    normalised quaternion, so a source quaternion that was not unit length is
    written normalised; the viewer normalises before it builds a rotation, which
    leaves the drawn silhouette unchanged.
    """
    count = scene.xyz.shape[0]
    rows = np.zeros((count, len(CORE_PROPERTIES)), dtype=np.float32)
    rows[:, 0:3] = np.asarray(scene.xyz, dtype=np.float32)
    rows[:, 3:6] = np.log(np.maximum(np.asarray(scene.size, dtype=np.float64), 1e-30)).astype(np.float32)
    if scene.rot is None:
        rows[:, 6:10] = (1.0, 0.0, 0.0, 0.0)
    else:
        rows[:, 6:10] = np.asarray(scene.rot, dtype=np.float32)
    alpha = np.clip(np.asarray(scene.alpha, dtype=np.float64), 1e-6, 1.0 - 1e-6)
    rows[:, 13] = np.log(alpha / (1.0 - alpha)).astype(np.float32)
    return rows


def colour_rows(geometry: np.ndarray, colours: np.ndarray) -> np.ndarray:
    """The geometry columns with a display colour written as DC terms."""
    rows = geometry.copy()
    display = np.clip(np.asarray(colours, dtype=np.float64) / 255.0, 0.0, 1.0)
    rows[:, 10:13] = ((display - 0.5) / SH_DC).astype(np.float32)
    return rows


def subset_scene(scene: Scene, keep: np.ndarray) -> Scene:
    """The scene restricted to the kept rows, same metadata and up axis."""
    return Scene(
        xyz=np.asarray(scene.xyz, dtype=np.float64)[keep],
        rgb=np.asarray(scene.rgb)[keep],
        size=np.asarray(scene.size)[keep],
        alpha=np.asarray(scene.alpha)[keep],
        meta=scene.meta,
        rot=None if scene.rot is None else np.asarray(scene.rot)[keep],
    )


def fog_keep(scene: Scene) -> np.ndarray:
    """Rows the photo viewer asset keeps, so the toggle changes colour only."""
    mean_size = np.asarray(scene.size, dtype=np.float64).mean(axis=1)
    alpha = np.asarray(scene.alpha, dtype=np.float64)
    return (mean_size < FOG_MEAN_SIZE_M) & (alpha > FOG_ALPHA_MIN)


def preview_paths(scene: Scene, colours: dict[str, np.ndarray], camera: dict, out: Path) -> dict:
    """Render one PNG per variant from the camera in the objects artifact."""
    picked = splat.decimate(int(scene.xyz.shape[0]), PREVIEW_MAX_GAUSSIANS, seed=0)
    base = splat_render.from_scene(scene)
    view = base.subset(picked)
    eye, target, up = (np.asarray(camera[key], dtype=np.float64) for key in ("eye", "target", "up"))
    splat_camera = splat_render.Camera.look_at(
        eye, target, up, PREVIEW_WIDTH, PREVIEW_HEIGHT,
    )
    paths = {}
    for name in VARIANTS:
        gaussians = splat_render.Gaussians(
            xyz=view.xyz,
            scale=view.scale,
            rot=view.rot,
            rgb=colours[name][picked].astype(np.float64) / 255.0,
            alpha=view.alpha,
        )
        path = out / f"preview_{name}.png"
        splat_render.render(gaussians, splat_camera).save(path)
        paths[name] = str(_display_path(path))
    return paths


def _display_path(path: Path) -> str:
    resolved = Path(path).resolve()
    try:
        return str(resolved.relative_to(ROOT))
    except ValueError:
        return str(resolved)


def bake(
    scene: Scene,
    objects: dict,
    assets: dict,
    *,
    scene_path: Path = Path("data/equipment/scene.npz"),
    objects_path: Path = Path("data/equipment/objects.json"),
    assets_path: Path = Path("data/equipment/assets.json"),
    out: Path | None = None,
    previews: bool = True,
    keep_fog: bool = False,
) -> dict:
    """Write the four variant PLYs, the legend, the index and the previews."""
    started = time.perf_counter()
    capture = str(scene.meta.get("source", {}).get("file", "capture"))
    keep = np.ones(scene.xyz.shape[0], dtype=bool) if keep_fog else fog_keep(scene)
    view = subset_scene(scene, keep)
    dropped = int(scene.xyz.shape[0] - view.xyz.shape[0])

    height = height_colours(view)
    normals = normal_colours(view)
    edges = edge_colours(edge_scores(view.xyz, gaussian_normals(view)))
    assignment, legend_entries = semantic_assignment(
        view.xyz,
        list(assets.get("assets", [])),
        list(objects.get("objects", [])),
    )
    semantics = semantic_colours(assignment, legend_entries)
    colours = {"height": height, "normals": normals, "edges": edges, "semantics": semantics}

    out = Path(out) if out is not None else ROOT / "data" / "viewer" / "filters" / Path(scene_path).resolve().parent.name
    out.mkdir(parents=True, exist_ok=True)
    geometry = geometry_rows(view)
    files = {}
    for name in VARIANTS:
        files[name] = write_ply(
            colour_rows(geometry, colours[name]),
            out / f"{name}.ply",
            f"filter variant {name} for {capture}, written by scripts/make_filter_assets.py",
        )

    assigned = int((assignment >= 0).sum())
    unassigned = int(view.xyz.shape[0] - assigned)
    legend = {
        "artifact": "semantics-legend",
        "version": 1,
        "source": {
            "scene": _display_path(Path(scene_path)),
            "assets": _display_path(Path(assets_path)),
            "objects": _display_path(Path(objects_path)),
            "capture": capture,
            "gaussians": int(view.xyz.shape[0]),
            "source_gaussians": int(scene.xyz.shape[0]),
            "fog_culled": dropped,
        },
        "unassigned": {"colour": list(SEMANTICS_UNASSIGNED), "gaussians": unassigned},
        "counts": {
            "entries": len(legend_entries),
            "assigned": assigned,
            "unassigned": unassigned,
            "asset_owned": int(sum(entry["gaussians"] for entry in legend_entries if entry["source"] == "asset")),
            "object_owned": int(sum(entry["gaussians"] for entry in legend_entries if entry["source"] == "object")),
        },
        "entries": legend_entries,
    }
    legend_path = out / "semantics_legend.json"
    legend_path.write_text(json.dumps(legend, indent=1) + "\n")

    camera = objects.get("camera") or {}
    if previews and not camera:
        raise SystemExit(f"{objects_path}: no camera in the objects artifact, cannot render previews")
    previews_path = preview_paths(view, colours, camera, out) if previews else {}

    filters = {
        "artifact": "filter-assets",
        "version": 1,
        "source": {
            "scene": _display_path(Path(scene_path)),
            "objects": _display_path(Path(objects_path)),
            "assets": _display_path(Path(assets_path)),
            "capture": capture,
            "gaussians": int(view.xyz.shape[0]),
            "source_gaussians": int(scene.xyz.shape[0]),
            "fog_culled": dropped,
        },
        "geometry": {
            "properties": list(CORE_PROPERTIES),
            "identity": "xyz, scale, rotation, opacity and vertex count are identical in all four PLYs; only f_dc differs",
            "fog_cull": {"mean_size_m": FOG_MEAN_SIZE_M, "alpha_min": FOG_ALPHA_MIN},
        },
        "filters": {"applied": list(VARIANTS)},
        "variants": {
            name: {
                **files[name],
                "preview": previews_path.get(name),
                "description": VARIANT_DESCRIPTIONS[name],
            }
            for name in VARIANTS
        },
    }
    filters_path = out / "filters.json"
    filters_path.write_text(json.dumps(filters, indent=1) + "\n")
    return {
        "out": _display_path(out),
        "files": files,
        "previews": previews_path,
        "legend": _display_path(legend_path),
        "filters": _display_path(filters_path),
        "semantics_counts": legend["counts"],
        "bake_seconds": round(time.perf_counter() - started, 2),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python scripts/make_filter_assets.py",
        description="Bake height, normals, edges and semantics viewer PLY variants from a scene artifact.",
    )
    parser.add_argument("--scene", default=Path("data/equipment/scene.npz"), type=Path)
    parser.add_argument("--objects", default=Path("data/equipment/objects.json"), type=Path)
    parser.add_argument("--assets", default=Path("data/equipment/assets.json"), type=Path)
    parser.add_argument(
        "--out", default=None, type=Path,
        help="output directory; defaults to data/viewer/filters/<scene directory name>",
    )
    parser.add_argument("--keep-fog", action="store_true", help="keep the fog gaussians the photo asset culls")
    parser.add_argument("--no-previews", action="store_true", help="skip the four preview PNGs")
    args = parser.parse_args(argv)

    try:
        scene = load_scene(args.scene)
        objects = json.loads(Path(args.objects).read_text())
        assets = json.loads(Path(args.assets).read_text())
        summary = bake(
            scene, objects, assets,
            scene_path=args.scene, objects_path=args.objects, assets_path=args.assets,
            out=args.out, previews=not args.no_previews, keep_fog=args.keep_fog,
        )
    except Exception as exc:  # noqa: BLE001 - the message is the point of the failure
        print(f"filter assets failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
