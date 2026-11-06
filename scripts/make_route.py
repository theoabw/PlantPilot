"""Generate route.json from scene, objects and mapped assets.

Usage:
    python scripts/make_route.py [--scene path] [--objects path] [--mapped path] [--target P-005] [--output path]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Add app/server/src to sys.path so plantpilot is importable
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app" / "server" / "src"))

from plantpilot import nav


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate PlantPilot navigation route and proximity analysis.")
    parser.add_argument("--scene", type=Path, default=ROOT / "data" / "scene" / "scene.npz",
                        help="Path to filtered point cloud scene.npz")
    parser.add_argument("--objects", type=Path, default=ROOT / "data" / "scene" / "objects.json",
                        help="Path to extracted objects.json")
    parser.add_argument("--mapped", type=Path, default=ROOT / "data" / "scene" / "mapped.json",
                        help="Path to mapped records mapped.json")
    parser.add_argument("--target", type=str, default="P-005",
                        help="Target asset ID to inspect")
    parser.add_argument("--output", type=Path, default=ROOT / "data" / "scene" / "route.json",
                        help="Destination route.json path")
    parser.add_argument("--floor-y", type=float, default=None,
                        help="Manual floor height override in metres")
    parser.add_argument("--agent-radius", type=float, default=0.20,
                        help="Agent radius in metres for inflation. 0.20 is the demo robot's "
                             "half width; a person would be 0.35")
    args = parser.parse_args()

    print(f"Generating route for target {args.target}...")
    result = nav.build_route(
        scene_path=args.scene,
        objects_path=args.objects,
        mapped_path=args.mapped,
        target_asset_id=args.target,
        output_path=args.output,
        manual_floor_y=args.floor_y,
        agent_radius_m=args.agent_radius,
    )

    if not result["reachable"]:
        print(f"FAILED: Route unreachable: {result.get('reason')}")
        return 1

    print(f"SUCCESS: Route generated to {result['target_asset_id']}")
    print(f"  Floor height:    {result['floor_height_m']} m (up-axis: {result['up_axis']})")
    print(f"  Start:           {result['start']}")
    print(f"  Target waypoint: {result['target_waypoint']}")
    print(f"  Route distance:  {result['distance_m']} m")
    print(f"  Min clearance:   {result['clearance_m']} m")
    print(f"  A* computation:  {result['astar_ms']} ms")
    print(f"  Path points:     {len(result['path'])} (3D)")
    print(f"  Proximity points:{len(result['path_samples'])} samples along path")
    print(f"  Saved to:        {args.output}")

    # Acceptance Check 4 verification:
    if result["distance_m"] < 2.0:
        print("  WARNING: Route distance is under 2.0 m (Acceptance Check 4 expects > 2 m)")
    if result["clearance_m"] < 0.30:
        print("  WARNING: Route clearance is under 0.30 m (Acceptance Check 4 expects >= 0.30 m)")
    if result["astar_ms"] > 500.0:
        print("  WARNING: A* took > 500 ms (Acceptance Check 4 expects < 500 ms)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
