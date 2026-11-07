"""Bake derived information channels of a capture as viewer PLY variants.

The browser room toggles between the photo and four derived views of the same
room: height, normals, edges and semantics. Height, normals, semantics and the
edges base are complete 3DGS PLY files carrying the capture's own position,
scale, rotation and opacity, so the silhouette is identical to the photo asset;
only the DC colour changes, plus the opacity of the non-anchor gaussians in the
semantics variant, which is the one allowed exception and is documented in
`filters.json`. The edges channel is two-part: a dimmed photo base in
`edges_base.ply` and a positions-only contour overlay in `contours.json`.

Conventions, chosen here once:

- Height is height above the detected floor. The 2nd to 98th percentile maps
  onto an inferno palette clamped to 0.05 to 0.95, and the colour is multiplied
  by `0.78 + 0.22 * luma` so the capture's own texture still reads. Everything
  under 0.15 m above the floor is a neutral grey band, so the floor does not
  compete with the room above it.
- A gaussian's normal is the rotation applied to the ellipsoid axis with the
  smallest scale, then smoothed by two voxel averaging passes at 6 cm and 12 cm
  (blending 0.55 and 0.75 towards the voxel means) so single-splat noise does
  not survive. RGB is 0.5 + 0.5 n multiplied by a headlight term, so facets
  read. An artifact without rotations falls back to the up axis.
- Edges are depth-discontinuity contours. Eight deterministic eye-height orbit
  cameras rasterise the gaussian centres into a nearest-depth buffer and an
  owner index. Each depth image is hole-filled, bilateral-filtered (5x5, 1.5 px
  space, 1.5 percent depth range), Gaussian-smoothed (3x3) and run through Canny
  hysteresis at 0.04 and 0.10 of the normalised range. Edge pixels vote for
  their owner gaussian, a gaussian needs at least two view votes, and the top
  four percent of the score, capped at 80,000 points, becomes `contours.json`.
- Semantics colours only the reviewed anchors (falling back to `assets.json`),
  using a fixed 24-entry qualitative palette with alternating lightness and an
  adjacency check at 15 CIELAB delta-E or 60 degrees of hue. Each anchor gets a
  per-gaussian shading factor in [0.85, 1.10] from its position relative to the
  instance centre, so its faces separate without breaking its colour identity.
  Everything outside an anchor becomes a very dark blue-grey dimmed to 12
  percent opacity, so the anchors read as vivid islands against a faint ghost.
  `semantics.ply` keeps that atlas look, and the viewer instead draws the
  dimmed photo base with `anchors_overlay.ply` on top: only the anchor rows, the
  same geometry, a pastel hue mixed 0.55/0.45 with the photo, at 0.55 opacity.
- The contours carry a colour per point: the owning anchor's hue, or light
  cyan-grey when the point belongs to nothing. Points come from two families,
  the depth edges above and instance boundaries where the anchor id of the
  nearest gaussian changes between neighbouring pixels of one view.

The output is byte-identical for the same inputs: no timestamp or machine state
reaches a PLY or the JSON documents.
"""

from __future__ import annotations

import argparse
import colorsys
import json
import math
import sys
import time
from pathlib import Path

import cv2
import numpy as np
from PIL import ImageDraw

from plantpilot import splat, splat_render
from plantpilot.render import floor_height
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
HEIGHT_CLAMP = (0.05, 0.95)
HEIGHT_TEXTURE = (0.78, 0.22)
HEIGHT_NEUTRAL_BELOW_M = 0.15
HEIGHT_NEUTRAL_RGB = np.array([110, 110, 112], dtype=np.float64)
INFERNO_STOPS = np.array(
    [(0, 0, 4), (66, 10, 104), (147, 38, 103), (221, 81, 58), (252, 255, 164)],
    dtype=np.float64,
)

NORMAL_SMOOTHING = ((0.06, 0.55), (0.12, 0.75))
NORMAL_HEADLIGHT_FLOOR = 0.55

# The edge views and the contour extraction parameters from the visual research.
EDGE_VIEWS = 8
EDGE_VIEW_WIDTH, EDGE_VIEW_HEIGHT = 560, 360
EDGE_FOV_DEG = 65.0
EDGE_EYE_HEIGHT_M = 1.55
EDGE_TARGET_HEIGHT_M = 0.90
EDGE_RADIUS_FRACTION = 0.55
EDGE_PERCENTILES = (2.0, 98.0)
EDGE_BILATERAL_D = 5
EDGE_BILATERAL_SIGMA_SPACE = 1.5
EDGE_BILATERAL_SIGMA_RANGE = 0.015
EDGE_GAUSSIAN_KSIZE = 3
EDGE_CANNY_LOW = 0.04
EDGE_CANNY_HIGH = 0.10
EDGE_INPAINT_RADIUS = 3
EDGE_MIN_VOTES = 2
CONTOUR_TOP_FRACTION = 0.03
CONTOUR_MAX_POINTS = 80_000
CONTOUR_INSTANCE_MAX = 40_000
CONTOUR_UNASSIGNED_RGB = (170, 200, 210)
OVERLAY_PASTEL_SATURATION = 0.45
OVERLAY_PASTEL_VALUE = 0.92
OVERLAY_OPACITY_SCALE = 0.55

# A fixed qualitative palette with alternating lightness. The first seven are
# the usual anchors; the rest are backups for the adjacency check.
QUALITATIVE_PALETTE = np.array(
    [
        (235, 72, 60),    # light red
        (46, 84, 156),    # dark blue
        (118, 220, 112),  # light green
        (128, 56, 148),   # dark purple
        (248, 224, 96),   # light yellow
        (30, 136, 136),   # dark teal
        (226, 96, 196),   # light magenta
        (140, 90, 40),    # dark brown
        (130, 200, 255),  # light sky
        (90, 20, 20),     # dark maroon
        (200, 255, 160),  # light lime
        (40, 60, 90),     # dark navy
        (255, 170, 90),   # light orange
        (70, 110, 20),    # dark olive
        (255, 190, 220),  # light pink
        (20, 90, 120),    # dark steel
        (220, 200, 255),  # light lavender
        (150, 40, 40),    # dark brick
        (0, 160, 90),     # light emerald
        (90, 60, 120),    # dark plum
        (255, 240, 160),  # light cream
        (60, 60, 60),     # dark grey
        (200, 140, 255),  # light violet
        (110, 30, 60),    # dark wine
    ],
    dtype=np.uint8,
)
PALETTE_MIN_DELTA_E = 15.0
PALETTE_MIN_HUE_DEG = 60.0

SEMANTICS_ROOM_COLOUR = (14, 18, 28)
SEMANTICS_ROOM_OPACITY_SCALE = 0.12
SEMANTICS_SHADING_RANGE = (0.85, 1.10)
SEMANTICS_SHADING_LIGHT = np.array([1.0, 1.0, 1.0]) / math.sqrt(3.0)

