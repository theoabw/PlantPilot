"""Generate the synthetic reference plant: a point cloud with ground truth.

Reads fixtures/plant/plant.json and samples the surfaces it describes, adding
sensor noise and dropout so it reads as a scan rather than as geometry. Writes
data/plant/cloud.npz (points and colours) and data/plant/truth.npz (class and
instance per point) plus a preview PNG.

This is our own data, labelled synthetic wherever it appears. It exists so the
mission demo cannot be blocked by a room with nothing industrial in it, and so
the semantic pipeline can be scored against known ground truth.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "fixtures" / "plant" / "plant.json"
OUT = ROOT / "data" / "plant"

CLASSES = {
    "floor": (0, (150, 150, 145)),
    "wall": (1, (175, 175, 170)),
    "pipe": (2, (70, 110, 70)),
    "pump": (3, (90, 110, 140)),
    "motor": (4, (120, 95, 90)),
    "valve": (5, (125, 105, 60)),
    "tank": (6, (200, 200, 195)),
    "skid": (7, (95, 95, 95)),
    "cabinet": (8, (80, 100, 110)),
    "hx": (9, (140, 125, 100)),
}

FLOOR_DENSITY = 260.0
WALL_DENSITY = 140.0
ASSET_DENSITY = 380.0
PIPE_DENSITY = 380.0
NOISE_M = 0.004
DROPOUT = 0.08


def jitter(colors: np.ndarray, rng: np.random.Generator) -> np.ndarray:
    shift = rng.normal(0, 7, size=colors.shape)
    return np.clip(colors + shift, 0, 255).astype(np.uint8)


def rect_floor(x0, x1, z0, z1, y, density, rng):
    n = max(1, int((x1 - x0) * (z1 - z0) * density))
    xs = rng.uniform(x0, x1, n)
    zs = rng.uniform(z0, z1, n)
    return np.stack([xs, np.full(n, y), zs], axis=1)


def wall_segment(p0, p1, y0, y1, density, rng):
    """A vertical wall between two floor points p0 and p1."""
    p0, p1 = np.array(p0, float), np.array(p1, float)
    length = float(np.linalg.norm(p1 - p0))
    n = max(1, int(length * (y1 - y0) * density))
    t = rng.uniform(0, 1, n)
    y = rng.uniform(y0, y1, n)
    return np.stack([p0[0] + (p1[0] - p0[0]) * t, y, p0[1] + (p1[1] - p0[1]) * t], axis=1)


def box_surface(center, size, density, rng):
    cx, cy, cz = center
    sx, sy, sz = size
    half = np.array([sx, sy, sz]) / 2.0
    out = []
    # top and bottom
    for y in (cy + half[1], cy - half[1]):
        n = max(1, int(sx * sz * density))
        out.append(np.stack([rng.uniform(cx - half[0], cx + half[0], n), np.full(n, y),
                             rng.uniform(cz - half[2], cz + half[2], n)], axis=1))
    # four sides
    for axis, sign in ((0, 1), (0, -1), (2, 1), (2, -1)):
        for ylo, yhi in ((cy - half[1], cy + half[1]),):
            n = max(1, int((sx if axis == 2 else sz) * sy * density))
            y = rng.uniform(ylo, yhi, n)
            fixed = (cy - half[1]) if False else None
            if axis == 0:
                u = rng.uniform(cz - half[2], cz + half[2], n)
                pt = np.stack([np.full(n, cx + sign * half[0]), y, u], axis=1)
            else:
                u = rng.uniform(cx - half[0], cx + half[0], n)
                pt = np.stack([u, y, np.full(n, cz + sign * half[2])], axis=1)
            out.append(pt)
    return np.concatenate(out)


def cylinder_surface(center, radius, height, density, rng, caps=True):
    cx, cy, cz = center
    n_side = max(1, int(2 * np.pi * radius * height * density))
    theta = rng.uniform(0, 2 * np.pi, n_side)
    y = rng.uniform(cy, cy + height, n_side)
    side = np.stack([cx + radius * np.cos(theta), y, cz + radius * np.sin(theta)], axis=1)
    parts = [side]
    if caps:
        n_cap = max(1, int(np.pi * radius ** 2 * density))
        for yy in (cy + height, cy + 0.02):
            r = radius * np.sqrt(rng.uniform(0, 1, n_cap))
            a = rng.uniform(0, 2 * np.pi, n_cap)
            parts.append(np.stack([cx + r * np.cos(a), np.full(n_cap, yy), cz + r * np.sin(a)], axis=1))
    return np.concatenate(parts)


def pipe_surface(p0, p1, radius, density, rng):
    p0, p1 = np.array(p0, float), np.array(p1, float)
    axis = p1 - p0
    length = float(np.linalg.norm(axis))
    if length < 1e-6:
        return np.zeros((0, 3))
    n = max(1, int(2 * np.pi * radius * length * density))
    t = rng.uniform(0, 1, n)
    centre = p0[None, :] + axis[None, :] * t[:, None]
    a = rng.uniform(0, 2 * np.pi, n)
    helper = np.array([0.0, 1.0, 0.0]) if abs(axis[1] / length) < 0.9 else np.array([1.0, 0.0, 0.0])
    e1 = np.cross(axis / length, helper)
    e1 /= np.linalg.norm(e1)
    e2 = np.cross(axis / length, e1)
    return centre + radius * (np.cos(a)[:, None] * e1[None, :] + np.sin(a)[:, None] * e2[None, :])


def build(spec: dict, seed: int = 11):
    rng = np.random.default_rng(seed)
    area = spec["area"]
    cloud, cls, inst = [], [], []
    asset_index = {a["id"]: i for i, a in enumerate(spec["assets"])}

    floor = rect_floor(area["x0"], area["x1"], area["z0"], area["z1"], 0.0, FLOOR_DENSITY, rng)
    cloud.append(floor); cls.append(np.full(len(floor), CLASSES["floor"][0])); inst.append(np.full(len(floor), -1))

    h = area["height"]
    door = spec["door"]
    wall_runs = [
        ((0.0, 0.0), (0.0, area["z1"])),
        ((area["x1"], 0.0), (area["x1"], area["z1"])),
        ((0.0, area["z1"]), (area["x1"], area["z1"])),
    ]
    for p0, p1 in wall_runs:
        pts = wall_segment(p0, p1, 0.0, h, WALL_DENSITY, rng)
        cloud.append(pts); cls.append(np.full(len(pts), CLASSES["wall"][0])); inst.append(np.full(len(pts), -1))
    for x0, x1 in ((0.0, door["x0"]), (door["x1"], area["x1"])):
        pts = wall_segment((x0, 0.0), (x1, 0.0), 0.0, h, WALL_DENSITY, rng)
        cloud.append(pts); cls.append(np.full(len(pts), CLASSES["wall"][0])); inst.append(np.full(len(pts), -1))

    for a in spec["assets"]:
        kind = a["kind"]
        sx, sy, sz = a["size"]
        if a.get("shape") == "cylinder":
            pts = cylinder_surface((a["pos"][0], a["pos"][1], a["pos"][2]), sx / 2.0, sy, ASSET_DENSITY, rng)
        else:
            pts = box_surface((a["pos"][0], a["pos"][1] + sy / 2.0, a["pos"][2]), (sx, sy, sz), ASSET_DENSITY, rng)
        cloud.append(pts)
        cls.append(np.full(len(pts), CLASSES[kind][0]))
        inst.append(np.full(len(pts), asset_index[a["id"]]))

    for p in spec["pipes"]:
        pts = pipe_surface(p["from"], p["to"], p["radius"], PIPE_DENSITY, rng)
        cloud.append(pts); cls.append(np.full(len(pts), CLASSES["pipe"][0])); inst.append(np.full(len(pts), -1))

    points = np.concatenate(cloud)
    classes = np.concatenate(cls)
    instances = np.concatenate(inst)
    points = points + rng.normal(0, NOISE_M, size=points.shape)
    keep = rng.random(len(points)) > DROPOUT
    points, classes, instances = points[keep], classes[keep], instances[keep]

    palette = np.zeros((10, 3), dtype=np.float32)
    for _, (idx, colour) in CLASSES.items():
        palette[idx] = colour
    colours = jitter(palette[classes], rng)
    order = rng.permutation(len(points))
    return points[order].astype(np.float32), colours[order], classes[order].astype(np.int16), instances[order].astype(np.int16)


def preview(points, colours, path: Path, size=(1100, 760)) -> None:
    """An isometric three quarter view, which is how the viewer opens."""
    w, h = size
    eye = np.array([21.0, 13.5, 19.0])
    target = np.array([8.0, 1.2, 5.6])
    forward = target - eye
    forward /= np.linalg.norm(forward)
    right = np.cross(forward, np.array([0.0, 1.0, 0.0]))
    right /= np.linalg.norm(right)
    up = np.cross(right, forward)
    rel = points - eye
    x_c = rel @ right
    y_c = rel @ up
    z = rel @ forward
    f = 0.5 * w / np.tan(np.deg2rad(60) / 2)
    u = (x_c * f / np.maximum(z, 1e-3) + w / 2).astype(int)
    v = (-y_c * f / np.maximum(z, 1e-3) + h / 2).astype(int)
    img = Image.new("RGB", size, (10, 12, 18))
    draw = ImageDraw.Draw(img)
    for i in np.argsort(-z):
        if 0 <= u[i] < w and 0 <= v[i] < h and z[i] > 0.05:
            c = tuple(int(x) for x in colours[i])
            draw.rectangle([u[i], v[i], u[i] + 1, v[i] + 1], fill=c)
    img.save(path)


def main() -> None:
    spec = json.loads(SPEC.read_text())
    points, colours, classes, instances = build(spec)
    OUT.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(OUT / "cloud.npz", points=points, colors=colours)
    np.savez_compressed(OUT / "truth.npz", classes=classes, instances=instances)
    preview(points, colours, OUT / "preview.png")
    counts = {name: int((classes == idx).sum()) for name, (idx, _) in CLASSES.items()}
    print(f"{len(points)} points from {SPEC.relative_to(ROOT)}")
    print("per class:", json.dumps({k: v for k, v in counts.items() if v}))
    print(f"wrote {OUT.relative_to(ROOT)}/cloud.npz, truth.npz, preview.png")


if __name__ == "__main__":
    main()
