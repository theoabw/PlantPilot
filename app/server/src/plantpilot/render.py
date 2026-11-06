"""Debug renderer for the scene artifact.

This is not the product viewer. It renders a point cloud and, optionally, the
oriented boxes from `objects.json` into a PNG with numpy and PIL, so the stages
that produce those artifacts can be checked offline and in CI where there is no
browser. The numbers a `make` target prints come from the same data the app
serves; this file only draws it.

Splat points are drawn as small discs sized from each gaussian's scale at its
depth, and blended by opacity. Boxes are drawn as their twelve edges.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from . import splat_render
from .splat import Scene, load_scene

AXES = ("x", "y", "z")
BACKGROUND = (6, 8, 10)
DEFAULT_SIZE = (1600, 1000)

# One colour per class proposal. Anything unmapped stays neutral grey.
CLASS_COLOURS = {
    "pump": (255, 96, 96),
    "motor": (255, 160, 64),
    "valve": (255, 224, 96),
    "pipe": (96, 200, 255),
    "duct": (96, 255, 200),
    "door": (200, 120, 255),
    "drum": (255, 120, 220),
    "pallet": (180, 255, 96),
    "cabinet": (140, 170, 255),
    "panel": (255, 190, 140),
    "ladder": (150, 255, 200),
    "beam": (150, 200, 220),
    "tray": (200, 200, 120),
    "machine": (240, 240, 240),
    "structure": (170, 170, 170),
    "unknown": (150, 150, 150),
}
FAULT_COLOUR = (255, 40, 40)


@dataclass
class Camera:
    """A pinhole camera with its basis in world coordinates."""

    eye: np.ndarray
    forward: np.ndarray
    right: np.ndarray
    up: np.ndarray
    width: int
    height: int
    focal_px: float
    half_width: float | None = None
    orthographic: bool = False
    near: float = 0.35
    meta: dict = field(default_factory=dict)

    @classmethod
    def look_at(
        cls,
        eye,
        target,
        up_vector,
        width: int,
        height: int,
        fov_deg: float = 60.0,
        orthographic: bool = False,
        half_width: float | None = None,
    ) -> "Camera":
        eye = np.asarray(eye, dtype=np.float64)
        target = np.asarray(target, dtype=np.float64)
        up_vector = np.asarray(up_vector, dtype=np.float64)
        forward = target - eye
        norm = float(np.linalg.norm(forward))
        if norm < 1e-9:
            raise ValueError("camera eye and target coincide")
        forward = forward / norm
        up_vector = up_vector - forward * float(np.dot(up_vector, forward))
        if float(np.linalg.norm(up_vector)) < 1e-6:
            raise ValueError("camera up vector is parallel to the view direction")
        up_vector = up_vector / float(np.linalg.norm(up_vector))
        right = np.cross(forward, up_vector)
        fov = math.radians(fov_deg)
        ortho = orthographic or half_width is not None
        return cls(
            eye=eye,
            forward=forward,
            right=right,
            up=up_vector,
            width=width,
            height=height,
            focal_px=0.5 * height / math.tan(fov / 2.0),
            half_width=half_width,
            orthographic=ortho,
            meta={"fov_deg": fov_deg, "orthographic": ortho},
        )

    def project(self, xyz: np.ndarray, size: np.ndarray | None = None) -> dict:
        """Project points to pixel coordinates plus a disc radius in pixels."""
        rel = xyz - self.eye
        if self.orthographic:
            half_w = float(self.half_width or 1.0)
            half_h = half_w * self.height / self.width
            u = (rel @ self.right) / (2.0 * half_w) + 0.5
            v = 0.5 - (rel @ self.up) / (2.0 * half_h)
            depth = -(rel @ self.forward) * -1.0
            radius = np.full(xyz.shape[0], 1.0)
        else:
            depth = rel @ self.forward
            safe = np.where(depth > self.near, depth, np.nan)
            u = self.focal_px * (rel @ self.right) / safe
            v = self.focal_px * (rel @ self.up) / safe
            u = u / self.width + 0.5
            v = 0.5 - v / self.height
            if size is None:
                radius = np.ones(xyz.shape[0])
            else:
                mean_size = np.mean(np.asarray(size, dtype=np.float64), axis=1)
                radius = 2.0 * self.focal_px * mean_size / safe
                radius = np.clip(radius, 0.7, 7.0)
        px = u * self.width
        py = v * self.height
        visible = (
            np.isfinite(px)
            & np.isfinite(py)
            & np.isfinite(depth)
            & (depth > self.near - 1e9 if self.orthographic else depth > self.near)
            & (px >= -32)
            & (px < self.width + 32)
            & (py >= -32)
            & (py < self.height + 32)
        )
        return {"px": px, "py": py, "depth": np.nan_to_num(depth, nan=0.0), "radius": radius, "visible": visible}


def splat_points(camera: Camera, scene: Scene, radius_scale: float = 1.0) -> Image.Image:
    """Render the point cloud with weighted alpha blending."""
    proj = camera.project(scene.xyz, scene.size)
    visible = proj["visible"]
    if not visible.any():
        raise ValueError("no point falls inside the camera frustum")

    px = proj["px"][visible]
    py = proj["py"][visible]
    radius = proj["radius"][visible] * radius_scale
    rgb = scene.rgb[visible].astype(np.float64) / 255.0
    alpha = scene.alpha[visible].astype(np.float64)

    width, height = camera.width, camera.height
    colour = np.zeros((height * width, 3), dtype=np.float64)
    weight = np.zeros(height * width, dtype=np.float64)
    base_x = np.rint(px).astype(np.int64)
    base_y = np.rint(py).astype(np.int64)

    buckets = np.clip(np.rint(radius).astype(np.int64), 0, 6)
    write = np.isfinite(rgb).all(axis=1)
    for bucket in np.unique(buckets[write]):
        index = np.flatnonzero(write & (buckets == bucket))
        offsets = _disc_offsets(int(bucket))
        gain = (float(bucket) + 1.0) ** 2 * 0.35
        step = 0.75 if bucket == 0 else 0.55
        for dx, dy in offsets:
            x = base_x[index] + dx
            y = base_y[index] + dy
            inside = (x >= 0) & (x < width) & (y >= 0) & (y < height)
            if not inside.any():
                continue
            flat = (y[inside] * width + x[inside]).astype(np.int64)
            w = alpha[index][inside] * gain * step
            for channel in range(3):
                np.add.at(colour[:, channel], flat, w * rgb[index][inside, channel])
            np.add.at(weight, flat, w)

    average = colour / np.maximum(weight, 1e-9)[:, None]
    image = np.clip(average, 0.0, 1.0).reshape(height, width, 3)
    return Image.fromarray((image * 255.0).astype(np.uint8), "RGB")


def _disc_offsets(radius: int) -> list[tuple[int, int]]:
    if radius <= 0:
        return [(0, 0)]
    offsets = []
    for dy in range(-radius, radius + 1):
        for dx in range(-radius, radius + 1):
            if dx * dx + dy * dy <= radius * radius:
                offsets.append((dx, dy))
    return offsets


def _font() -> ImageFont.ImageFont:
    for candidate in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ):
        path = Path(candidate)
        if path.exists():
            return ImageFont.truetype(str(path), 15)
    return ImageFont.load_default()


def box_corners(centre, axes, extents) -> np.ndarray:
    """The eight corners of an oriented box, in world coordinates."""
    centre = np.asarray(centre, dtype=np.float64)
    axes = np.asarray(axes, dtype=np.float64).reshape(3, 3)
    half = np.asarray(extents, dtype=np.float64) / 2.0
    corners = []
    for sx in (-1.0, 1.0):
        for sy in (-1.0, 1.0):
            for sz in (-1.0, 1.0):
                corners.append(centre + axes.T @ (half * np.array([sx, sy, sz])))
    return np.array(corners)


BOX_EDGES = (
    (0, 1),
    (0, 2),
    (0, 4),
    (1, 3),
    (1, 5),
    (2, 3),
    (2, 6),
    (3, 7),
    (4, 5),
    (4, 6),
    (5, 7),
    (6, 7),
)


def draw_boxes(image: Image.Image, camera: Camera, objects: list[dict], *, fault_id: str | None = None,
               label: bool = True, width: int = 2) -> Image.Image:
    """Draw the wireframe of every object box onto the image."""
    canvas = image.copy()
    draw = ImageDraw.Draw(canvas)
    font = _font()
    for obj in objects:
        corners = box_corners(obj["centre"], obj["axes"], obj["extents"])
        zero = np.zeros_like(corners)
        proj = camera.project(corners, zero)
        if not bool(proj["visible"].all()):
            continue
        px, py = proj["px"], proj["py"]
        cls = str(obj.get("class", "unknown"))
        colour = FAULT_COLOUR if obj.get("id") == fault_id else CLASS_COLOURS.get(cls, CLASS_COLOURS["unknown"])
        for a, b in BOX_EDGES:
            draw.line([(float(px[a]), float(py[a])), (float(px[b]), float(py[b]))], fill=colour, width=width)
        if label:
            cx, cy = float(px.mean()), float(py.mean())
            text = f"{obj.get('id', '?')} {cls}"
            draw.text((cx + 3, cy - 8), text, fill=colour, font=font,
                      stroke_width=2, stroke_fill=(0, 0, 0))
    return canvas


def _up_vector(up_index: int, up_sign: int) -> np.ndarray:
    vector = np.zeros(3)
    vector[up_index] = float(up_sign)
    return vector


def perspective_camera(scene: Scene, width: int, height: int, fov_deg: float = 62.0,
                       azimuth_deg: float = 35.0, elevation_deg: float = 8.0) -> Camera:
    """A camera outside the cloud, at eye height above the floor, looking at its centre."""
    up = _up_vector(scene.up_index, scene.up_sign)
    height_coord = scene.height()
    horizontal = [axis for axis in range(3) if axis != scene.up_index]
    centre = scene.xyz.mean(axis=0)
    centre[scene.up_index] = float(np.percentile(height_coord, 55.0)) * scene.up_sign
    span = np.percentile(scene.xyz[:, horizontal], 98, axis=0) - np.percentile(scene.xyz[:, horizontal], 2, axis=0)
    radius = 0.5 * math.sqrt(float(np.sum(np.square(span)))) * 1.15
    radius = max(radius, 0.5)
    yaw = math.radians(azimuth_deg)
    flat = np.zeros(3)
    flat[horizontal[0]] = math.cos(yaw)
    flat[horizontal[1]] = math.sin(yaw)
    rise = math.radians(elevation_deg)
    eye = centre + radius * (flat * math.cos(rise) + up * math.sin(rise))
    return Camera.look_at(eye, centre, up, width, height, fov_deg=fov_deg)


def floor_height(scene: Scene) -> float:
    """The up-axis coordinate of the densest flat slab, which is the floor.

    The ingest detector signs the up axis so that the densest slab is the floor,
    and records that slab and sign in the metadata. Falls back to the lowest
    dense band when the evidence is missing.
    """
    frame = scene.meta.get("frame", {})
    evidence = frame.get("up_axis_evidence", {}) or {}
    slab = evidence.get("slab")
    sign = int(evidence.get("sign", frame.get("up_axis_sign", 1)) or 1)
    if slab is not None:
        return float(sign) * float(slab)
    return float(np.percentile(scene.height(), 1.0))


def hero_camera(scene: Scene, width: int, height: int, fov_deg: float = 66.0) -> Camera:
    """A person's view inside the room, standing where there is space to stand.

    The floor comes from the detected slab, eye height sits 1.45 m above it, and
    the standing position is chosen on a grid over the footprint by distance to
    the nearest thing at torso height. That avoids parking the camera inside a
    machine, which is what a plain orbit camera does, and it needs no constant
    from this room.
    """
    import cv2

    up = _up_vector(scene.up_index, scene.up_sign)
    horizontal = [axis for axis in range(3) if axis != scene.up_index]
    floor = floor_height(scene)
    heights = scene.height()
    points = scene.xyz
    torso = (heights > floor + 0.7) & (heights < floor + 1.9)
    obstacles = points[torso] if int(torso.sum()) > 500 else points

    lo = np.percentile(points[:, horizontal], 2, axis=0)
    hi = np.percentile(points[:, horizontal], 98, axis=0)
    cell = 0.15
    cols = max(4, int(np.ceil((hi[0] - lo[0]) / cell)))
    rows = max(4, int(np.ceil((hi[1] - lo[1]) / cell)))
    occupied = np.zeros((rows, cols), dtype=np.uint8)
    cols_index = np.clip(((obstacles[:, horizontal[0]] - lo[0]) / cell).astype(int), 0, cols - 1)
    rows_index = np.clip(((obstacles[:, horizontal[1]] - lo[1]) / cell).astype(int), 0, rows - 1)
    occupied[rows_index, cols_index] = 1
    free = (1 - occupied).astype(np.uint8)
    clearance = cv2.distanceTransform(free, cv2.DIST_L2, 5) * cell

    centre = points.mean(axis=0)
    steps = np.arange(0.12, 0.9, 0.06)
    angles = np.linspace(0.0, 2.0 * np.pi, 24, endpoint=False)
    best: tuple[float, np.ndarray] | None = None
    for step in steps:
        for angle in angles:
            candidate = centre.copy()
            candidate[horizontal[0]] = centre[horizontal[0]] + step * (hi[0] - lo[0]) * math.cos(angle)
            candidate[horizontal[1]] = centre[horizontal[1]] + step * (hi[1] - lo[1]) * math.sin(angle)
            column = int((candidate[horizontal[0]] - lo[0]) / cell)
            row = int((candidate[horizontal[1]] - lo[1]) / cell)
            if not (1 <= row < rows - 1 and 1 <= column < cols - 1):
                continue
            if occupied[row, column]:
                continue
            score = float(clearance[row, column])
            if best is None or score > best[0]:
                best = (score, candidate)
    if best is None:
        eye = centre - 0.4 * (hi[0] - lo[0]) * _axis_vector(horizontal[0])
    else:
        eye = best[1]
    eye = eye - up * float(eye @ up) + up * (floor + 1.45)
    target = centre - up * float(centre @ up) + up * (floor + 0.9)
    return Camera.look_at(eye, target, up, width, height, fov_deg=fov_deg)


def _axis_vector(axis: int) -> np.ndarray:
    vector = np.zeros(3)
    vector[axis] = 1.0
    return vector


def top_down_camera(scene: Scene, width: int, height: int) -> Camera:
    """Orthographic camera looking straight down the up axis."""
    up = _up_vector(scene.up_index, scene.up_sign)
    horizontal = [axis for axis in range(3) if axis != scene.up_index]
    centre = scene.xyz.mean(axis=0)
    span_u = float(np.ptp(np.percentile(scene.xyz[:, horizontal[0]], [1, 99])))
    span_v = float(np.ptp(np.percentile(scene.xyz[:, horizontal[1]], [1, 99])))
    half = 0.55 * max(span_u, span_v, 0.5) * 1.05
    eye = centre + up * 10.0
    camera = Camera.look_at(eye, centre, np.eye(3)[horizontal[1]] * (-1.0), width, height,
                            orthographic=True, half_width=half * width / max(width, height) * 1.0)
    camera.half_width = half
    return camera


def load_objects(path: Path) -> dict:
    return json.loads(Path(path).read_text())


def render_scene(
    scene: Scene,
    out: Path,
    *,
    objects: list[dict] | None = None,
    fault_id: str | None = None,
    width: int = DEFAULT_SIZE[0],
    height: int = DEFAULT_SIZE[1],
    view: str = "hero",
    mode: str = "splats",
    max_gaussians: int | None = None,
    eye: tuple[float, float, float] | None = None,
    target: tuple[float, float, float] | None = None,
) -> Path:
    """Render one view and write a PNG. Returns the path written.

    `splats` draws the room the way a capture viewer does: every gaussian as a
    soft ellipse from its own covariance, back to front. `points` is the fast
    debug view, used for the top view where the boxes matter more than the room.
    """
    if eye is not None and target is not None:
        camera = Camera.look_at(eye, target, _up_vector(scene.up_index, scene.up_sign), width, height)
    elif view == "top":
        camera = top_down_camera(scene, width, height)
    elif view == "perspective":
        camera = perspective_camera(scene, width, height)
    else:
        camera = hero_camera(scene, width, height)
    if mode == "splats" and view != "top":
        gaussians = splat_render.from_scene(scene, maximum=max_gaussians)
        image = splat_render.render(gaussians, splat_render.Camera.from_camera(camera))
    else:
        image = splat_points(camera, scene)
    if objects:
        image = draw_boxes(image, camera, objects, fault_id=fault_id)
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    image.save(out)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m plantpilot.render",
        description="Render the scene artifact, and optionally the object boxes, to a PNG.",
    )
    parser.add_argument("--scene", default=Path("data/scene/scene.npz"), type=Path)
    parser.add_argument("--objects", default=None, type=Path)
    parser.add_argument("--out", default=Path("data/scene/preview.png"), type=Path)
    parser.add_argument("--view", default="hero", choices=("hero", "perspective", "top"),
                        help="hero is a person's view inside the room; perspective orbits from outside")
    parser.add_argument("--eye", default=None, help="camera position as x,y,z")
    parser.add_argument("--target", default=None, help="look-at point as x,y,z")
    parser.add_argument("--mode", default="splats", choices=("splats", "points"),
                        help="splats draws native gaussian splats (slower, like a capture viewer); "
                             "points is the fast debug view, and the only mode for the top view")
    parser.add_argument("--max-gaussians", default=400_000, type=int,
                        help="deterministic subset for the preview; 0 keeps every gaussian")
    parser.add_argument("--width", default=DEFAULT_SIZE[0], type=int)
    parser.add_argument("--height", default=DEFAULT_SIZE[1], type=int)
    parser.add_argument("--fault-id", default=None)
    parser.add_argument("--json", action="store_true", help="print the camera and counts as JSON")
    args = parser.parse_args(argv)

    try:
        scene = load_scene(args.scene)
    except Exception as exc:  # noqa: BLE001 - the message is the point of the failure
        print(f"render failed: {exc}", file=sys.stderr)
        return 2
    objects = None
    fault = args.fault_id
    if args.objects is not None:
        payload = load_objects(args.objects)
        objects = payload.get("objects", [])
        fault = fault or (payload.get("mapping") or {}).get("faulty_target")
    maximum = args.max_gaussians if args.max_gaussians and args.max_gaussians > 0 else None
    if args.view == "top" and args.mode == "splats":
        args.mode = "points"  # the top view is a layout drawing, fast points are enough
    eye = tuple(float(v) for v in args.eye.split(",")) if args.eye else None
    target = tuple(float(v) for v in args.target.split(",")) if args.target else None
    out = render_scene(
        scene,
        args.out,
        objects=objects,
        fault_id=fault,
        width=args.width,
        height=args.height,
        view=args.view,
        mode=args.mode,
        max_gaussians=maximum,
        eye=eye,
        target=target,
    )
    if args.json:
        print(json.dumps({
            "view": args.view,
            "points": int(scene.xyz.shape[0]),
            "boxes": 0 if objects is None else len(objects),
            "out": str(out),
            "bytes": out.stat().st_size,
        }))
    else:
        print(f"{args.view} view ({args.mode}) of {scene.xyz.shape[0]:,} points"
              + (f" with {len(objects)} boxes" if objects else "")
              + f" written to {out} ({out.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