PREVIEW_WIDTH, PREVIEW_HEIGHT = 960, 600
PREVIEW_MAX_GAUSSIANS = 400_000
PREVIEW_ANGLES_DEG = (0.0, 30.0, -30.0)
CONTOUR_OVERLAY_RGB = (255, 200, 120)

VARIANTS = ("height", "normals", "edges", "semantics")

VARIANT_DESCRIPTIONS = {
    "height": "height above the floor on an inferno palette with texture and a neutral floor band",
    "normals": "smoothed gaussian normal as 0.5 + 0.5 n with a headlight term so facets read",
    "edges": "dimmed photo base with a positions-only depth-discontinuity contour overlay",
    "semantics": "reviewed anchors on an adjacency-checked qualitative palette against a dimmed room",
}

VARIANT_NOTES = {
    "edges": (
        "edges_base.ply is the photo colour multiplied by 0.30, opacity unchanged; contours.json "
        "carries the top four percent of the depth-discontinuity score from eight orbit views, at "
        "least two votes each, capped at 80,000 points; the two are drawn together"
    ),
    "semantics": (
        "only the reviewed anchors are coloured, with a fixed qualitative palette and a per-gaussian "
        "shading factor in 0.85 to 1.10; every other gaussian is dark blue-grey with opacity scaled "
        "to 12 percent, the one variant whose opacity differs from the photo PLY"
    ),
}


# ---------------------------------------------------------------------------
# Palettes


def ramp(values: np.ndarray, stops: np.ndarray) -> np.ndarray:
    """Map values in [0, 1] through evenly spaced colour stops, as float."""
    values = np.clip(np.asarray(values, dtype=np.float64), 0.0, 1.0)
    positions = np.linspace(0.0, 1.0, stops.shape[0])
    channels = [np.interp(values, positions, stops[:, channel]) for channel in range(3)]
    return np.stack(channels, axis=-1)


def srgb_to_lab(rgb: np.ndarray) -> np.ndarray:
    """Convert one sRGB triple in [0, 255] to CIELAB."""
    value = np.asarray(rgb, dtype=np.float64) / 255.0
    value = np.where(value <= 0.04045, value / 12.92, ((value + 0.055) / 1.055) ** 2.4)
    matrix = np.array(
        [[0.4124564, 0.3575761, 0.1804375],
         [0.2126729, 0.7151522, 0.0721750],
         [0.0193339, 0.1191920, 0.9503041]]
    )
    xyz = value @ matrix.T
    white = np.array([0.95047, 1.00000, 1.08883])
    ratio = xyz / white
    delta = 6.0 / 29.0
    f = np.where(ratio > delta ** 3, np.cbrt(ratio), ratio / (3.0 * delta ** 2) + 4.0 / 29.0)
    return np.array([116.0 * f[1] - 16.0, 500.0 * (f[0] - f[1]), 200.0 * (f[1] - f[2])])


def rgb_hue(rgb: np.ndarray) -> float:
    """HSV hue in degrees for one sRGB triple."""
    red, green, blue = (float(value) / 255.0 for value in rgb)
    hue = colorsys.rgb_to_hsv(red, green, blue)[0] * 360.0
    return hue


def colours_are_distinct(left: np.ndarray, right: np.ndarray) -> bool:
    """True when two palette colours are not close in both lightness and hue.

    The review's rule is that a pair within 15 CIELAB delta-E or 60 degrees of
    hue is confusable, so a candidate is shifted when it is close on both axes.
    Differing strongly on either axis is enough to tell the two apart, which is
    what lets seven anchors share the wheel.
    """
    delta_e = float(np.linalg.norm(srgb_to_lab(left) - srgb_to_lab(right)))
    hue = abs(rgb_hue(left) - rgb_hue(right))
    hue = min(hue, 360.0 - hue)
    return delta_e >= PALETTE_MIN_DELTA_E or hue >= PALETTE_MIN_HUE_DEG


def select_anchor_palette(count: int, palette: np.ndarray = QUALITATIVE_PALETTE) -> list[np.ndarray]:
    """Pick `count` high-separation entries from the qualitative palette.

    Each candidate has to clear both the CIELAB and the hue distance against
    every earlier choice; when it does not, the next palette entry is tried, as
    the review asked. With a well-spread palette and seven anchors the first
    seven entries usually survive, but the rule is enforced rather than assumed.
    """
    chosen: list[np.ndarray] = []
    cursor = 0
    for _ in range(count):
        candidate = palette[cursor % palette.shape[0]]
        attempts = 0
        while attempts < palette.shape[0] and any(
            not colours_are_distinct(candidate, earlier) for earlier in chosen
        ):
            cursor += 1
            candidate = palette[cursor % palette.shape[0]]
            attempts += 1
        chosen.append(np.asarray(candidate, dtype=np.uint8).copy())
        cursor += 1
    return chosen


# ---------------------------------------------------------------------------
# Height


def height_fraction(scene: Scene) -> np.ndarray:
    """Height above the floor, normalised on the 2nd to 98th percentile."""
    above = scene.height() - float(floor_height(scene))
    low, high = np.percentile(above, HEIGHT_PERCENTILES)
    if not np.isfinite(low) or not np.isfinite(high) or high <= low:
        return np.full(above.shape[0], 0.5, dtype=np.float64)
    return np.clip((above - low) / (high - low), 0.0, 1.0)


def height_colours(scene: Scene) -> np.ndarray:
    """Inferno over the clamped height, textured by luma, neutral on the floor."""
    fraction = height_fraction(scene)
    clamped = HEIGHT_CLAMP[0] + (HEIGHT_CLAMP[1] - HEIGHT_CLAMP[0]) * fraction
    palette = ramp(clamped, INFERNO_STOPS)
    luma = (
        0.2126 * scene.rgb[:, 0] + 0.7152 * scene.rgb[:, 1] + 0.0722 * scene.rgb[:, 2]
    ) / 255.0
    texture = HEIGHT_TEXTURE[0] + HEIGHT_TEXTURE[1] * luma
    colours = palette * texture[:, None]
    above = scene.height() - float(floor_height(scene))
    neutral = above < HEIGHT_NEUTRAL_BELOW_M
    colours[neutral] = HEIGHT_NEUTRAL_RGB[None, :] * texture[neutral, None]
    return np.clip(np.rint(colours), 0.0, 255.0).astype(np.uint8)


# ---------------------------------------------------------------------------
# Normals


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


