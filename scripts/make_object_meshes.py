#!/usr/bin/env python3
"""Bake one triangle mesh per reviewed anchor from the gaussian scene.

The reviewed anchor artifact owns a set of gaussians per object (the smallest
covering reviewed box wins when a gaussian sits in several boxes). This stage
turns each owned set into a coloured, closed-ish surface: the thinnest ellipsoid
axis gives an initial surface normal, the cloud is downsampled and Poisson
reconstructed, the low-density fringe is trimmed, the result is cropped to the
anchor box plus a small margin, decimated and coloured from the nearest gaussian.

Open3D is optional and imported only when a bake actually runs, so the pure
helpers below stay importable in an environment without it. The script writes
one binary PLY per anchor and one deterministic manifest under
`<out>/<capture>/`.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "app" / "server" / "src"))

from plantpilot import splat  # noqa: E402
from plantpilot.splat_render import quat_to_matrix  # noqa: E402

ARTIFACT = "object_meshes"
VERSION = 1

ALPHA_MIN = 0.05
MEAN_SIZE_MAX_M = 0.12
VOXEL_M = 0.025
POISSON_DEPTH = 8
# Poisson runs on one thread so the reconstruction, and therefore the mesh, is
# reproducible run to run. The default thread count changes the density field
# at the last bit, which moves the density trim boundary and the triangle count.
POISSON_THREADS = 1
DENSITY_TRIM_FRACTION = 0.08
CROP_MARGIN_M = 0.02
MAX_TRIANGLES = 20_000
MIN_USABLE_GAUSSIANS = 200
NORMAL_KNN = 30


class BakeError(RuntimeError):
    """One anchor cannot be baked into a mesh."""


def _rounded(values, digits: int = 4) -> list[float]:
    return [round(float(value), digits) for value in np.asarray(values, dtype=np.float64).reshape(-1)]


def points_in_box(xyz: np.ndarray, centre, axes, extents, margin: float = 0.0) -> np.ndarray:
    """Boolean mask for gaussians inside an oriented box, optionally expanded by a margin."""
    local = (np.asarray(xyz, dtype=np.float64) - np.asarray(centre, dtype=np.float64)) @ np.asarray(
        axes, dtype=np.float64
    ).T
    half = np.asarray(extents, dtype=np.float64) / 2.0 + margin
    return np.all(np.abs(local) <= half + 1e-9, axis=1)


def owned_anchor_indices(xyz: np.ndarray, anchors: list[dict]) -> np.ndarray:
    """Assign every gaussian to the smallest covering anchor box, or -1.

    Volume is the tie-breaker a reviewer would accept: a gaussian shared by a
    large and a small reviewed box belongs to the small one. Equal volumes keep
    the anchor that appears first in the artifact, so the join stays
    deterministic.
    """
    xyz = np.asarray(xyz, dtype=np.float64)
    labels = np.full(xyz.shape[0], -1, dtype=np.int64)
    best_volume = np.full(xyz.shape[0], np.inf, dtype=np.float64)
    for index, anchor in enumerate(anchors):
        volume = float(np.prod(np.asarray(anchor["extents"], dtype=np.float64)))
        inside = points_in_box(xyz, anchor["centre"], anchor["axes"], anchor["extents"])
        take = inside & (volume < best_volume)
        labels[take] = index
        best_volume[take] = volume
    return labels


def usable_gaussian_mask(
    alpha: np.ndarray,
    size: np.ndarray,
    *,
    alpha_min: float = ALPHA_MIN,
    mean_size_max_m: float = MEAN_SIZE_MAX_M,
) -> np.ndarray:
    """Keep gaussians with alpha above the floor and a mean size below the cap.

    Both comparisons are strict: an alpha of exactly 0.05 and a mean size of
    exactly 0.12 m are dropped, which is what "drop alpha <= 0.05" and "drop mean
    size >= 0.12 m" ask for.
    """
    alpha = np.asarray(alpha, dtype=np.float64)
    size = np.asarray(size, dtype=np.float64)
    mean_size = size if size.ndim == 1 else size.mean(axis=1)
    if alpha.shape != mean_size.shape:
        raise ValueError("alpha and size describe different gaussians")
    return (alpha > alpha_min) & (mean_size < mean_size_max_m)


def gaussian_normals(rot, size: np.ndarray, points: np.ndarray, centroid=None) -> np.ndarray:
    """Normal from the thinnest ellipsoid axis, flipped to point away from the centroid."""
    points = np.asarray(points, dtype=np.float64)
    size = np.asarray(size, dtype=np.float64)
    rotations = np.asarray(rot, dtype=np.float64)
    if rotations.ndim == 2:
        rotations = quat_to_matrix(rotations)
    if rotations.shape != (points.shape[0], 3, 3):
        raise ValueError("rot must be quaternions or a matching (n, 3, 3) matrix stack")
    thinnest = np.argmin(size, axis=1)
    normals = rotations[np.arange(points.shape[0]), :, thinnest]
    norm = np.linalg.norm(normals, axis=1, keepdims=True)
    normals = normals / np.maximum(norm, 1e-12)
    origin = points.mean(axis=0) if centroid is None else np.asarray(centroid, dtype=np.float64)
    inward = np.einsum("ij,ij->i", normals, points - origin) < 0.0
    normals = normals.copy()
    normals[inward] *= -1.0
    return normals


def crop_mask(
    vertices: np.ndarray,
    centre,
    axes,
    extents,
    margin: float = CROP_MARGIN_M,
) -> np.ndarray:
    """Vertices inside the anchor box expanded by the crop margin on every side."""
    return points_in_box(vertices, centre, axes, extents, margin=margin)


def capture_name(scene_path) -> str:
    """The capture directory name, taken from the scene artifact's parent folder."""
    path = Path(scene_path)
    parent = path.resolve().parent.name
    return parent or path.stem


