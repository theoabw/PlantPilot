"""Write the sanitised capture as a compact PLY for the browser splat viewer.

The supplied export carries the full 3DGS property set. A browser needs only the
core properties, so this stage keeps the sane prefix and writes position,
per-axis scale, rotation, DC colour and opacity. That is about four times smaller
than the full 59 property export and loads far faster in the viewer.

Output is a local asset under `data/`, never committed.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from plantpilot.splat import CORE_PROPERTIES, load_sane_prefix

ROOT = Path(__file__).resolve().parents[1]
DELIVERED = ROOT / "data" / "supplied" / "Equipment Room.ply"
OUT = ROOT / "data" / "viewer" / "equipment.ply"


def write_ply(rows: np.ndarray, out: Path) -> dict:
    """Write core-property rows as a binary little endian PLY."""
    out.parent.mkdir(parents=True, exist_ok=True)
    header = "\n".join([
        "ply",
        "format binary_little_endian 1.0",
        "comment gaussian splats for the browser viewer, sanitised by scripts/make_splat_asset.py",
        f"element vertex {rows.shape[0]}",
        *[f"property float {name}" for name in CORE_PROPERTIES],
        "end_header",
        "",
    ]).encode("ascii")
    with out.open("wb") as handle:
        handle.write(header)
        handle.write(rows.astype(np.float32).tobytes())
    return {
        "path": str(out.relative_to(ROOT)) if out.is_relative_to(ROOT) else str(out),
        "vertices": int(rows.shape[0]),
        "properties": list(CORE_PROPERTIES),
        "bytes": out.stat().st_size,
    }


# The CPU preview renderer culls the metre-wide fog gaussians a capture carries,
# because they cover whole image regions and wash the picture out. The browser
# renderer has no such cull, so the viewer asset drops them here instead.
FOG_MEAN_SIZE_M = 0.12
FOG_ALPHA_MIN = 0.03


def cull_fog(rows: np.ndarray, max_mean_size: float = FOG_MEAN_SIZE_M,
             alpha_min: float = FOG_ALPHA_MIN) -> tuple[np.ndarray, int]:
    """Drop gaussians that are large and faint, the capture's fog."""
    scale = np.exp(rows[:, 3:6].astype(np.float64))
    mean_size = scale.mean(axis=1)
    alpha = 1.0 / (1.0 + np.exp(-rows[:, 13].astype(np.float64)))
    keep = (mean_size < max_mean_size) & (alpha > alpha_min)
    return rows[keep], int((~keep).sum())


def build(ply: Path, out: Path) -> dict:
    rows, info = load_sane_prefix(Path(ply))
    kept, dropped = cull_fog(rows)
    info = write_ply(kept, out)
    info["fog_culled"] = dropped
    info["source_rows"] = int(rows.shape[0])
    info["source"] = str(ply)
    info["source_declared"] = int(load_info(ply))
    return info


def load_info(ply: Path) -> int:
    from plantpilot.splat import read_header

    return read_header(Path(ply)).declared_vertices


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python scripts/make_splat_asset.py",
        description="Write the sanitised capture as a core-property PLY for the web viewer.",
    )
    parser.add_argument("--ply", default=DELIVERED, type=Path)
    parser.add_argument("--out", default=OUT, type=Path)
    args = parser.parse_args(argv)

    if not Path(args.ply).exists():
        raise SystemExit(f"no capture at {args.ply}; put the supplied .ply in data/supplied/")
    info = build(Path(args.ply), Path(args.out))
    print(json.dumps(info, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