def voxel_mean_normals(xyz: np.ndarray, normals: np.ndarray, voxel: float) -> np.ndarray:
    """Mean unit normal of each gaussian's voxel, broadcast back to gaussians."""
    xyz = np.asarray(xyz, dtype=np.float64)
    normals = np.asarray(normals, dtype=np.float64)
    indices = np.floor((xyz - xyz.min(axis=0)) / voxel).astype(np.int64)
    dims = indices.max(axis=0) + 1
    keys = (indices[:, 0] * dims[1] + indices[:, 1]) * dims[2] + indices[:, 2]
    _, inverse = np.unique(keys, return_inverse=True)
    inverse = inverse.reshape(-1).astype(np.int64)
    size = int(inverse.max()) + 1 if inverse.size else 0
    sums = np.stack(
        [np.bincount(inverse, weights=normals[:, axis], minlength=size) for axis in range(3)],
        axis=1,
    )
    means = sums[inverse]
    length = np.linalg.norm(means, axis=1, keepdims=True)
    return means / np.maximum(length, 1e-12)


def smoothed_normals(scene: Scene) -> np.ndarray:
    """Thin-axis normals blended towards two voxel means, 6 cm then 12 cm."""
    normals = gaussian_normals(scene)
    for voxel, weight in NORMAL_SMOOTHING:
        averaged = voxel_mean_normals(scene.xyz, normals, voxel)
        normals = (1.0 - weight) * normals + weight * averaged
        length = np.linalg.norm(normals, axis=1, keepdims=True)
        normals = normals / np.maximum(length, 1e-12)
    return normals


def normal_colours(scene: Scene, light_direction: np.ndarray | None = None) -> np.ndarray:
    """Encode smoothed normals as 0.5 + 0.5 n, optionally headlight shaded."""
    normals = smoothed_normals(scene)
    encoded = 0.5 + 0.5 * normals
    if light_direction is not None:
        light = np.asarray(light_direction, dtype=np.float64)
        light = light / max(float(np.linalg.norm(light)), 1e-12)
        facing = np.clip(-(normals @ light), 0.0, 1.0)
        encoded = encoded * (NORMAL_HEADLIGHT_FLOOR + (1.0 - NORMAL_HEADLIGHT_FLOOR) * facing)[:, None]
    return np.clip(np.rint(encoded * 255.0), 0.0, 255.0).astype(np.uint8)


# ---------------------------------------------------------------------------
# Edges: depth-discontinuity contours


def rasterise_centres(xyz: np.ndarray, camera: splat_render.Camera) -> tuple[np.ndarray, np.ndarray]:
    """Nearest-depth image and owner index of a point cloud, sorted by pixel.

    Every gaussian centre is projected, then sorted by pixel and depth; the
    first row per pixel is the nearest centre and owns that pixel. This is the
    cheap z buffer the contour channel needs, not a splat rasteriser.
    """
    xyz = np.asarray(xyz, dtype=np.float64)
    width, height = int(camera.width), int(camera.height)
    depth_image = np.full((height, width), np.nan, dtype=np.float64)
    index_image = np.full((height, width), -1, dtype=np.int32)
    if xyz.shape[0] == 0:
        return depth_image, index_image

    projection = camera.project(xyz)
    depth = projection["depth"]
    finite = (
        np.isfinite(projection["px"])
        & np.isfinite(projection["py"])
        & np.isfinite(depth)
        & (depth > camera.near)
    )
    visible = projection["visible"] & finite
    if not visible.any():
        return depth_image, index_image
    owner = np.flatnonzero(visible)
    rows = np.rint(projection["py"][visible]).astype(np.int64)
    cols = np.rint(projection["px"][visible]).astype(np.int64)
    inside = (cols >= 0) & (cols < width) & (rows >= 0) & (rows < height)
    if not inside.any():
        return depth_image, index_image
    owner = owner[inside]
    rows, cols, depth = rows[inside], cols[inside], depth[visible][inside]
    pixels = rows * width + cols

    order = np.lexsort((depth, pixels))
    ordered_pixels = pixels[order]
    first = np.ones(order.size, dtype=bool)
    first[1:] = ordered_pixels[1:] != ordered_pixels[:-1]
    winners = order[first]
    winning_rows = rows[winners]
    winning_cols = cols[winners]
    depth_image[winning_rows, winning_cols] = depth[winners]
    index_image[winning_rows, winning_cols] = owner[winners]
    return depth_image, index_image


def depth_edges(depth: np.ndarray) -> np.ndarray:
    """Boolean one-pixel contour mask from a depth image.

    Splat centres leave sub-pixel holes, so the image is hole-filled first;
    then the research pass's filters apply: 5x5 bilateral at 1.5 px and 1.5
    percent of the normalised depth range, a 3x3 Gaussian, and Canny hysteresis
    at 0.04 and 0.10 of the range. Log depth keeps the far wall from flattening
    the near field.
    """
    depth = np.asarray(depth, dtype=np.float64)
    valid = np.isfinite(depth)
    if int(valid.sum()) < 64:
        return np.zeros(depth.shape, dtype=bool)
    values = depth[valid]
    low, high = np.percentile(values, EDGE_PERCENTILES)
    if not np.isfinite(low) or not np.isfinite(high) or high <= low:
        return np.zeros(depth.shape, dtype=bool)
    span = math.log(max(high, 1e-9)) - math.log(max(low, 1e-9))
    if span <= 1e-9:
        return np.zeros(depth.shape, dtype=bool)
    normalised = np.zeros(depth.shape, dtype=np.float64)
    near = (np.log(np.maximum(values, 1e-9)) - math.log(max(low, 1e-9))) / span
    normalised[valid] = np.clip(near, 0.0, 1.0)
    image = np.rint(normalised * 255.0).astype(np.uint8)
    invalid = (~valid).astype(np.uint8)
    if invalid.any():
        image = cv2.inpaint(image, invalid, EDGE_INPAINT_RADIUS, cv2.INPAINT_TELEA)
    image = cv2.bilateralFilter(
        image,
        EDGE_BILATERAL_D,
        EDGE_BILATERAL_SIGMA_RANGE * 255.0,
        EDGE_BILATERAL_SIGMA_SPACE,
    )
    image = cv2.GaussianBlur(image, (EDGE_GAUSSIAN_KSIZE, EDGE_GAUSSIAN_KSIZE), 0.0)
    return cv2.Canny(
        image,
        EDGE_CANNY_LOW * 255.0,
        EDGE_CANNY_HIGH * 255.0,
    ) > 0


def orbit_cameras(scene: Scene, count: int = EDGE_VIEWS) -> list[splat_render.Camera]:
    """Deterministic eye-height orbit of the room, looking at its centre."""
    up = np.zeros(3, dtype=np.float64)
    up[scene.up_index] = float(scene.up_sign)
    low, high = np.percentile(scene.xyz, EDGE_PERCENTILES, axis=0)
    centre = (low + high) / 2.0
    floor = float(floor_height(scene))
    horizontal = [axis for axis in range(3) if axis != scene.up_index]
    span = high - low
    half_diagonal = 0.5 * math.sqrt(float(span[horizontal[0]] ** 2 + span[horizontal[1]] ** 2))
    radius = max(0.5, EDGE_RADIUS_FRACTION * half_diagonal)
    eye_height = floor + EDGE_EYE_HEIGHT_M
    target_height = floor + EDGE_TARGET_HEIGHT_M
    cameras = []
    for index in range(count):
        angle = 2.0 * math.pi * index / count
        eye = centre.copy()
        eye[horizontal[0]] = centre[horizontal[0]] + radius * math.cos(angle)
        eye[horizontal[1]] = centre[horizontal[1]] + radius * math.sin(angle)
        eye[scene.up_index] = scene.up_sign * eye_height
        target = centre.copy()
        target[scene.up_index] = scene.up_sign * target_height
        cameras.append(
            splat_render.Camera.look_at(
                eye, target, up, EDGE_VIEW_WIDTH, EDGE_VIEW_HEIGHT, fov_deg=EDGE_FOV_DEG,
            )
        )
    return cameras


