"""Photo to point cloud, with an ArUco marker for metric scale.

The pipeline is deliberately open source and local: Depth Anything V2 small in
ONNX for monocular depth, OpenCV's guided filter to sharpen the depth against
the image, OpenCV ArUco for camera pose and the metre scale, numpy for the
back-projection, a RANSAC plane for the floor.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
import onnxruntime as ort

DEFAULT_FOV_DEG = 60.0
MODEL = "data/models/depth_anything_v2_small_q.onnx"
LONG_SIDE = 518


@dataclass
class Scan:
    points: np.ndarray        # (N, 3) metres, camera frame, x right y down z forward
    colors: np.ndarray        # (N, 3) uint8
    scale: float              # metres * relative depth
    meta: dict


def _session(model: Path) -> ort.InferenceSession:
    return ort.InferenceSession(str(model), providers=["CPUExecutionProvider"])


def depth_map(img_bgr: np.ndarray, model: Path) -> tuple[np.ndarray, float]:
    """Relative inverse depth at the model resolution, plus the seconds it took."""
    import time

    h, w = img_bgr.shape[:2]
    scale = LONG_SIDE / max(h, w)
    nh = max(14, int(round(h * scale / 14)) * 14)
    nw = max(14, int(round(w * scale / 14)) * 14)
    small = cv2.resize(img_bgr, (nw, nh))
    rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB).astype(np.float32) / 255.0
    mean = np.array([0.485, 0.456, 0.406], dtype=np.float32)
    std = np.array([0.229, 0.224, 0.225], dtype=np.float32)
    x = ((rgb - mean) / std).transpose(2, 0, 1)[None]
    t0 = time.perf_counter()
    out = _session(model).run(None, {"pixel_values": x})[0][0]
    return out.astype(np.float32), time.perf_counter() - t0


def refine_depth(rel_small: np.ndarray, img_bgr: np.ndarray, radius: int = 12, eps: float = 1e-4) -> np.ndarray:
    """Edge-aware upsampling: the guided filter keeps depth edges on image edges."""
    h, w = img_bgr.shape[:2]
    guide = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    rel = cv2.resize(rel_small, (w, h), interpolation=cv2.INTER_LINEAR)
    guide_f = guide.astype(np.float32) / 255.0
    rel_f = rel.astype(np.float32)
    try:
        return cv2.ximgproc.guidedFilter(guide_f, rel_f, radius, eps)
    except cv2.error:
        return rel_f


def intrinsics(width: int, height: int, fov_deg: float = DEFAULT_FOV_DEG) -> tuple[float, float, float]:
    f = 0.5 * width / np.tan(np.deg2rad(fov_deg) / 2.0)
    return f, width / 2.0, height / 2.0


Z_MIN = 0.10
Z_MAX = 20.0


def backproject(rel: np.ndarray, img_bgr: np.ndarray, scale: float) -> tuple[np.ndarray, np.ndarray]:
    """Relative inverse depth to a bounded cloud. Sky and the far field are dropped,
    because a monocular model puts near zero signal there and z would run to kilometres."""
    h, w = rel.shape
    f, cx, cy = intrinsics(w, h)
    depth = np.maximum(rel, 1e-6)
    z = scale / depth
    keep = (z > Z_MIN) & (z < Z_MAX)
    ys, xs = np.mgrid[0:h, 0:w]
    x = (xs - cx) * z / f
    y = (ys - cy) * z / f
    points = np.stack([x, y, z], axis=-1).reshape(-1, 3)[keep.reshape(-1)]
    colors = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB).reshape(-1, 3)[keep.reshape(-1)]
    return points.astype(np.float32), colors


def aruco_scale(img_bgr: np.ndarray, rel: np.ndarray, marker_size_m: float = 0.10) -> tuple[float | None, dict]:
    """Metre scale from a printed ArUco marker: z = f * size_m / size_px, matched to the relative depth."""
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    try:
        dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
        detector = cv2.aruco.ArucoDetector(dictionary, cv2.aruco.DetectorParameters())
        corners, ids, _ = detector.detectMarkers(gray)
    except Exception:
        return None, {}
    if not corners:
        return None, {}
    c = corners[0].reshape(4, 2)
    side_px = float(np.mean([np.linalg.norm(c[0] - c[1]), np.linalg.norm(c[1] - c[2])]))
    f, _, _ = intrinsics(img_bgr.shape[1], img_bgr.shape[0])
    z_marker = f * marker_size_m / max(side_px, 1e-6)
    h, w = rel.shape
    cu = int(np.clip(c[:, 0].mean(), 0, w - 1))
    cv = int(np.clip(c[:, 1].mean(), 0, h - 1))
    rel_at_marker = float(rel[cu and cv:cv + 1, cu:cu + 1][0, 0])
    if rel_at_marker <= 0:
        return None, {}
    return float(z_marker * rel_at_marker), {
        "marker_id": int(ids[0][0]),
        "side_px": round(side_px, 1),
        "marker_depth_m": round(z_marker, 3),
    }


def voxel_downsample(points: np.ndarray, colors: np.ndarray, voxel: float = 0.02) -> tuple[np.ndarray, np.ndarray]:
    if len(points) == 0:
        return points, colors
    keys = np.floor(points / voxel).astype(np.int64)
    _, index = np.unique(keys, axis=0, return_index=True)
    return points[index], colors[index]


def floor_plane(points: np.ndarray, dist: float = 0.02, iters: int = 300, seed: int = 7) -> dict:
    """RANSAC plane, oriented so the normal points up in the camera frame (negative y)."""
    rng = np.random.default_rng(seed)
    best = None
    sample = points if len(points) <= 20000 else points[rng.choice(len(points), 20000, replace=False)]
    for _ in range(iters):
        p = sample[rng.choice(len(sample), 3, replace=False)]
        normal = np.cross(p[1] - p[0], p[2] - p[0])
        norm = np.linalg.norm(normal)
        if norm < 1e-6:
            continue
        normal = normal / norm
        offset = -normal @ p[0]
        inliers = np.abs(sample @ normal + offset) < dist
        count = int(inliers.sum())
        if best is None or count > best[0]:
            best = (count, normal, offset, inliers)
    if best is None:
        return {}
    count, normal, offset, inliers = best
    if normal[1] > 0:
        normal, offset = -normal, -offset
    return {"normal": normal.tolist(), "offset": float(offset), "inliers": count,
            "ratio": round(count / len(sample), 3)}


def scan_photo(path: Path, model: Path, marker_size_m: float = 0.10, voxel: float = 0.02) -> Scan:
    img = cv2.imread(str(path))
    if img is None:
        raise FileNotFoundError(path)
    rel_small, infer_s = depth_map(img, model)
    rel = refine_depth(rel_small, img)
    scale, marker = aruco_scale(img, rel, marker_size_m)
    if not scale:
        # No marker: assume the nearest tenth of the frame sits at one metre.
        scale = float(np.percentile(rel, 90)) * 1.0
        marker = {"note": "no marker, assumed scale: nearest tenth at one metre"}
    points, colors = backproject(rel, img, scale)
    points, colors = voxel_downsample(points, colors, voxel)
    meta = {
        "source": path.name,
        "size": [int(img.shape[1]), int(img.shape[0])],
        "inference_s": round(infer_s, 2),
        "points": int(len(points)),
        "scale": round(scale, 5),
        "marker": marker,
        "floor": floor_plane(points),
    }
    return Scan(points=points, colors=colors, scale=scale, meta=meta)


def save(scan: Scan, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out, points=scan.points, colors=scan.colors, meta=json.dumps(scan.meta))


def load(path: Path) -> Scan:
    data = np.load(path, allow_pickle=False)
    meta = json.loads(str(data["meta"]))
    return Scan(points=data["points"], colors=data["colors"], scale=meta.get("scale", 1.0), meta=meta)