def safe_file_stem(anchor_id) -> str:
    stem = re.sub(r"[^A-Za-z0-9._-]+", "_", str(anchor_id)).strip("._-")
    return stem or "anchor"


def world_bbox(mesh) -> dict:
    box = mesh.get_axis_aligned_bounding_box()
    minimum = np.asarray(box.min_bound, dtype=np.float64)
    maximum = np.asarray(box.max_bound, dtype=np.float64)
    return {
        "min": _rounded(minimum),
        "max": _rounded(maximum),
        "extent": _rounded(maximum - minimum),
    }


def object_record(
    anchor: dict,
    file_name: str,
    world_bounding_box: dict,
    triangles: int,
    vertices: int,
    owned_gaussians: int,
    watertight: bool,
    *,
    usable_gaussians: int | None = None,
    downsampled_points: int | None = None,
) -> dict:
    """One anchor's manifest entry, with its anchor box copied verbatim."""
    record = {
        "anchor_id": str(anchor.get("id")),
        "label": anchor.get("label"),
        "class": anchor.get("class"),
        "file": file_name,
        "world_bbox": world_bounding_box,
        "triangles": int(triangles),
        "vertices": int(vertices),
        "owned_gaussians": int(owned_gaussians),
        "anchor_box": {
            "centre": _rounded(anchor["centre"]),
            "axes": [_rounded(row) for row in anchor["axes"]],
            "extents": _rounded(anchor["extents"]),
        },
        "watertight": bool(watertight),
    }
    if usable_gaussians is not None:
        record["usable_gaussians"] = int(usable_gaussians)
    if downsampled_points is not None:
        record["downsampled_points"] = int(downsampled_points)
    return record


def bake_parameters() -> dict:
    return {
        "alpha_min": ALPHA_MIN,
        "mean_size_max_m": MEAN_SIZE_MAX_M,
        "voxel_m": VOXEL_M,
        "poisson_depth": POISSON_DEPTH,
        "poisson_threads": POISSON_THREADS,
        "density_trim_fraction": DENSITY_TRIM_FRACTION,
        "crop_margin_m": CROP_MARGIN_M,
        "max_triangles": MAX_TRIANGLES,
    }


