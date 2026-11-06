"""Ingest a 3D Gaussian splatting PLY into the scene artifact.

This module is the only place that knows the delivered file format. It
validates the header loudly, keeps only plausible gaussians, decimates to a
render budget and writes one npz that every later stage reads.

Nothing here is specific to the supplied boiler room. Bounds, the up axis,
counts and sizes are measured and reported in the artifact metadata, and every
threshold is a parameter with a stated default, so the same command runs on
another capture. The one assumption is written down in the metadata: the file
units are treated as metres until the scale check in `segment` says otherwise.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

# The standard 3D Gaussian splatting property set. A file missing any of these
# is not a splat this pipeline can read, and the loader says so by name.
CORE_PROPERTIES = (
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
# Optional higher order spherical harmonics. Present in every export we have
# seen, ignored: colour comes from the DC term.
OPTIONAL_PROPERTIES = tuple(f"f_rest_{i}" for i in range(45))

# 3DGS stores colour as 0.5 + C0 * f_dc, where C0 is the first spherical
# harmonic coefficient. This is a convention of the format, not a scene value.
SH_DC = 0.28209479177387814

SCENE_VERSION = 2
DEFAULT_BUDGET = 600_000
AXES = ("x", "y", "z")

# Plausibility bounds for one gaussian. These are format sanity checks, not
# scene measurements: a finite row outside them is uninitialised memory from a
# truncated export, not a point in the room.
MAX_ABS_CORE = 1.0e6
SCALE_RANGE = (-20.0, 5.0)
QUATERNION_NORM = (0.9, 1.1)
DC_RANGE = (-10.0, 10.0)
OPACITY_RANGE = (-20.0, 20.0)

# Densest slab used to find the floor when detecting the up axis. A floor is
# the sharpest large flat surface in an indoor capture, so the detector slides
# a window down a fine histogram and keeps the window holding the most points.
# The window is wide enough to survive the tilt of a real floor; both numbers
# are spatial scale, not room constants, and both are reported.
SLAB_WIDTH = 0.15
HISTOGRAM_BIN = 0.02


class SplatError(ValueError):
    """The file is not a 3DGS PLY this pipeline can read."""


@dataclass(frozen=True)
class PlyHeader:
    path: Path
    format: str
    properties: tuple[str, ...]
    declared_vertices: int
    header_bytes: int
    extra_elements: tuple[str, ...] = ()

    @property
    def stride(self) -> int:
        return 4 * len(self.properties)

    @property
    def columns(self) -> dict[str, int]:
        return {name: i for i, name in enumerate(self.properties)}

    def core_columns(self) -> np.ndarray:
        return np.array([self.columns[name] for name in CORE_PROPERTIES], dtype=np.intp)


def read_header(path: Path) -> PlyHeader:
    """Parse and validate the header. Fails by name on an unsupported schema."""
    path = Path(path)
    if not path.exists():
        raise SplatError(f"no file at {path}")

    head = b""
    limit = 4 * 1024 * 1024
    with path.open("rb") as f:
        while b"end_header\n" not in head:
            chunk = f.read(65536)
            if not chunk:
                raise SplatError(f"{path.name}: no end_header in the first {len(head)} bytes")
            head += chunk
            if len(head) > limit:
                raise SplatError(f"{path.name}: header grows past {limit} bytes, not a PLY we can read")
    cut = head.index(b"end_header\n") + len(b"end_header\n")

    try:
        lines = head[:cut].decode("ascii").splitlines()
    except UnicodeDecodeError as exc:
        raise SplatError(f"{path.name}: header is not ASCII") from exc
    if not lines or lines[0].strip() != "ply":
        raise SplatError(f"{path.name}: first line is not 'ply'")

    fmt = ""
    properties: list[str] = []
    declared = -1
    extra: list[str] = []
    current_element = None
    for line in lines[1:]:
        parts = line.split()
        if not parts:
            continue
        keyword = parts[0]
        if keyword == "comment":
            continue
        if keyword == "format":
            if len(parts) < 3:
                raise SplatError(f"{path.name}: malformed format line {line!r}")
            fmt = f"{parts[1]} {parts[2]}"
        elif keyword == "element":
            if len(parts) != 3:
                raise SplatError(f"{path.name}: malformed element line {line!r}")
            current_element = parts[1]
            if current_element == "vertex":
                declared = int(parts[2])
            else:
                extra.append(current_element)
        elif keyword == "property":
            if len(parts) != 3:
                raise SplatError(
                    f"{path.name}: only scalar float properties are supported, got {line!r}"
                )
            kind, name = parts[1], parts[2]
            if current_element != "vertex":
                raise SplatError(
                    f"{path.name}: property {name!r} belongs to element {current_element!r}, "
                    "this loader reads one vertex element"
                )
            if kind != "float":
                raise SplatError(
                    f"{path.name}: property {name!r} is {kind}, not float; "
                    "a 3DGS export stores float32 properties"
                )
            properties.append(name)
        elif keyword in ("end_header",):
            break
        else:
            raise SplatError(f"{path.name}: unsupported header line {line!r}")

    if fmt != "binary_little_endian 1.0":
        raise SplatError(f"{path.name}: format is {fmt or 'missing'}, expected binary_little_endian 1.0")
    if extra:
        raise SplatError(
            f"{path.name}: extra elements {sorted(set(extra))}; this loader reads a single vertex element"
        )
    if declared < 0:
        raise SplatError(f"{path.name}: no element vertex line")
    missing = [name for name in CORE_PROPERTIES if name not in properties]
    if missing:
        raise SplatError(f"{path.name}: missing required properties {', '.join(missing)}")
    expected = cut + declared * 4 * len(properties)
    actual = path.stat().st_size
    if actual < expected:
        raise SplatError(
            f"{path.name}: {actual} bytes, header and vertex count need {expected}; the file is truncated"
        )
    return PlyHeader(
        path=path,
        format=fmt,
        properties=tuple(properties),
        declared_vertices=declared,
        header_bytes=cut,
        extra_elements=tuple(sorted(set(extra))),
    )


def sane_mask(rows: np.ndarray) -> np.ndarray:
    """True for a row that is a plausible gaussian rather than garbage.

    The core columns are checked for finite values and for a magnitude no
    camera-scale capture reaches. The quaternion norm is computed only for rows
    that pass that gate, so a row holding 1e26 cannot overflow the arithmetic.
    """
    core = rows[:, : len(CORE_PROPERTIES)]
    ok = np.isfinite(core).all(axis=1)
    bounded = np.zeros(rows.shape[0], dtype=bool)
    finite = np.flatnonzero(ok)
    if finite.size:
        bounded[finite] = (np.abs(core[finite]) < MAX_ABS_CORE).all(axis=1)
    ok &= bounded

    scale = rows[:, 3:6]
    ok &= (scale > SCALE_RANGE[0]).all(axis=1) & (scale < SCALE_RANGE[1]).all(axis=1)

    candidates = np.flatnonzero(ok)
    if candidates.size:
        quat = rows[candidates, 6:10].astype(np.float64)
        norm = np.linalg.norm(quat, axis=1)
        good = (norm > QUATERNION_NORM[0]) & (norm < QUATERNION_NORM[1])
        ok[candidates[~good]] = False

    dc = rows[:, 10:13]
    ok &= (dc > DC_RANGE[0]).all(axis=1) & (dc < DC_RANGE[1]).all(axis=1)
    opacity = rows[:, 13]
    ok &= (opacity > OPACITY_RANGE[0]) & (opacity < OPACITY_RANGE[1])
    return ok


def _floor_evidence(xyz: np.ndarray) -> dict:
    """Find the densest flat slab per axis, which is the floor candidate.

    A fine histogram is smoothed with a window of `SLAB_WIDTH`, and the peak of
    the smoothed curve is the slab. Returns, per axis, the slab coordinate, the
    share of points inside it, and the share on either side. The up axis is the
    axis whose slab holds the most points; the sign points into the room,
    because a floor has the room above it and mostly nothing below.
    """
    window_bins = max(1, int(round(SLAB_WIDTH / HISTOGRAM_BIN)))
    evidence: dict[str, dict] = {}
    for axis, name in enumerate(AXES):
        values = np.ascontiguousarray(xyz[:, axis], dtype=np.float64)
        lo, hi = np.percentile(values, [1.0, 99.0])
        if not np.isfinite(lo) or not np.isfinite(hi) or hi <= lo:
            evidence[name] = {"dense_extent": 0.0, "slab": None, "slab_share": 0.0}
            continue
        bins = max(window_bins + 1, int(np.ceil((hi - lo) / HISTOGRAM_BIN)))
        counts, edges = np.histogram(values, bins=bins, range=(lo, hi))
        smoothed = np.convolve(counts.astype(np.float64), np.ones(window_bins), mode="valid")
        peak = int(np.argmax(smoothed))
        start, stop = float(edges[peak]), float(edges[peak + window_bins])
        inside = (values >= start) & (values < stop)
        # The window edge is not the surface: report the median of the points it
        # holds, which is where the flat surface actually is.
        centre = float(np.median(values[inside])) if inside.any() else (start + stop) / 2.0
        half = (stop - start) / 2.0
        total = float(values.size)
        evidence[name] = {
            "dense_extent": round(float(hi - lo), 4),
            "slab": round(centre, 4),
            "slab_share": round(float(smoothed[peak] / total), 4),
            "share_above": round(float((values > centre + half).mean()), 4),
            "share_below": round(float((values < centre - half).mean()), 4),
            "slab_points": int(inside.sum()),
        }
    return evidence


def detect_up_axis(xyz: np.ndarray) -> tuple[int, int, dict]:
    """Return (axis index, sign, evidence) for the up axis.

    The floor is the densest flat surface in an indoor capture, so the up axis
    is the axis whose sharpest slab holds the most points, and the sign points
    from that slab towards the bulk of the cloud. When no axis has a slab worth
    calling a floor the detector falls back to the tightest dense extent and
    says the confidence is low. A capture that defeats the heuristic declares
    its axis with `--up`.
    """
    evidence = _floor_evidence(xyz)
    shares = {name: (evidence[name]["slab_share"] or 0.0) for name in AXES}
    ranked = sorted(AXES, key=lambda name: shares[name], reverse=True)
    best, second = ranked[0], ranked[1]
    confident = shares[best] >= 0.05 and shares[best] >= 1.35 * max(shares[second], 1e-9)

    if confident:
        chosen = best
        source = "detected from the densest flat slab"
    else:
        extents = {name: evidence[name]["dense_extent"] for name in AXES}
        chosen = min(AXES, key=lambda name: extents[name])
        source = "fallback to the narrowest dense extent, confidence low"

    slab = evidence[chosen]["slab"]
    sign = 1
    if slab is not None:
        above = float(evidence[chosen]["share_above"] or 0.0)
        below = float(evidence[chosen]["share_below"] or 0.0)
        sign = 1 if above >= below else -1
    detail = {
        "axis": chosen,
        "sign": sign,
        "source": source,
        "confident": bool(confident),
        "slab": slab,
        "per_axis": evidence,
    }
    return AXES.index(chosen), sign, detail


def load_sane_prefix(
    path: Path,
    *,
    chunk_rows: int = 200_000,
) -> tuple[np.ndarray, dict]:
    """Read the contiguous sane prefix of a splat as 15 core float32 columns.

    The supplied export declares more vertices than it fills: the tail is
    uninitialised memory. A file whose first invalid row is followed by more
    rows is treated the same way, because a writer that left a hole cannot be
    trusted after it. The count of rows not read is reported, never guessed.
    """
    header = read_header(path)
    columns = header.core_columns()
    stride = header.stride
    chunks: list[np.ndarray] = []
    read = 0
    first_invalid: int | None = None
    with path.open("rb") as f:
        f.seek(header.header_bytes)
        while read < header.declared_vertices:
            want = min(chunk_rows, header.declared_vertices - read)
            buf = f.read(want * stride)
            got = len(buf) // stride
            if got == 0:
                break
            rows = np.frombuffer(buf, dtype="<f4", count=got * len(header.properties))
            rows = rows.reshape(got, len(header.properties))
            ok = sane_mask(rows)
            if not ok.all():
                cut = int(np.argmin(ok))
                chunks.append(rows[:cut][:, columns])
                first_invalid = read + cut
                read += cut
                break
            chunks.append(rows[:, columns])
            read += got
            if got < want:
                break
    if not chunks:
        raise SplatError(f"{path.name}: no sane gaussians in the first {read} rows")
    data = np.concatenate(chunks).astype(np.float32, copy=False)
    info = {
        "declared_vertices": int(header.declared_vertices),
        "kept_vertices": int(data.shape[0]),
        "dropped_vertices": int(header.declared_vertices - data.shape[0]),
        "first_invalid_row": first_invalid,
        "rows_not_read": int(header.declared_vertices - read),
        "properties": list(header.properties),
        "header_bytes": int(header.header_bytes),
        "stride_bytes": int(stride),
    }
    return data, info


def derive_gaussians(core: np.ndarray) -> dict[str, np.ndarray]:
    """Turn the core columns into what a renderer needs.

    Position, colour, per-axis size, opacity and orientation. The quaternion is
    stored as (w, x, y, z) by property name, not in file order, and is
    normalised: the rotation is what turns three per-axis sizes into the
    anisotropic gaussian a splat renderer draws. The higher order spherical
    harmonics are not carried; the DC term is the view-independent colour.
    """
    xyz = np.ascontiguousarray(core[:, 0:3], dtype=np.float32)
    scale = core[:, 3:6].astype(np.float32)
    quaternion = core[:, 6:10].astype(np.float64)
    dc = core[:, 10:13].astype(np.float32)
    opacity = core[:, 13].astype(np.float32)
    norm = np.linalg.norm(quaternion, axis=1, keepdims=True)
    rot = (quaternion / np.maximum(norm, 1e-9)).astype(np.float32)
    rgb = np.clip(0.5 + SH_DC * dc, 0.0, 1.0)
    alpha = 1.0 / (1.0 + np.exp(-np.clip(opacity, -30.0, 30.0)))
    size = np.exp(np.clip(scale, SCALE_RANGE[0], SCALE_RANGE[1]))
    return {
        "xyz": xyz,
        "rot": rot,
        "rgb": np.rint(rgb * 255.0).astype(np.uint8),
        "size": size.astype(np.float32),
        "alpha": alpha.astype(np.float32),
    }


def decimate(n: int, budget: int, seed: int = 0) -> np.ndarray:
    """Return sorted indices of a uniform random subset, deterministic per seed."""
    if budget <= 0 or budget >= n:
        return np.arange(n)
    rng = np.random.default_rng(seed)
    return np.sort(rng.choice(n, size=budget, replace=False))


def _sha256(path: Path, chunk: int = 8 * 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            block = f.read(chunk)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def ingest(
    ply: Path,
    out: Path,
    *,
    budget: int = DEFAULT_BUDGET,
    up: str | None = None,
    seed: int = 0,
    hash_source: bool = True,
) -> dict:
    """Run the ingest stage and write `scene.npz`. Returns the metadata."""
    started = time.perf_counter()
    ply = Path(ply)
    out = Path(out)
    core, counts = load_sane_prefix(ply)
    gaussians = derive_gaussians(core)
    total = gaussians["xyz"].shape[0]

    if up is None:
        axis, sign, up_detail = detect_up_axis(gaussians["xyz"])
        up_source = up_detail["source"]
    else:
        parsed = str(up).strip().lower()
        sign = -1 if parsed.startswith("-") else 1
        name = parsed.lstrip("+-")
        if name not in AXES:
            raise SplatError(f"--up {up!r} is not one of x, y, z, +x, -x, +y, -y, +z, -z")
        axis = AXES.index(name)
        up_detail = {"axis": name, "sign": sign, "source": "declared on the command line", "confident": True}
        up_source = up_detail["source"]

    picked = decimate(total, budget, seed=seed)
    arrays = {name: value[picked] for name, value in gaussians.items()}
    xyz = gaussians["xyz"]

    elapsed = time.perf_counter() - started
    meta = {
        "artifact": "scene",
        "version": SCENE_VERSION,
        "source": {
            "file": ply.name,
            "path": str(ply),
            "bytes": ply.stat().st_size,
            "sha256": _sha256(ply) if hash_source else None,
            "properties": counts["properties"],
            "declared_vertices": counts["declared_vertices"],
            "sane_prefix": counts["kept_vertices"],
            "dropped_vertices": counts["dropped_vertices"],
            "first_invalid_row": counts["first_invalid_row"],
            "rows_not_read": counts["rows_not_read"],
        },
        "frame": {
            "up_axis": ("-" if sign < 0 else "+") + AXES[axis],
            "up_axis_index": axis,
            "up_axis_sign": sign,
            "up_axis_source": up_source,
            "up_axis_evidence": up_detail,
            "units": "file units, treated as metres pending the scale check in objects.json",
        },
        "counts": {
            "declared": counts["declared_vertices"],
            "sane": counts["kept_vertices"],
            "rendered": int(arrays["xyz"].shape[0]),
            "budget": int(budget),
            "dropped": counts["dropped_vertices"],
        },
        "bounds": {
            "min": [round(float(v), 4) for v in xyz.min(axis=0)],
            "max": [round(float(v), 4) for v in xyz.max(axis=0)],
            "p1": [round(float(v), 4) for v in np.percentile(xyz, 1.0, axis=0)],
            "p99": [round(float(v), 4) for v in np.percentile(xyz, 99.0, axis=0)],
        },
        "gaussians": {
            "median_size": [round(float(v), 5) for v in np.median(gaussians["size"], axis=0)],
            "alpha_median": round(float(np.median(gaussians["alpha"])), 4),
            "alpha_p95": round(float(np.percentile(gaussians["alpha"], 95.0)), 4),
            "rotation": "unit quaternion per gaussian as (w, x, y, z), a splat's orientation",
            "colour": "view-independent DC term only; the higher order harmonics are not carried",
        },
        "render": {
            "decimation": "uniform random subset, sorted original order",
            "seed": int(seed),
        },
        "timing_s": round(elapsed, 3),
    }

    out.parent.mkdir(parents=True, exist_ok=True)
    np.savez(
        out,
        xyz=arrays["xyz"].astype(np.float32, copy=False),
        rot=arrays["rot"].astype(np.float32, copy=False),
        rgb=arrays["rgb"].astype(np.uint8, copy=False),
        size=arrays["size"].astype(np.float32, copy=False),
        alpha=arrays["alpha"].astype(np.float32, copy=False),
        meta=np.array(json.dumps(meta, sort_keys=True)),
    )
    meta["artifacts"] = {"scene_npz": str(out), "bytes": out.stat().st_size}
    return meta


@dataclass
class Scene:
    """One loaded scene artifact.

    `rot` is optional only so a version 1 artifact still loads; every artifact
    written by this stage carries it.
    """

    xyz: np.ndarray
    rgb: np.ndarray
    size: np.ndarray
    alpha: np.ndarray
    meta: dict = field(default_factory=dict)
    rot: np.ndarray | None = None

    @property
    def up_index(self) -> int:
        return int(self.meta["frame"]["up_axis_index"])

    @property
    def up_sign(self) -> int:
        return int(self.meta["frame"]["up_axis_sign"])

    def height(self) -> np.ndarray:
        """Coordinate along the up axis, measured upwards from the frame origin."""
        return self.up_sign * self.xyz[:, self.up_index]


def load_scene(path: Path) -> Scene:
    """Load and validate `scene.npz`."""
    path = Path(path)
    if not path.exists():
        raise SplatError(f"no scene artifact at {path}; run `make scene` first")
    with np.load(path) as data:
        keys = set(data.files)
        missing = {"xyz", "rgb", "size", "alpha", "meta"} - keys
        if missing:
            raise SplatError(f"{path.name}: missing arrays {', '.join(sorted(missing))}")
        xyz = np.array(data["xyz"], dtype=np.float64)
        rgb = np.array(data["rgb"], dtype=np.uint8)
        size = np.array(data["size"], dtype=np.float32)
        alpha = np.array(data["alpha"], dtype=np.float32)
        rot = np.array(data["rot"], dtype=np.float32) if "rot" in keys else None
        meta = json.loads(str(np.asarray(data["meta"]).item()))
    if xyz.ndim != 2 or xyz.shape[1] != 3:
        raise SplatError(f"{path.name}: xyz has shape {xyz.shape}, expected (n, 3)")
    if rgb.shape != xyz.shape or size.shape != xyz.shape or alpha.shape[:1] != xyz.shape[:1]:
        raise SplatError(f"{path.name}: array shapes disagree, {xyz.shape} against {rgb.shape}")
    if not np.isfinite(xyz).all():
        raise SplatError(f"{path.name}: non-finite coordinates reached the artifact")
    if rot is not None and rot.shape != (xyz.shape[0], 4):
        raise SplatError(f"{path.name}: rot has shape {rot.shape}, expected ({xyz.shape[0]}, 4)")
    return Scene(xyz=xyz, rgb=rgb, size=size, alpha=alpha, meta=meta, rot=rot)


def format_report(meta: dict) -> str:
    """Human readable summary of an ingest run, printed by `make scene`."""
    source = meta["source"]
    counts = meta["counts"]
    frame = meta["frame"]
    bounds = meta["bounds"]
    gaussians = meta["gaussians"]
    evidence = frame.get("up_axis_evidence", {})
    slab = evidence.get("slab")
    slab_note = f", floor slab at {slab:+.3f}, {evidence.get('per_axis', {}).get(evidence.get('axis'), {}).get('slab_share', 0):.1%} of points" if slab is not None else ""
    lines = [
        f"file              {source['file']} ({source['bytes']:,} bytes)",
        f"declared vertices {source['declared_vertices']:,}",
        f"sane prefix       {source['sane_prefix']:,}",
        f"dropped rows      {source['dropped_vertices']:,}"
        + (f", first invalid at row {source['first_invalid_row']:,}" if source["first_invalid_row"] is not None else ""),
        f"rendered          {counts['rendered']:,} (budget {counts['budget']:,})",
        f"up axis           {frame['up_axis']} ({frame['up_axis_source']}{slab_note})",
        f"bounds p1..p99    x {bounds['p1'][0]:+.2f}..{bounds['p99'][0]:+.2f}  "
        f"y {bounds['p1'][1]:+.2f}..{bounds['p99'][1]:+.2f}  "
        f"z {bounds['p1'][2]:+.2f}..{bounds['p99'][2]:+.2f}",
        f"median gaussian   {gaussians['median_size'][0] * 1000:.1f} mm",
        f"alpha median      {gaussians['alpha_median']:.3f}",
        f"ingest            {meta['timing_s']:.2f} s",
    ]
    if "artifacts" in meta:
        lines.append(f"wrote             {meta['artifacts']['scene_npz']} ({meta['artifacts']['bytes']:,} bytes)")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m plantpilot.splat",
        description="Ingest a 3D Gaussian splatting PLY into data/scene/scene.npz.",
    )
    parser.add_argument("--ply", required=True, type=Path, help="the delivered .ply")
    parser.add_argument("--out", default=Path("data/scene/scene.npz"), type=Path)
    parser.add_argument(
        "--budget",
        default=DEFAULT_BUDGET,
        type=int,
        help=f"maximum gaussians kept for rendering (default {DEFAULT_BUDGET:,}); 0 keeps all",
    )
    parser.add_argument(
        "--up",
        default=None,
        help="declare the up axis as x, y or z, with an optional sign, instead of detecting it",
    )
    parser.add_argument("--seed", default=0, type=int, help="decimation seed")
    parser.add_argument("--no-hash", action="store_true", help="skip hashing the source file")
    parser.add_argument("--json", action="store_true", help="print the metadata as JSON")
    args = parser.parse_args(argv)

    try:
        meta = ingest(
            args.ply,
            args.out,
            budget=args.budget,
            up=args.up,
            seed=args.seed,
            hash_source=not args.no_hash,
        )
    except SplatError as exc:
        print(f"ingest failed: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(meta, indent=2, sort_keys=True))
    else:
        print(format_report(meta))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
