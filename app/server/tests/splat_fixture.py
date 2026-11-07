"""Small synthetic splats for the ingest and extraction tests.

The real capture is not in the repository, so the tests build their own: a
floor plane, two solid blocks, a pipe run, and a tail of uninitialised rows that
must be dropped exactly like a malformed export's tail. Everything is offline
and deterministic.
"""

from __future__ import annotations

import struct
from pathlib import Path

import numpy as np

PROPERTIES = (
    "x",
    "y",
    "z",
    "scale_0",
    "scale_1",
    "scale_2",
    "rot_0",
    "rot_1",
    "rot_2",
    "rot_3",
    "f_dc_0",
    "f_dc_1",
    "f_dc_2",
    "opacity",
)


def header(vertices: int, properties: tuple[str, ...] = PROPERTIES) -> bytes:
    lines = [
        "ply",
        "format binary_little_endian 1.0",
        "comment synthetic test splat",
        f"element vertex {vertices}",
        *[f"property float {name}" for name in properties],
        "end_header",
        "",
    ]
    return "\n".join(lines).encode("ascii")


def rows_for(xyz: np.ndarray) -> np.ndarray:
    rows = np.zeros((xyz.shape[0], len(PROPERTIES)), dtype=np.float32)
    rows[:, 0:3] = xyz.astype(np.float32)
    rows[:, 3:6] = np.log(0.007)  # 7 mm gaussians
    rows[:, 6:10] = (1.0, 0.0, 0.0, 0.0)  # unit quaternion
    rows[:, 10:13] = (0.0, 0.0, 0.0)  # mid grey, 0.5 + 0.282 * 0
    rows[:, 13] = 0.0  # alpha 0.5
    return rows


def write_ply(path: Path, xyz: np.ndarray, *, garbage_rows: int = 0) -> Path:
    """Write a valid splat, optionally followed by uninitialised rows."""
    xyz = np.asarray(xyz, dtype=np.float64)
    rows = rows_for(xyz)
    total = rows.shape[0] + garbage_rows
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        f.write(header(total))
        f.write(rows.tobytes())
        for index in range(garbage_rows):
            # a malformed export's tail: huge finite numbers, then NaN
            row = np.full(len(PROPERTIES), 1.0e26, dtype=np.float32)
            if index % 2:
                row[1] = np.nan
            f.write(struct.pack(f"<{len(PROPERTIES)}f", *row))
    return path


def box_shell(origin, size, spacing: float = 0.025, jitter: float = 0.002) -> np.ndarray:
    """The surface of a box, like a splat, rather than its volume.

    A real capture only has surfaces, so the fixture must not fill volumes: a
    solid block would let a plane cut through its interior, which no surface
    scan contains.
    """
    sizes = np.asarray(size, dtype=float)
    counts = np.maximum(2, np.rint(sizes / spacing).astype(int) + 1)
    grids = [np.linspace(0.0, 1.0, int(count)) for count in counts]
    faces: list[np.ndarray] = []
    for axis in range(3):
        for side in (0.0, 1.0):
            first, second = [grids[index] for index in range(3) if index != axis]
            u, v = np.meshgrid(first, second, indexing="ij")
            local = np.zeros((u.size, 3))
            local[:, axis] = side
            local[:, (axis + 1) % 3] = u.ravel()
            local[:, (axis + 2) % 3] = v.ravel()
            faces.append(local * sizes[None, :])
    points = np.concatenate(faces, axis=0) + np.asarray(origin)[None, :]
    rng = np.random.default_rng(1)
    return points + rng.normal(scale=jitter, size=points.shape)


def room(seed: int = 0) -> np.ndarray:
    """A floor, two blocks standing on it, a pipe run, and a few stray points."""
    rng = np.random.default_rng(seed)
    axis_x = np.arange(-1.5, 1.5, 0.02)
    axis_z = np.arange(-1.0, 1.0, 0.02)
    gx, gz = np.meshgrid(axis_x, axis_z, indexing="ij")
    floor = np.stack([gx.ravel(), np.zeros(gx.size), gz.ravel()], axis=1)
    floor += rng.normal(scale=0.001, size=floor.shape)

    first = box_shell((0.10, 0.02, -0.30), (0.40, 0.40, 0.40), 0.02)
    second = box_shell((0.95, 0.02, 0.25), (0.35, 0.55, 0.35), 0.02)
    fourth = box_shell((-0.95, 0.02, 0.30), (0.30, 0.30, 0.30), 0.02)

    pipe_x = np.arange(-1.4, 1.4, 0.01)
    pipe = np.stack([pipe_x, np.full(pipe_x.size, 0.95), np.full(pipe_x.size, -0.1)], axis=1)
    pipe += rng.normal(scale=0.004, size=pipe.shape)

    stray = rng.uniform(low=(-2.0, 0.0, -1.5), high=(2.0, 2.0, 1.5), size=(40, 3))
    return np.concatenate([floor, first, second, fourth, pipe, stray], axis=0)


def room_ply(path: Path, *, garbage_rows: int = 6) -> Path:
    return write_ply(path, room(), garbage_rows=garbage_rows)