def contour_votes(scene: Scene, cameras: list[splat_render.Camera] | None = None) -> tuple[np.ndarray, dict]:
    """Per-gaussian contour vote over the orbit views, plus the distribution."""
    cameras = orbit_cameras(scene) if cameras is None else cameras
    count = int(scene.xyz.shape[0])
    votes = np.zeros(count, dtype=np.int64)
    for camera in cameras:
        depth, owner = rasterise_centres(scene.xyz, camera)
        edges = depth_edges(depth)
        if not edges.any():
            continue
        owners = owner[edges]
        owners = owners[owners >= 0]
        if owners.size:
            votes += np.bincount(owners, minlength=count)
    hist = np.bincount(votes).tolist()
    return votes, {"views": len(cameras), "vertices": count, "vote_histogram": hist}


def edges_base_colours(scene: Scene) -> np.ndarray:
    """The photo colour at 30 percent luminance, keeping its chroma."""
    return np.clip(np.rint(np.asarray(scene.rgb, dtype=np.float64) * 0.30), 0.0, 255.0).astype(np.uint8)


def pastel_colour(base_rgb) -> np.ndarray:
    """The pastel version of an anchor hue: same hue, lower saturation, lighter."""
    red, green, blue = (float(value) / 255.0 for value in base_rgb)
    hue = colorsys.rgb_to_hsv(red, green, blue)[0]
    pastel = colorsys.hsv_to_rgb(hue, OVERLAY_PASTEL_SATURATION, OVERLAY_PASTEL_VALUE)
    return np.clip(np.asarray(pastel, dtype=np.float64) * 255.0, 0.0, 255.0)


