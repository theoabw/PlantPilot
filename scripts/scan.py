"""Turn a photo into a metric, bounded point cloud.

    uv run python scripts/scan.py data/capture/room.jpg

Writes data/capture/<stem>.npz (points, colours, meta) and prints the counts.
The ArUco marker on the printed plate supplies the metre scale; without one the
scale is assumed and the meta says so.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app" / "server" / "src"))

from plantpilot import capture  # noqa: E402

MODEL = ROOT / "data" / "models" / "depth_anything_v2_small_q.onnx"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("photo", type=Path)
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--marker-mm", type=float, default=100.0)
    parser.add_argument("--voxel", type=float, default=0.02)
    args = parser.parse_args()

    if not MODEL.exists():
        print(f"missing model {MODEL}", file=sys.stderr)
        print("fetch it with: make models", file=sys.stderr)
        raise SystemExit(1)

    started = time.perf_counter()
    scan = capture.scan_photo(args.photo, MODEL, args.marker_mm / 1000.0, args.voxel)
    out = args.out or (ROOT / "data" / "capture" / f"{args.photo.stem}.npz")
    out = out if Path(out).is_absolute() else Path.cwd() / out
    capture.save(scan, out)
    print(json.dumps(scan.meta, indent=2))
    print(f"wrote {out} in {time.perf_counter() - started:.2f} s")


if __name__ == "__main__":
    main()
