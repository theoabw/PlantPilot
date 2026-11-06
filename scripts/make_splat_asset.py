"""Write the sanitised capture as a compact PLY for the browser splat viewer.

The delivered file is not what a browser should read: it declares more vertices
than it fills and the tail is uninitialised memory. This stage keeps the sane
prefix and writes only the properties a gaussian splat renderer needs (position,
per-axis scale, rotation, DC colour, opacity), which is about four times smaller
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
DELIVERED = ROOT / "data" / "supplied" / "Industrial Boiler Room (1).ply"
OUT = ROOT / "data" / "viewer" / "room.ply"


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


def build(ply: Path, out: Path) -> dict:
    rows, info = load_sane_prefix(Path(ply))
    info = write_ply(rows, out)
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
        raise SystemExit(f"no capture at {args.ply}; put the delivered .ply in data/supplied/")
    info = build(Path(args.ply), Path(args.out))
    print(json.dumps(info, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