def anchors_overlay_colours(
    scene: Scene,
    labels: np.ndarray,
    entries: list[dict],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Tint colours for anchor-owned gaussians, plus the pastel per entry.

    The tint is 0.55 * pastel anchor hue + 0.45 * photo colour, so the capture
    reads through the tint. Only anchor-owned rows are filled; the rest stay
    black and are never written. Returns (colours full length, mask, pastels).
    """
    colours = np.zeros((labels.shape[0], 3), dtype=np.float64)
    pastels = np.stack([pastel_colour(entry["colour"]) for entry in entries]) if entries else np.zeros((0, 3))
    mask = labels >= 0
    if mask.any() and entries:
        photo = np.asarray(scene.rgb, dtype=np.float64)[mask]
        tint = 0.55 * pastels[labels[mask]] + 0.45 * photo
        colours[mask] = np.clip(tint, 0.0, 255.0)
    return colours, mask, pastels


def anchors_overlay_rows(
    geometry: np.ndarray,
    scene: Scene,
    labels: np.ndarray,
    entries: list[dict],
    colours: np.ndarray,
    mask: np.ndarray,
) -> np.ndarray:
    """The overlay PLY rows: anchor gaussians only, same geometry, 0.55 opacity."""
    rows = geometry[mask].copy()
    display = np.clip(colours[mask] / 255.0, 0.0, 1.0)
    rows[:, 10:13] = ((display - 0.5) / SH_DC).astype(np.float32)
    alpha = 1.0 / (1.0 + np.exp(-geometry[mask][:, 13].astype(np.float64)))
    alpha = np.clip(alpha * OVERLAY_OPACITY_SCALE, 1e-6, 1.0 - 1e-6)
    rows[:, 13] = np.log(alpha / (1.0 - alpha)).astype(np.float32)
    return rows


def instance_boundary_owners(owner: np.ndarray, labels: np.ndarray) -> np.ndarray:
    """Owner gaussians that sit on a boundary between two anchor ids.

    `owner` is the depth index image of one view and `labels` maps a gaussian to
    its anchor entry (-1 outside). A horizontal or vertical neighbour pair with
    different ids contributes the owner of each side that is an anchor, so the
    boundary between an anchor and the room is kept and the boundary between two
    anchors contributes both of their owners.
    """
    owner = np.asarray(owner, dtype=np.int64)
    labels = np.asarray(labels, dtype=np.int64)
    safe = np.maximum(owner, 0)
    ids = np.where(owner >= 0, labels[safe], -1)
    collected: list[np.ndarray] = []
    pairs = (
        (ids[:, :-1] != ids[:, 1:], owner[:, :-1], owner[:, 1:], ids[:, :-1], ids[:, 1:]),
        (ids[:-1, :] != ids[1:, :], owner[:-1, :], owner[1:, :], ids[:-1, :], ids[1:, :]),
    )
    for differs, owner_a, owner_b, ids_a, ids_b in pairs:
        for take, candidates in ((differs & (ids_a >= 0), owner_a), (differs & (ids_b >= 0), owner_b)):
            chosen = candidates[take]
            chosen = chosen[chosen >= 0]
            if chosen.size:
                collected.append(chosen)
    if not collected:
        return np.zeros(0, dtype=np.int64)
    return np.concatenate(collected)


def instance_boundary_votes(
    scene: Scene,
    labels: np.ndarray,
    cameras: list[splat_render.Camera],
) -> tuple[np.ndarray, dict]:
    """Per-gaussian votes from anchor-id discontinuities across the orbit views."""
    count = int(scene.xyz.shape[0])
    votes = np.zeros(count, dtype=np.int64)
    pixels = 0
    for camera in cameras:
        _, owner = rasterise_centres(scene.xyz, camera)
        chosen = instance_boundary_owners(owner, labels)
        if chosen.size:
            votes += np.bincount(chosen, minlength=count)
            pixels += int(chosen.size)
    return votes, {"views": len(cameras), "points_considered": pixels}


def contour_payload(
    scene: Scene,
    depth_votes: np.ndarray,
    boundary_votes: np.ndarray,
    labels: np.ndarray,
    entries: list[dict],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, dict]:
    """Combined contour points, their per-point score and RGB, and the counts.

    Depth-discontinuity points take the top four percent of the per-gaussian
    vote score (at least two view votes). Instance-boundary points are the
    gaussians owning an anchor-id discontinuity in any view, appended after the
    depth points and capped so the total stops at 80,000. Colours use the owning
    anchor's hue, light cyan-grey when the point belongs to no anchor.
    """
    count = int(depth_votes.shape[0])
    max_depth = int(depth_votes.max()) if count else 0
    depth_scores = np.where(
        depth_votes >= EDGE_MIN_VOTES,
        depth_votes / max_depth if max_depth > 0 else 0.0,
        0.0,
    )
    depth_eligible = np.flatnonzero(depth_scores > 0.0)
    # The fraction is taken over the scored population, not all gaussians: a
    # small vote threshold marks most surfaces from some view and the overlay
    # reads as dust. Taking the top 3 percent of scored points keeps the lines.
    scored = int(np.count_nonzero(depth_votes > 0))
    depth_limit = min(
        max(1, int(round(CONTOUR_TOP_FRACTION * scored))) if scored else 0,
        CONTOUR_MAX_POINTS,
        depth_eligible.size,
    )
    if depth_limit > 0:
        order = np.lexsort((depth_eligible, -depth_scores[depth_eligible]))
        depth_points = np.sort(depth_eligible[order[:depth_limit]])
    else:
        depth_points = np.zeros(0, dtype=np.int64)

    max_boundary = int(boundary_votes.max()) if count else 0
    boundary_scores = boundary_votes / max_boundary if max_boundary > 0 else np.zeros(count)
    boundary_eligible = np.flatnonzero((boundary_votes > 0) & (boundary_scores > 0.0))
    boundary_eligible = boundary_eligible[~np.isin(boundary_eligible, depth_points)]
    boundary_limit = min(
        CONTOUR_INSTANCE_MAX,
        CONTOUR_MAX_POINTS - int(depth_points.size),
        int(boundary_eligible.size),
    )
    if boundary_limit > 0:
        order = np.lexsort((boundary_eligible, -boundary_scores[boundary_eligible]))
        boundary_points = np.sort(boundary_eligible[order[:boundary_limit]])
    else:
        boundary_points = np.zeros(0, dtype=np.int64)

    indices = np.sort(np.concatenate([depth_points, boundary_points])).astype(np.int64)
    scores_full = np.zeros(count, dtype=np.float64)
    scores_full[depth_points] = depth_scores[depth_points]
    scores_full[boundary_points] = boundary_scores[boundary_points]
    colours = np.zeros((indices.size, 3), dtype=np.uint8)
    for position, index in enumerate(indices):
        label = int(labels[index])
        if label >= 0 and entries:
            colours[position] = np.asarray(entries[label]["colour"], dtype=np.uint8)
        else:
            colours[position] = np.asarray(CONTOUR_UNASSIGNED_RGB, dtype=np.uint8)
    points = np.asarray(scene.xyz, dtype=np.float64)[indices]
    stats = {
        "count": int(indices.size),
        "depth_edges": int(depth_points.size),
        "instance_boundaries": int(boundary_points.size),
        "depth_available": int(depth_eligible.size),
        "depth_scored": int(np.count_nonzero(depth_votes > 0)),
        "boundary_available": int(boundary_eligible.size),
        "top_fraction": CONTOUR_TOP_FRACTION,
        "cap": CONTOUR_MAX_POINTS,
        "max_depth_votes": max_depth,
        "max_boundary_votes": max_boundary,
        "depth_votes_histogram": np.bincount(depth_votes).tolist() if count else [],
        "boundary_votes_histogram": np.bincount(boundary_votes).tolist() if count else [],
        "score_p50": round(float(np.percentile(scores_full[indices], 50)), 5) if indices.size else 0.0,
        "score_p90": round(float(np.percentile(scores_full[indices], 90)), 5) if indices.size else 0.0,
        "score_p99": round(float(np.percentile(scores_full[indices], 99)), 5) if indices.size else 0.0,
    }
    return points, scores_full[indices], colours, stats


# ---------------------------------------------------------------------------
# Semantics: reviewed anchors on a qualitative palette


def semantics_records(anchors: dict | None, assets: dict) -> tuple[list[dict], str]:
    """The reviewed anchors when available, otherwise the merged asset boxes."""
    if anchors and anchors.get("anchors"):
        return list(anchors["anchors"]), "anchor"
    return list(assets.get("assets", [])), "asset"


def _box_volume(record: dict) -> float:
    return float(np.prod(np.asarray(record["extents"], dtype=np.float64)))


def semantic_assignment(
    xyz: np.ndarray,
    records: list[dict],
    source: str = "anchor",
) -> tuple[np.ndarray, list[dict], np.ndarray]:
    """Assign each gaussian to the smallest covering anchor box.

    Returns the entry index per gaussian (-1 unassigned), the entries that own
    at least one gaussian in document order, and the per-gaussian shading factor
    in the reviewed range. The shading is derived from the position relative to
    the instance centre along one fixed light direction, so the faces of an
    instance separate while its palette colour stays its identity.
    """
    xyz = np.asarray(xyz, dtype=np.float64)
    count = xyz.shape[0]
    labels = np.full(count, -1, dtype=np.int32)
    shading = np.ones(count, dtype=np.float64)

    palette = select_anchor_palette(len(records))
    entries = []
    for position, record in enumerate(records):
        entry = {
            "source": source,
            "id": str(record["id"]),
            "label": str(record.get("label") or record.get("class") or record["id"]),
            "class": str(record.get("class", "unknown")),
            "colour": [int(value) for value in palette[position]],
            "pastel": [int(value) for value in pastel_colour(palette[position])],
            "shading_range": list(SEMANTICS_SHADING_RANGE),
            "gaussians": 0,
        }
        for key in ("asset_id", "reviewed", "verdict", "confidence"):
            if key in record:
                entry[key] = record[key]
        if "points" in record:
            entry["points_in_box"] = int(record["points"])
        entries.append(entry)

    order = sorted(
        range(len(records)),
        key=lambda position: (_box_volume(records[position]), str(records[position]["id"])),
    )
    for position in order:
        record = records[position]
        centre = np.asarray(record["centre"], dtype=np.float64)
        axes = np.asarray(record["axes"], dtype=np.float64).reshape(3, 3)
        extents = np.asarray(record["extents"], dtype=np.float64)
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
        labels[chosen] = int(position)
        entries[position]["gaussians"] = int(chosen.size)
        half = max(float(extents.max()) / 2.0, 1e-6)
        forward = (xyz[chosen] - centre) @ SEMANTICS_SHADING_LIGHT
        factor = np.clip(0.5 + 0.5 * forward / half, 0.0, 1.0)
        low, high = SEMANTICS_SHADING_RANGE
        shading[chosen] = low + (high - low) * factor

    used_positions = [position for position, entry in enumerate(entries) if entry["gaussians"] > 0]
    used_entries = [entries[position] for position in used_positions]
    if len(used_positions) != len(entries):
        remap = {old: new for new, old in enumerate(used_positions)}
        positive = labels >= 0
        labels[positive] = np.asarray([remap[int(value)] for value in labels[positive]], dtype=np.int32)
    return labels, used_entries, shading


def semantic_colours(labels: np.ndarray, entries: list[dict], shading: np.ndarray | None = None) -> np.ndarray:
    """Palette colour times the instance shading, dark blue-grey where unassigned."""
    colours = np.tile(np.asarray(SEMANTICS_ROOM_COLOUR, dtype=np.float64), (labels.shape[0], 1))
    for index, entry in enumerate(entries):
        colours[labels == index] = np.asarray(entry["colour"], dtype=np.float64)
    if shading is not None:
        colours = colours * np.asarray(shading, dtype=np.float64)[:, None]
    return np.clip(np.rint(colours), 0.0, 255.0).astype(np.uint8)


def semantic_opacity_scale(labels: np.ndarray) -> np.ndarray:
    """Full opacity on anchors, the room dimming everywhere else."""
    return np.where(labels >= 0, 1.0, SEMANTICS_ROOM_OPACITY_SCALE).astype(np.float64)


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


def colour_rows(geometry: np.ndarray, colours: np.ndarray, opacity_scale: np.ndarray | None = None) -> np.ndarray:
    """The geometry columns with a display colour written as DC terms.

    `opacity_scale` is the semantics exception: a per-gaussian multiplier on the
    scene's own opacity, written back as its logit. Every other variant keeps
    the geometry array untouched.
    """
    rows = geometry.copy()
    display = np.clip(np.asarray(colours, dtype=np.float64) / 255.0, 0.0, 1.0)
    rows[:, 10:13] = ((display - 0.5) / SH_DC).astype(np.float32)
    if opacity_scale is not None:
        alpha = 1.0 / (1.0 + np.exp(-rows[:, 13].astype(np.float64)))
        alpha = np.clip(alpha * np.asarray(opacity_scale, dtype=np.float64), 1e-6, 1.0 - 1e-6)
        rows[:, 13] = np.log(alpha / (1.0 - alpha)).astype(np.float32)
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


def _preview_cameras(camera: dict, up: np.ndarray, angles_deg: tuple[float, ...]) -> list[splat_render.Camera]:
    """The objects camera plus rotations of its eye about the target."""
    eye = np.asarray(camera["eye"], dtype=np.float64)
    target = np.asarray(camera["target"], dtype=np.float64)
    axis = np.asarray(up, dtype=np.float64)
    axis = axis / max(float(np.linalg.norm(axis)), 1e-12)
    offset = eye - target
    vertical = axis * float(offset @ axis)
    flat = offset - vertical
    cameras = []
    for angle_deg in angles_deg:
        angle = math.radians(angle_deg)
        rotated = flat * math.cos(angle) + np.cross(axis, flat) * math.sin(angle)
        rotated_eye = target + vertical + rotated
        cameras.append(
            splat_render.Camera.look_at(
                rotated_eye, target, axis, PREVIEW_WIDTH, PREVIEW_HEIGHT,
            )
        )
    return cameras


def _project_coloured_points(points: np.ndarray, colours: np.ndarray, camera: splat_render.Camera) -> dict:
    """Projected integer pixels grouped by RGB, so ImageDraw stamps each colour once."""
    points = np.asarray(points, dtype=np.float64)
    colours = np.asarray(colours, dtype=np.int64).reshape(-1, 3)
    if points.shape[0] != colours.shape[0] or points.shape[0] == 0:
        return {}
    projection = camera.project(points)
    visible = projection["visible"] & np.isfinite(projection["px"]) & np.isfinite(projection["py"])
    if not visible.any():
        return {}
    cols = np.rint(projection["px"][visible]).astype(np.int64)
    rows = np.rint(projection["py"][visible]).astype(np.int64)
    inside = (cols >= 0) & (cols < camera.width) & (rows >= 0) & (rows < camera.height)
    groups: dict[tuple[int, int, int], list[tuple[int, int]]] = {}
    for (red, green, blue), col, row in zip(colours[visible][inside], cols[inside], rows[inside]):
        groups.setdefault((int(red), int(green), int(blue)), []).append((int(col), int(row)))
    return groups


def preview_paths(
    scene: Scene,
    colours: dict[str, np.ndarray],
    alphas: dict[str, np.ndarray],
    camera: dict,
    out: Path,
    contours: np.ndarray | None = None,
    contour_colours: np.ndarray | None = None,
) -> dict[str, list[str]]:
    """Render three previews per channel from the objects camera and two orbits.

    The edges preview shows the dimmed base plus the contour points. The
    semantics preview shows the agreed composite: the dimmed photo base with the
    pastel anchor overlay and the contour points on top, which is what the
    viewer draws.
    """
    picked = splat.decimate(int(scene.xyz.shape[0]), PREVIEW_MAX_GAUSSIANS, seed=0)
    view = splat_render.from_scene(scene).subset(picked)
    up = np.zeros(3, dtype=np.float64)
    up[scene.up_index] = float(scene.up_sign)
    cameras = _preview_cameras(camera, up, PREVIEW_ANGLES_DEG)
    paths: dict[str, list[str]] = {}
    for name in VARIANTS:
        variant_paths = []
        for position in range(len(PREVIEW_ANGLES_DEG)):
            gaussians = splat_render.Gaussians(
                xyz=view.xyz,
                scale=view.scale,
                rot=view.rot,
                rgb=colours[name][picked].astype(np.float64) / 255.0,
                alpha=alphas[name][picked].astype(np.float64),
            )
            image = splat_render.render(gaussians, cameras[position])
            if name in ("edges", "semantics") and contours is not None and len(contours):
                groups = _project_coloured_points(contours, contour_colours, cameras[position])
                if groups:
                    draw = ImageDraw.Draw(image)
                    for colour, pixels in groups.items():
                        draw.point(pixels, fill=colour)
            suffix = "" if position == 0 else f"_alt{position}"
            path = out / f"preview_{name}{suffix}.png"
            image.save(path)
            variant_paths.append(str(_display_path(path)))
        paths[name] = variant_paths
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
    anchors: dict | None = None,
    *,
    scene_path: Path = Path("data/equipment/scene.npz"),
    objects_path: Path = Path("data/equipment/objects.json"),
    assets_path: Path = Path("data/equipment/assets.json"),
    anchors_path: Path | None = None,
    out: Path | None = None,
    previews: bool = True,
    keep_fog: bool = False,
) -> dict:
    """Write the variant PLYs, overlay PLY, contours, legend, index and previews."""
    started = time.perf_counter()
    capture = str(scene.meta.get("source", {}).get("file", "capture"))
    keep = np.ones(scene.xyz.shape[0], dtype=bool) if keep_fog else fog_keep(scene)
    view = subset_scene(scene, keep)
    dropped = int(scene.xyz.shape[0] - view.xyz.shape[0])
    geometry = geometry_rows(view)

    started_height = time.perf_counter()
    height = height_colours(view)
    height_seconds = time.perf_counter() - started_height

    started_normals = time.perf_counter()
    camera = objects.get("camera") or {}
    if camera:
        light = np.asarray(camera["target"], dtype=np.float64) - np.asarray(camera["eye"], dtype=np.float64)
    else:
        light = None
    normals = normal_colours(view, light)
    normals_seconds = time.perf_counter() - started_normals

    started_semantics = time.perf_counter()
    records, semantics_source = semantics_records(anchors, assets)
    assignment, legend_entries, shading = semantic_assignment(view.xyz, records, source=semantics_source)
    semantics = semantic_colours(assignment, legend_entries, shading)
    opacity_scale = semantic_opacity_scale(assignment)
    overlay_colours, overlay_mask, pastels = anchors_overlay_colours(view, assignment, legend_entries)
    overlay_rows = anchors_overlay_rows(geometry, view, assignment, legend_entries, overlay_colours, overlay_mask)
    semantics_seconds = time.perf_counter() - started_semantics

    started_edges = time.perf_counter()
    edges_base = edges_base_colours(view)
    cameras = orbit_cameras(view)
    depth_votes, _ = contour_votes(view, cameras)
    boundary_votes, _ = instance_boundary_votes(view, assignment, cameras)
    contours, contour_scores, contour_colours, contour_stats = contour_payload(
        view, depth_votes, boundary_votes, assignment, legend_entries,
    )
    edges_seconds = time.perf_counter() - started_edges

    alpha = np.asarray(view.alpha, dtype=np.float64)
    colours = {"height": height, "normals": normals, "edges": edges_base, "semantics": semantics}
    alphas = {
        "height": alpha,
        "normals": alpha,
        "edges": alpha,
        "semantics": alpha * opacity_scale,
    }
    opacity_scales = {"height": None, "normals": None, "edges": None, "semantics": opacity_scale}

    # The viewer's semantics channel is the dimmed base plus the pastel overlay,
    # so its preview is that composite rather than the vivid atlas colours.
    composite_colours = edges_base.copy()
    composite_colours[overlay_mask] = np.clip(overlay_colours[overlay_mask], 0.0, 255.0)
    composite_alphas = alpha.copy()
    composite_alphas[overlay_mask] = alpha[overlay_mask] * OVERLAY_OPACITY_SCALE
    preview_colours = dict(colours)
    preview_colours["semantics"] = composite_colours
    preview_alphas = dict(alphas)
    preview_alphas["semantics"] = composite_alphas

    out = Path(out) if out is not None else ROOT / "data" / "viewer" / "filters" / Path(scene_path).resolve().parent.name
    out.mkdir(parents=True, exist_ok=True)
    stale = out / "edges.ply"
    if stale.exists():
        stale.unlink()
    files = {}
    for name in VARIANTS:
        filename = "edges_base.ply" if name == "edges" else f"{name}.ply"
        files[name] = write_ply(
            colour_rows(geometry, colours[name], opacity_scale=opacity_scales[name]),
            out / filename,
            f"filter variant {name} for {capture}, written by scripts/make_filter_assets.py",
        )
    overlay_file = write_ply(
        overlay_rows,
        out / "anchors_overlay.ply",
        f"pastel anchor tint layer for {capture}, written by scripts/make_filter_assets.py",
    )

    contour_document = {
        "artifact": "contours",
        "version": 1,
        "count": int(contours.shape[0]),
        "points": [[round(float(value), 4) for value in point] for point in contours],
        "colors": [[int(value) for value in colour] for colour in contour_colours],
        "contour_scores": [round(float(value), 6) for value in contour_scores],
        "families": {
            "depth_edges": contour_stats["depth_edges"],
            "instance_boundaries": contour_stats["instance_boundaries"],
        },
        "source": "depth_discontinuity",
    }
    contours_path = out / "contours.json"
    contours_path.write_text(json.dumps(contour_document) + "\n")

    assigned = int((assignment >= 0).sum())
    unassigned = int(view.xyz.shape[0] - assigned)
    legend = {
        "artifact": "semantics-legend",
        "version": 4,
        "source": {
            "scene": _display_path(Path(scene_path)),
            "assets": _display_path(Path(assets_path)),
            "anchors": None if anchors_path is None else _display_path(Path(anchors_path)),
            "objects": _display_path(Path(objects_path)),
            "capture": capture,
            "semantics_source": semantics_source,
            "gaussians": int(view.xyz.shape[0]),
            "source_gaussians": int(scene.xyz.shape[0]),
            "fog_culled": dropped,
        },
        "room": {
            "label": "unassigned room",
            "colour": list(SEMANTICS_ROOM_COLOUR),
            "opacity_scale": SEMANTICS_ROOM_OPACITY_SCALE,
            "gaussians": unassigned,
        },
        "palette": {
            "scheme": "qualitative, adjacency checked at 15 CIELAB delta-E and 60 degrees of hue",
            "entries": [list(int(value) for value in colour) for colour in QUALITATIVE_PALETTE],
            "overlay": "0.55 * pastel hue + 0.45 * photo colour, opacity 0.55 of original",
            "contours": "owning anchor hue, light cyan-grey when unowned",
        },
        "counts": {
            "entries": len(legend_entries),
            "assigned": assigned,
            "unassigned": unassigned,
            "anchors": int(sum(1 for entry in legend_entries if entry["source"] == "anchor")),
            "assets": int(sum(1 for entry in legend_entries if entry["source"] == "asset")),
            "overlay_gaussians": int(overlay_mask.sum()),
        },
        "entries": legend_entries,
    }
    legend_path = out / "semantics_legend.json"
    legend_path.write_text(json.dumps(legend, indent=1) + "\n")

    if previews and not camera:
        raise SystemExit(f"{objects_path}: no camera in the objects artifact, cannot render previews")
    started_previews = time.perf_counter()
    previews_path = (
        preview_paths(view, preview_colours, preview_alphas, camera, out,
                      contours=contours, contour_colours=contour_colours)
        if previews else {}
    )
    preview_seconds = time.perf_counter() - started_previews if previews else 0.0

    filters = {
        "artifact": "filter-assets",
        "version": 4,
        "source": {
            "scene": _display_path(Path(scene_path)),
            "objects": _display_path(Path(objects_path)),
            "assets": _display_path(Path(assets_path)),
            "anchors": None if anchors_path is None else _display_path(Path(anchors_path)),
            "capture": capture,
            "semantics_source": semantics_source,
            "gaussians": int(view.xyz.shape[0]),
            "source_gaussians": int(scene.xyz.shape[0]),
            "fog_culled": dropped,
        },
        "geometry": {
            "properties": list(CORE_PROPERTIES),
            "identity": (
                "xyz, scale and rotation are identical in all four PLYs and equal the photo PLY rows; "
                "anchors_overlay.ply is a subset of those rows with the same geometry; opacity is "
                "identical in height, normals and edges; opacity differs in semantics (non-anchor rows "
                "dimmed) and anchors_overlay (0.55 of original), the two allowed exceptions"
            ),
            "opacity_exceptions": {
                "semantics": {"non_anchor_scale": SEMANTICS_ROOM_OPACITY_SCALE},
                "anchors_overlay": {"scale": OVERLAY_OPACITY_SCALE},
            },
            "fog_cull": {"mean_size_m": FOG_MEAN_SIZE_M, "alpha_min": FOG_ALPHA_MIN},
        },
        "filters": {"applied": list(VARIANTS)},
        "overlays": {
            "anchors_overlay.ply": overlay_file,
            "contours.json": {
                "file": contours_path.name,
                "count": int(contours.shape[0]),
                "bytes": int(contours_path.stat().st_size),
                "families": contour_document["families"],
            },
        },
        "variants": {
            name: {
                **files[name],
                "preview": previews_path.get(name, [None])[0],
                "extra_previews": previews_path.get(name, [])[1:],
                "description": VARIANT_DESCRIPTIONS[name],
                "note": VARIANT_NOTES.get(name, VARIANT_DESCRIPTIONS[name]),
            }
            for name in VARIANTS
        },
    }
    filters["variants"]["height"]["method"] = {
        "channel": "height above floor",
        "palette": "inferno",
        "percentiles": list(HEIGHT_PERCENTILES),
        "clamp": list(HEIGHT_CLAMP),
        "texture": "0.78 + 0.22 * luma",
        "neutral_below_m": HEIGHT_NEUTRAL_BELOW_M,
    }
    filters["variants"]["normals"]["method"] = {
        "channel": "thin-axis normal",
        "smoothing": [{"voxel_m": voxel, "blend": blend} for voxel, blend in NORMAL_SMOOTHING],
        "headlight_floor": NORMAL_HEADLIGHT_FLOOR,
        "encoding": "0.5 + 0.5 n",
    }
    filters["variants"]["edges"]["base"] = "edges_base.ply"
    filters["variants"]["edges"]["overlay"] = "contours.json"
    filters["variants"]["edges"]["method"] = {
        "channel": "depth discontinuity",
        "base": "photo colour multiplied by 0.30, opacity unchanged",
        "views": contour_stats.get("views", EDGE_VIEWS),
        "view_size": [EDGE_VIEW_WIDTH, EDGE_VIEW_HEIGHT],
        "min_votes": EDGE_MIN_VOTES,
        "bilateral": {
            "diameter": EDGE_BILATERAL_D,
            "sigma_space_px": EDGE_BILATERAL_SIGMA_SPACE,
            "sigma_range_fraction": EDGE_BILATERAL_SIGMA_RANGE,
        },
        "gaussian_ksize": EDGE_GAUSSIAN_KSIZE,
        "canny": {"low": EDGE_CANNY_LOW, "high": EDGE_CANNY_HIGH},
        "top_fraction": contour_stats["top_fraction"],
        "cap": contour_stats["cap"],
        **{key: contour_stats[key] for key in (
            "count", "depth_edges", "instance_boundaries", "depth_available",
            "boundary_available", "max_depth_votes", "max_boundary_votes",
            "depth_votes_histogram", "boundary_votes_histogram",
            "score_p50", "score_p90", "score_p99",
        )},
    }
    filters["variants"]["semantics"]["base"] = "edges_base.ply"
    filters["variants"]["semantics"]["overlay"] = "anchors_overlay.ply"
    filters["variants"]["semantics"]["contours"] = "contours.json"
    filters["variants"]["semantics"]["method"] = {
        "channel": "reviewed anchors",
        "debug_file": "semantics.ply",
        "viewer": "edges_base.ply + anchors_overlay.ply + contours.json",
        "semantics_source": semantics_source,
        "palette": "qualitative, adjacency checked",
        "palette_entries": [
            {"id": entry["id"], "label": entry["label"], "colour": entry["colour"], "pastel": entry["pastel"]}
            for entry in legend_entries
        ],
        "overlay": "0.55 * pastel + 0.45 * photo colour, opacity 0.55 of original",
        "shading_range": list(SEMANTICS_SHADING_RANGE),
        "room_opacity_scale": SEMANTICS_ROOM_OPACITY_SCALE,
        "entries": legend["counts"]["entries"],
        "assigned": assigned,
        "unassigned": unassigned,
        "overlay_gaussians": int(overlay_mask.sum()),
    }
    filters_path = out / "filters.json"
    filters_path.write_text(json.dumps(filters, indent=1) + "\n")
    total_seconds = time.perf_counter() - started
    return {
        "out": _display_path(out),
        "files": files,
        "overlays": filters["overlays"],
        "previews": previews_path,
        "legend": _display_path(legend_path),
        "filters": _display_path(filters_path),
        "contours": contour_stats,
        "semantics_counts": legend["counts"],
        "palette": [
            {"id": entry["id"], "label": entry["label"], "base": entry["colour"], "pastel": entry["pastel"]}
            for entry in legend_entries
        ],
        "timings_s": {
            "height": round(height_seconds, 2),
            "normals": round(normals_seconds, 2),
            "edges": round(edges_seconds, 2),
            "semantics": round(semantics_seconds, 2),
            "previews": round(preview_seconds, 2),
            "total": round(total_seconds, 2),
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python scripts/make_filter_assets.py",
        description="Bake height, normals, edges and semantics viewer assets from a scene artifact.",
    )
    parser.add_argument("--scene", default=Path("data/equipment/scene.npz"), type=Path)
    parser.add_argument("--objects", default=Path("data/equipment/objects.json"), type=Path)
    parser.add_argument("--assets", default=Path("data/equipment/assets.json"), type=Path)
    parser.add_argument(
        "--anchors", default=None, type=Path,
        help="reviewed anchor document; defaults to <capture>/anchors.json when it exists, else assets",
    )
    parser.add_argument(
        "--out", default=None, type=Path,
        help="output directory; defaults to data/viewer/filters/<scene directory name>",
    )
    parser.add_argument("--keep-fog", action="store_true", help="keep the fog gaussians the photo asset culls")
    parser.add_argument("--no-previews", action="store_true", help="skip the preview PNGs")
    args = parser.parse_args(argv)

    try:
        scene = load_scene(args.scene)
        objects = json.loads(Path(args.objects).read_text())
        assets = json.loads(Path(args.assets).read_text())
        anchors = None
        anchors_path = args.anchors
        if anchors_path is None:
            candidate = Path(args.scene).parent / "anchors.json"
            anchors_path = candidate if candidate.exists() else None
        if anchors_path is not None:
            anchors = json.loads(Path(anchors_path).read_text())
        summary = bake(
            scene, objects, assets, anchors,
            scene_path=args.scene, objects_path=args.objects, assets_path=args.assets,
            anchors_path=anchors_path, out=args.out, previews=not args.no_previews,
            keep_fog=args.keep_fog,
        )
    except Exception as exc:  # noqa: BLE001 - the message is the point of the failure
        print(f"filter assets failed: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