def manifest_document(
    capture: str,
    scene_path: str,
    anchors_path: str,
    objects: list[dict],
    parameters: dict | None = None,
) -> dict:
    """The deterministic manifest document for one capture's baked meshes."""
    counts = {
        "objects": len(objects),
        "triangles": int(sum(item["triangles"] for item in objects)),
        "vertices": int(sum(item["vertices"] for item in objects)),
        "owned_gaussians": int(sum(item["owned_gaussians"] for item in objects)),
        "watertight": int(sum(1 for item in objects if item.get("watertight"))),
    }
    return {
        "artifact": ARTIFACT,
        "version": VERSION,
        "capture": capture,
        "source": {"scene": scene_path, "anchors": anchors_path},
        "parameters": parameters if parameters is not None else bake_parameters(),
        "counts": counts,
        "objects": objects,
    }


def _import_open3d():
    """Import Open3D lazily so tests and dry environments do not need it."""
    try:
        import open3d as o3d
    except Exception as exc:  # noqa: BLE001 - the install hint is the point of the message
        raise SystemExit(
            "open3d is required to bake object meshes; install it with: uv pip install open3d "
            f"(import failed: {exc})"
        ) from exc
    return o3d


def _write_mesh(o3d, mesh, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    written = o3d.io.write_triangle_mesh(
        str(path),
        mesh,
        write_ascii=False,
        write_vertex_normals=True,
        write_vertex_colors=True,
    )
    if not written:
        raise BakeError(f"Open3D could not write {path}")


def bake_anchor(
    o3d,
    scene,
    anchor: dict,
    mask: np.ndarray,
    *,
    owned_gaussians: int,
    voxel: float = VOXEL_M,
    depth: int = POISSON_DEPTH,
    density_trim: float = DENSITY_TRIM_FRACTION,
    margin: float = CROP_MARGIN_M,
    max_triangles: int = MAX_TRIANGLES,
):
    """Rebuild one anchor's surface and return (mesh, manifest record)."""
    points = np.asarray(scene.xyz[mask], dtype=np.float64)
    if points.shape[0] < MIN_USABLE_GAUSSIANS:
        raise BakeError(
            f"{anchor.get('id')}: only {points.shape[0]} usable gaussians after the alpha and size filters"
        )
    colours = np.asarray(scene.rgb[mask], dtype=np.float64) / 255.0
    sizes = np.asarray(scene.size[mask], dtype=np.float64)
    rotations = np.asarray(scene.rot[mask], dtype=np.float64)
    normals = gaussian_normals(quat_to_matrix(rotations), sizes, points)

    cloud = o3d.geometry.PointCloud()
    cloud.points = o3d.utility.Vector3dVector(points)
    cloud.normals = o3d.utility.Vector3dVector(normals)
    cloud.colors = o3d.utility.Vector3dVector(colours)

    down = cloud.voxel_down_sample(voxel)
    down.estimate_normals(o3d.geometry.KDTreeSearchParamHybrid(radius=voxel * 2.0, max_nn=NORMAL_KNN))
    down.orient_normals_consistent_tangent_plane(10)

    mesh, density = o3d.geometry.TriangleMesh.create_from_point_cloud_poisson(
        down, depth=depth, n_threads=POISSON_THREADS
    )
    density = np.asarray(density, dtype=np.float64).reshape(-1)
    if density.size:
        cut = float(np.quantile(density, density_trim))
        mesh.remove_vertices_by_mask(density < cut)

    vertices = np.asarray(mesh.vertices, dtype=np.float64)
    if vertices.size:
        keep = crop_mask(vertices, anchor["centre"], anchor["axes"], anchor["extents"], margin=margin)
        mesh.remove_vertices_by_mask(~keep)
    mesh.remove_degenerate_triangles()
    mesh.remove_unreferenced_vertices()

    if len(mesh.triangles) > max_triangles:
        mesh = mesh.simplify_quadric_decimation(max_triangles)

    if len(mesh.vertices) == 0 or len(mesh.triangles) == 0:
        raise BakeError(f"{anchor.get('id')}: Poisson reconstruction produced an empty mesh")

    tree = o3d.geometry.KDTreeFlann(cloud)
    vertex_colours = np.zeros((len(mesh.vertices), 3), dtype=np.float64)
    source_colours = np.asarray(cloud.colors, dtype=np.float64)
    for index, vertex in enumerate(np.asarray(mesh.vertices, dtype=np.float64)):
        _, nearest, _ = tree.search_knn_vector_3d(vertex, 1)
        vertex_colours[index] = source_colours[nearest[0]]
    mesh.vertex_colors = o3d.utility.Vector3dVector(vertex_colours)
    mesh.compute_vertex_normals()

    file_name = f"{safe_file_stem(anchor.get('id'))}.ply"
    record = object_record(
        anchor,
        file_name,
        world_bbox(mesh),
        len(mesh.triangles),
        len(mesh.vertices),
        owned_gaussians,
        bool(mesh.is_watertight()),
        usable_gaussians=int(points.shape[0]),
        downsampled_points=int(len(down.points)),
    )
    return mesh, record


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Bake one coloured mesh per reviewed scene anchor.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--scene", required=True, type=Path, help="scene.npz from the splat stage")
    parser.add_argument("--anchors", required=True, type=Path, help="reviewed anchors.json")
    parser.add_argument("--out", required=True, type=Path, help="mesh output root")
    args = parser.parse_args(argv)

    o3d = _import_open3d()
    scene = splat.load_scene(args.scene)
    if scene.rot is None:
        raise SystemExit(f"{args.scene} has no gaussian rotations; re-run the scene stage")
    anchor_payload = json.loads(args.anchors.read_text())
    anchors = list(anchor_payload.get("anchors") or [])
    if not anchors:
        raise SystemExit(f"{args.anchors} has no reviewed anchors")

    capture = capture_name(args.scene)
    out_root = args.out / capture
    labels = owned_anchor_indices(scene.xyz, anchors)

    print(f"== object meshes: {capture} ==")
    print(f"scene    {args.scene} ({scene.xyz.shape[0]:,} gaussians)")
    print(f"anchors  {args.anchors} ({len(anchors)} reviewed anchors)")
    print(f"out      {out_root}")

    started = time.perf_counter()
    objects = []
    for index, anchor in enumerate(anchors):
        owned = labels == index
        usable = owned & usable_gaussian_mask(scene.alpha, scene.size)
        owned_count = int(owned.sum())
        usable_count = int(usable.sum())
        anchor_started = time.perf_counter()
        try:
            mesh, record = bake_anchor(o3d, scene, anchor, usable, owned_gaussians=owned_count)
        except BakeError as exc:
            raise SystemExit(f"bake failed: {exc}") from exc
        mesh_path = out_root / record["file"]
        _write_mesh(o3d, mesh, mesh_path)
        elapsed = time.perf_counter() - anchor_started
        objects.append(record)
        print(
            f"  {record['anchor_id']:<14} {str(record['label']):<30} "
            f"owned {owned_count:6d} usable {usable_count:6d} down {record['downsampled_points']:6d} "
            f"verts {record['vertices']:6d} tris {record['triangles']:6d} "
            f"watertight {str(record['watertight']):<5} {elapsed:6.2f} s"
        )

    manifest = manifest_document(
        capture,
        str(args.scene),
        str(args.anchors),
        objects,
    )
    manifest_path = out_root / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    elapsed = time.perf_counter() - started
    print(f"manifest {manifest_path} ({manifest['counts']['objects']} objects, "
          f"{manifest['counts']['triangles']:,} triangles)")
    print(f"total bake time {elapsed:.2f} s")
    return 0


if __name__ == "__main__":
    import os

    try:
        exit_code = main()
    except SystemExit as exc:
        if isinstance(exc.code, str) and exc.code:
            print(exc.code, file=sys.stderr)
        exit_code = exc.code if isinstance(exc.code, int) else 1
    sys.stdout.flush()
    sys.stderr.flush()
    # Open3D 0.20 occasionally faults in its own static teardown after a
    # successful bake on this platform, turning a finished run into exit 139.
    # All files are written and closed by this point, so leave the process
    # rather than letting interpreter shutdown race the Open3D threads.
    os._exit(exit_code)
