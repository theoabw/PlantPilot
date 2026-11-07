"""Native gaussian splat rendering for previews and stills.

A gaussian is an anisotropic ellipsoid, not a dot. This module projects each
one through the camera Jacobian to a 2D covariance (the EWA splatting
formulation), draws it as a soft ellipse, and blends back to front. That is how
the reference web viewers draw a capture, and it is what makes surfaces read as
textured planes instead of a cloud of points.

It is deliberately not the product viewer: it is a numpy rasteriser that takes
seconds per still, used for the preview PNGs, the deck and the videos. The
product viewer draws the same artifact on the GPU.

The scene's own up axis comes from its metadata, never from a constant here: both
supplied captures are -y up, and a renderer that assumes +y turns them upside
down.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image

from .splat import Scene, SplatError, derive_gaussians, load_sane_prefix


@dataclass
class Gaussians:
    """What a splat renderer needs, one row per gaussian."""

    xyz: np.ndarray      # (n, 3) position in the scene frame
    scale: np.ndarray    # (n, 3) standard deviation per axis, scene units
    rot: np.ndarray      # (n, 4) unit quaternion (w, x, y, z)
    rgb: np.ndarray      # (n, 3) display-referred colour, 0 to 1
    alpha: np.ndarray    # (n,) opacity, 0 to 1

    def __len__(self) -> int:
        return int(self.xyz.shape[0])

    def subset(self, indices: np.ndarray) -> "Gaussians":
        return Gaussians(
            xyz=self.xyz[indices],
            scale=self.scale[indices],
            rot=self.rot[indices],
            rgb=self.rgb[indices],
            alpha=self.alpha[indices],
        )

    def decimate(self, maximum: int | None, seed: int = 0) -> "Gaussians":
        """A deterministic random subset, for a faster preview."""
        if not maximum or maximum >= len(self):
            return self
        rng = np.random.default_rng(seed)
        return self.subset(np.sort(rng.choice(len(self), size=maximum, replace=False)))


def from_scene(scene: Scene, maximum: int | None = None, seed: int = 0) -> Gaussians:
    """The scene artifact as gaussians. Version 1 artifacts get identity rotations."""
    count = scene.xyz.shape[0]
    rot = scene.rot
    if rot is None:
        rot = np.zeros((count, 4), dtype=np.float32)
        rot[:, 0] = 1.0
    gaussians = Gaussians(
        xyz=scene.xyz.astype(np.float64),
        scale=scene.size.astype(np.float64),
        rot=rot.astype(np.float64),
        rgb=scene.rgb.astype(np.float64) / 255.0,
        alpha=scene.alpha.astype(np.float64),
    )
    return gaussians.decimate(maximum, seed=seed)


def from_ply(path: Path, maximum: int | None = None, seed: int = 0) -> Gaussians:
    """Read a 3DGS PLY straight into gaussians, for rendering the capture itself."""
    core, info = load_sane_prefix(Path(path))
    if core.shape[0] == 0:
        raise SplatError(f"{path}: no sane gaussians")
    derived = derive_gaussians(core)
    gaussians = Gaussians(
        xyz=derived["xyz"].astype(np.float64),
        scale=derived["size"].astype(np.float64),
        rot=derived["rot"].astype(np.float64),
        rgb=derived["rgb"].astype(np.float64) / 255.0,
        alpha=derived["alpha"].astype(np.float64),
    )
    del info
    return gaussians.decimate(maximum, seed=seed)


def quat_to_matrix(quaternions: np.ndarray) -> np.ndarray:
    """Batch (w, x, y, z) quaternions to rotation matrices (n, 3, 3)."""
    q = quaternions
    w, x, y, z = q[:, 0], q[:, 1], q[:, 2], q[:, 3]
    matrices = np.empty((q.shape[0], 3, 3), dtype=np.float64)
    matrices[:, 0, 0] = 1.0 - 2.0 * (y * y + z * z)
    matrices[:, 0, 1] = 2.0 * (x * y - z * w)
    matrices[:, 0, 2] = 2.0 * (x * z + y * w)
    matrices[:, 1, 0] = 2.0 * (x * y + z * w)
    matrices[:, 1, 1] = 1.0 - 2.0 * (x * x + z * z)
    matrices[:, 1, 2] = 2.0 * (y * z - x * w)
    matrices[:, 2, 0] = 2.0 * (x * z - y * w)
    matrices[:, 2, 1] = 2.0 * (y * z + x * w)
    matrices[:, 2, 2] = 1.0 - 2.0 * (x * x + y * y)
    return matrices


@dataclass
class Camera:
    """Pinhole camera with the same projection contract as `render.Camera`.

    That contract is `project(points, size)` returning pixel positions, depth,
    radius and a visibility mask, so the box drawing can be shared by the point
    renderer and the splat renderer without either knowing about the other.
    """

    eye: np.ndarray
    forward: np.ndarray
    right: np.ndarray
    up: np.ndarray
    width: int
    height: int
    focal: float
    near: float = 0.4

    @classmethod
    def look_at(cls, eye, target, up_vector, width: int, height: int, fov_deg: float = 65.0,
                near: float = 0.4) -> "Camera":
        eye = np.asarray(eye, dtype=np.float64)
        target = np.asarray(target, dtype=np.float64)
        up_vector = np.asarray(up_vector, dtype=np.float64)
        forward = target - eye
        norm = float(np.linalg.norm(forward))
        if norm < 1e-9:
            raise ValueError("camera eye and target coincide")
        forward = forward / norm
        up_vector = up_vector - forward * float(np.dot(up_vector, forward))
        if float(np.linalg.norm(up_vector)) < 1e-9:
            raise ValueError("camera up vector is parallel to the view direction")
        up_vector = up_vector / float(np.linalg.norm(up_vector))
        right = np.cross(forward, up_vector)
        right = right / float(np.linalg.norm(right))
        focal = 0.5 * height / math.tan(math.radians(fov_deg) / 2.0)
        return cls(eye=eye, forward=forward, right=right, up=up_vector, width=width,
                   height=height, focal=focal, near=near)

    @classmethod
    def from_camera(cls, camera) -> "Camera":
        """Reuse the framing of a `render.Camera`, including its scene up vector."""
        return cls(eye=np.asarray(camera.eye, dtype=np.float64),
                   forward=np.asarray(camera.forward, dtype=np.float64),
                   right=np.asarray(camera.right, dtype=np.float64),
                   up=np.asarray(camera.up, dtype=np.float64),
                   width=camera.width, height=camera.height, focal=float(camera.focal_px))

    def project(self, xyz: np.ndarray, size: np.ndarray | None = None) -> dict:
        rel = np.asarray(xyz, dtype=np.float64) - self.eye
        depth = rel @ self.forward
        safe = np.where(depth > self.near, depth, np.nan)
        px = self.focal * (rel @ self.right) / safe + 0.5 * self.width
        py = 0.5 * self.height - self.focal * (rel @ self.up) / safe
        visible = (
            np.isfinite(px) & np.isfinite(py) & np.isfinite(depth)
            & (depth > self.near)
            & (px >= -64) & (px < self.width + 64)
            & (py >= -64) & (py < self.height + 64)
        )
        return {"px": px, "py": py, "depth": np.nan_to_num(depth, nan=0.0),
                "radius": np.ones(np.asarray(xyz).shape[0]), "visible": visible}


def render(
    gaussians: Gaussians,
    camera: Camera,
    *,
    min_alpha: float = 0.03,
    sigma_cap: float = 32.0,
    max_gaussian_size: float | None = 0.12,
    alpha_boost: float = 1.0,
) -> Image.Image:
    """Draw the gaussians back to front into an RGB image.

    `max_gaussian_size` culls the metre-wide fog gaussians a capture carries;
    they cover whole image regions at low opacity and wash the render out.
    """
    started = time.perf_counter()
    xyz, scale, rot, rgb, alpha = (gaussians.xyz, gaussians.scale, gaussians.rot,
                                   gaussians.rgb, gaussians.alpha)
    rel = xyz - camera.eye
    depth = rel @ camera.forward
    right = rel @ camera.right
    up = rel @ camera.up
    keep = depth > camera.near
    if max_gaussian_size is not None:
        keep &= scale.mean(axis=1) < max_gaussian_size
    keep &= alpha > min_alpha
    index = np.flatnonzero(keep)
    if index.size == 0:
        return Image.new("RGB", (camera.width, camera.height), (0, 0, 0))

    # 3D covariance R diag(scale^2) R^T in the world, then rotated into the camera
    rotation = quat_to_matrix(rot[index])
    scaled = rotation * scale[index][:, None, :]
    cov_world = scaled @ np.transpose(scaled, (0, 2, 1))
    basis = np.stack([camera.right, camera.up, camera.forward])
    cov_camera = np.einsum("ij,njk,lk->nil", basis, cov_world, basis, optimize=True)

    inv_z = 1.0 / depth[index]
    jacobian = np.zeros((index.size, 2, 3))
    jacobian[:, 0, 0] = camera.focal * inv_z
    jacobian[:, 0, 2] = -camera.focal * right[index] * inv_z ** 2
    jacobian[:, 1, 1] = -camera.focal * inv_z
    jacobian[:, 1, 2] = camera.focal * up[index] * inv_z ** 2
    cov_2d = np.einsum("nij,njk,nlk->nil", jacobian, cov_camera, jacobian, optimize=True)
    cov_2d[:, 0, 0] += 0.3
    cov_2d[:, 1, 1] += 0.3

    px = 0.5 * camera.width + camera.focal * right[index] * inv_z
    py = 0.5 * camera.height - camera.focal * up[index] * inv_z
    inside = (px > -64) & (px < camera.width + 64) & (py > -64) & (py < camera.height + 64)
    index = index[inside]
    px, py, cov_2d = px[inside], py[inside], cov_2d[inside]
    depth_visible = depth[index]
    colours = rgb[index]
    opacities = np.clip(alpha[index] * alpha_boost, 0.0, 1.0)

    order = np.argsort(-depth_visible)  # far first
    image = np.zeros((camera.height, camera.width, 3), dtype=np.float64)
    drawn = 0
    width, height = camera.width, camera.height
    for k in order:
        a00, a01, a11 = cov_2d[k, 0, 0], cov_2d[k, 0, 1], cov_2d[k, 1, 1]
        det = a00 * a11 - a01 * a01
        if det <= 1e-12:
            continue
        radius_x = min(sigma_cap, 3.0 * math.sqrt(max(a00, 0.0)))
        radius_y = min(sigma_cap, 3.0 * math.sqrt(max(a11, 0.0)))
        x0 = max(0, int(math.floor(px[k] - radius_x)))
        x1 = min(width - 1, int(math.ceil(px[k] + radius_x)))
        y0 = max(0, int(math.floor(py[k] - radius_y)))
        y1 = min(height - 1, int(math.ceil(py[k] + radius_y)))
        if x0 > x1 or y0 > y1:
            continue
        dx = np.arange(x0, x1 + 1) - px[k]
        dy = np.arange(y0, y1 + 1) - py[k]
        i00, i01, i11 = a11 / det, -a01 / det, a00 / det
        power = -0.5 * (i00 * dx[None, :] ** 2 + i11 * dy[:, None] ** 2) - i01 * dx[None, :] * dy[:, None]
        weight = opacities[k] * np.exp(np.minimum(power, 0.0))
        if weight.max() < 0.002:
            continue
        tile = image[y0:y1 + 1, x0:x1 + 1]
        tile *= (1.0 - weight[:, :, None])
        tile += colours[k][None, None, :] * weight[:, :, None]
        drawn += 1

    del started
    return Image.fromarray((np.clip(image, 0.0, 1.0) * 255.0).astype(np.uint8), "RGB")
