# Scene pipeline: raw splat to geometry and semantics

Status: proposed contract for the static scene pipeline, 2026-11-06. Read this
with [roadmap.md](roadmap.md).

This document defines the module layout, stages and files that replace the
FastAPI scene service. The pipeline is an offline Python package. The only
runtime consumer is the Three.js client.

## 1. Goals

1. Read the supplied Gaussian splat PLY without crashing on its invalid tail.
2. Produce a clean scene representation that Three.js can load.
3. Produce oriented boxes for industrial assets and obstacles.
4. Map the workbook's 30 asset records to scene objects where possible.
5. Produce a walkable grid that the client can use for A*.
6. Make every output deterministic and inspectable.
7. Fail loudly when the input schema or the scene frame is wrong.

## 2. Non-goals

- No HTTP API in the pipeline.
- No database.
- No OCR, PDF corpus or printed tags.
- No physics or robot dynamics.
- No live sensor data.
- No attempt to make the visual mesh watertight for navigation. Navigation uses
  the occupancy grid.

## 3. Package layout

Proposed layout, created by the implementation PRs:

```
pipeline/
  pyproject.toml
  README.md
  configs/
    default.toml
  src/scene_pipeline/
    __init__.py
    cli.py                 command line and stage orchestration
    config.py              typed configuration and paths
    io/
      ply.py               header parsing, schema validation, sane-prefix read
      artifacts.py         read and write versioned JSON artifacts
    clean/
      filter.py            finite checks, opacity and scale filters, outliers
      frame.py             up axis, floor plane, scale check, bounds
    geometry/
      voxel.py             downsampling and voxel hashing
      mesh.py              surface reconstruction
      decimate.py          simplification and LOD selection
    segment/
      floor.py             floor and dominant plane removal
      cluster.py           connected components and oversized split
      obb.py               oriented boxes and object features
    classify/
      features.py          size, aspect, height, planarity, colour features
      rules.py             asset and obstacle proposals
      assets.py            workbook parsing and one-to-one mapping
    nav/
      occupancy.py         floor grid, height band, inflation
      route.py             stand-off point selection and validation helpers
    export/
      glb.py               GLB write, compression, budget check
      json.py              schema write and validation
  tests/
    fixtures/
      tiny.ply
      tiny.xlsx
      expected/
```

The package is a separate uv project. It does not import `plantpilot` at
runtime. Code from the old `app/server/src/plantpilot/splat.py` and
`app/server/src/plantpilot/segment.py` can be copied and simplified, not
imported.

## 4. Pipeline stages

### 4.1 Ingest

Command:

```
uv run --project pipeline scene-pipeline ingest \
  --ply "data/supplied/Industrial Boiler Room.ply" \
  --out data/derived
```

Input: a PLY with the standard 3DGS properties:

- `x, y, z`;
- `scale_0..2` (log scale);
- `rot_0..3` (quaternion, stored x, y, z, w in this file);
- `f_dc_0..2` (SH DC colour);
- `opacity` (logit);
- optional `f_rest_0..44`.

Output: `scene.points.npz` with `xyz`, `rgb`, `size`, `alpha`, `rot`, plus
source metadata.

Rules:

- Read the header and validate the property list. A missing or extra property
  that changes the layout is a hard error.
- Read the vertex count from the header, not from the file size.
- Keep the first contiguous sane run. A row is sane when all coordinates, scale,
  rotation and opacity are finite and the coordinate magnitude is below a
  configurable limit.
- Convert colour with `rgb = 0.5 + 0.28209479177387814 * f_dc`, clipped to
  `[0, 1]`.
- Convert scale with `exp(scale)` and opacity with `sigmoid(opacity)`.
- Record declared, sane, dropped and first-invalid counts.

The supplied file declares 1,506,136 vertices and fills 502,483 sane rows. The
rest is uninitialised memory. That fact belongs in the manifest so a future
reader does not think the pipeline silently discarded good data.

### 4.2 Clean

Output: `scene.clean.ply` and `scene.frame.json`.

Rules:

- Drop non-finite rows and rows outside the robust bounding box.
- Drop gaussians with very low opacity or implausible scale.
- Remove disconnected floaters with a statistical or radius outlier pass.
- Detect the up axis from the densest planar slab. Record the evidence.
- Fit the floor plane. Record point, normal and signed floor height.
- Check the scale against a known dimension when one is available. The supplied
  scene has no scale reference, so the manifest must say `units: assumed_m` or
  `units: m` and why.
- Transform to a documented frame. The preferred frame is Y up, metres, origin
  at the floor centre or the scene bounds centre. The original splat frame is
  kept in the manifest.

### 4.3 Geometry

There are two possible outputs. The manifest names which one is active.

**Primary: mesh**

- Build a mesh from the cleaned point cloud with screened Poisson reconstruction
  or a surface-aligned splat method.
- Transfer vertex colour from the splat.
- Decimate to the triangle budget.
- Write `scene.glb` with meshopt or Draco compression.
- Target: under 40 MB and under 3 seconds to first render from local disk.

**Fallback: point or splat layer**

- Write `scene.points.bin` with positions, colour and size, or a compressed
  splat format supported by the chosen Three.js loader.
- This is a visual layer only. Navigation still uses `nav.json`.

The geometry stage does not invent surfaces that are not supported by the
capture. If the mesh is visibly worse than the point layer, ship the point layer
and say so in the manifest. A trusted point cloud is better than a broken mesh.

### 4.4 Segment

Output: `scene.objects.raw.json`.

Rules:

- Remove the floor plane and dominant wall, ceiling and pipe-rack planes.
- Voxelise the remainder. The voxel size starts at 3 cm and is raised to at
  least 1.4 times the measured point spacing.
- Build connected components in the voxel grid.
- Split every oversized component with k-means or a patch split. A room-sized
  component is a failure, not an object.
- Fit an oriented box per component. Use the 2nd to 98th percentile of the
  points along each axis so one stray gaussian does not define the box.
- Record point count, centre, axes, extents, height above floor, volume,
  planarity and a class proposal.

### 4.5 Classify

Output: class proposals in `scene.objects.raw.json`.

Two layers:

1. **Asset proposals.** A candidate can be an asset if its size, aspect ratio,
   height above floor and context fit one of the five workbook classes. The
   proposal includes a confidence and a reason.
2. **Obstacle proposals.** Every other component in the robot height band is an
   obstacle. The class is coarse: wall, column, beam, pipe, duct, tank, boiler,
   drum, cabinet, pallet, railing, stair, equipment, clutter or unknown.

The classifier is rule-based first. A vision-language model can add a second
opinion later, but it cannot be the only path. The demo must run offline and
deterministically.

The class label is a proposal. The UI shows the confidence. Navigation does not
depend on the label; every obstacle box blocks.

### 4.6 Map assets

Input: `builder_pack.xlsx` and `scene.objects.raw.json`.

Output: `assets.json` and `mapping.json`.

Rules:

- Read the `Asset_Master` and `Scene_Anchors` sheets. The anchors are
  placeholders from the synthetic pack and must not be used as scene positions.
- The workbook has 30 records in five classes: control valve (12), process pump
  (6), electric motor (6), pressure transmitter (3), vibration sensor (3).
- Assign at most one object per record and one record per object.
- Prefer the same class proposal, then size and height similarity, then
  proximity to pipe runs. Record the score, the method and the confidence.
- Mark records with no candidate as `unmapped`. Mark objects with no record as
  `extra`.
- P-005 (`ASSET-017`, process pump, fouling, health 44) is the demo target. It
  must map to a reachable pump-like object. If it cannot, the run fails and says
  why.

The workbook remains the authority for asset metadata. The pipeline copies the
fields the client needs: id, tag, class, area, criticality, health, condition,
issue and recommended check.

### 4.7 Navigation

Output: `nav.json`.

Rules:

- Use the floor plane and the cleaned point cloud.
- Grid cell size: 10 cm by default.
- Mark a cell blocked when it contains points between `floor + 0.10 m` and
  `floor + robot_height_m`.
- Inflate blocked cells by `robot_radius_m + safety_margin_m`.
- Keep the grid origin and dimensions in the file.
- Choose the start point from the largest free region near the entrance, or use
  an explicit override.
- For each asset, propose a stand-off point outside its box with at least the
  robot radius of clearance. Prefer the side facing the start.
- Store the grid as a compact bitset or run-length block, not as a large JSON
  array of booleans.

The client computes A* on this grid. The pipeline does not need to know the
current target.

### 4.8 Export

Output: `scene.manifest.json` plus published copies in
`app/web/public/scene/`.

Rules:

- Validate every artifact against its schema version.
- Verify that every artifact named in the manifest exists and has a hash.
- Verify that the scene frame, floor and units agree across artifacts.
- Verify that every asset reference points to an object that exists.
- Copy the manifest and artifacts into the web public directory only after all
  checks pass.
- Never publish a partial artifact set.

## 5. Artifact contracts

### 5.1 `scene.manifest.json`

```json
{
  "version": 1,
  "generated_at": "2026-11-06T21:00:00Z",
  "source": {
    "ply": "Industrial Boiler Room (1).ply",
    "sha256": "...",
    "declared_vertices": 1506136,
    "sane_vertices": 502483,
    "first_invalid_row": 502483
  },
  "frame": {
    "up": "+y",
    "units": "assumed_m",
    "origin": [0, 0, 0],
    "bounds": { "min": [-6.08, -4.47, -7.56], "max": [5.99, 3.91, -0.74] }
  },
  "floor": {
    "normal": [0.018, 0.9998, -0.0098],
    "point": [0, -0.844, 0],
    "height_m": -0.844,
    "rms_m": 0.02
  },
  "artifacts": {
    "geometry": { "path": "scene.glb", "kind": "mesh", "bytes": 0 },
    "objects": { "path": "objects.json", "bytes": 0 },
    "assets": { "path": "assets.json", "bytes": 0 },
    "obstacles": { "path": "obstacles.json", "bytes": 0 },
    "nav": { "path": "nav.json", "bytes": 0 }
  },
  "parameters": {
    "voxel_m": 0.03,
    "robot_radius_m": 0.45,
    "robot_height_m": 1.6,
    "standoff_m": 0.9
  },
  "timings_s": {
    "ingest": 0.0,
    "clean": 0.0,
    "geometry": 0.0,
    "segment": 0.0,
    "classify": 0.0,
    "nav": 0.0
  }
}
```

### 5.2 `objects.json`

One array of framed objects. `kind` is `asset`, `obstacle` or `structure`.

```json
{
  "version": 1,
  "objects": [
    {
      "id": "OBJ-0001",
      "kind": "asset",
      "class": "PROCESS_PUMP",
      "asset_id": "ASSET-017",
      "tag": "P-005",
      "obb": {
        "center": [10.4, 0.7, 2.3],
        "axes": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
        "extents": [1.8, 1.2, 1.35]
      },
      "points": 1840,
      "height_above_floor_m": 0.7,
      "confidence": 0.82,
      "class_reason": "floor-standing, pump-sized, attached to a pipe run"
    }
  ]
}
```

`axes` are unit vectors. `extents` are full lengths, not half lengths. The eight
corners are `center +/- sum(extents[i] / 2 * axes[i])`.

### 5.3 `assets.json`

The workbook records plus mapping state:

```json
{
  "version": 1,
  "assets": [
    {
      "asset_id": "ASSET-017",
      "tag": "P-005",
      "class": "PROCESS_PUMP",
      "area": "Utility Island",
      "criticality": "A - production critical",
      "health": 44,
      "condition": "attention_required",
      "issue": "FOULING",
      "recommended_check": "inspect hydraulic path",
      "object_id": "OBJ-0001",
      "mapping": "provisional",
      "confidence": 0.82
    }
  ]
}
```

### 5.4 `obstacles.json`

A filtered view of the obstacle objects:

```json
{
  "version": 1,
  "obstacles": [
    {
      "id": "OBJ-0042",
      "class": "pipe",
      "obb": {
        "center": [4.2, 1.1, 3.4],
        "axes": [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
        "extents": [3.2, 0.2, 0.2]
      },
      "blocks_route": true,
      "confidence": 0.7
    }
  ]
}
```

### 5.5 `nav.json`

```json
{
  "version": 1,
  "frame": { "up": "+y", "cell_m": 0.1 },
  "grid": {
    "origin": [-6.0, -7.5],
    "cols": 120,
    "rows": 76,
    "encoding": "bitset-base64",
    "blocked": "..."
  },
  "robot": { "radius_m": 0.45, "height_m": 1.6 },
  "start": [1.4, 4.5],
  "standoff": {
    "P-005": [8.8, 2.7]
  }
}
```

The client decodes `blocked` once, then runs A* from the start to the selected
stand-off point.

## 6. Configuration

`pipeline/configs/default.toml` owns every threshold:

```toml
[voxel]
size_m = 0.03
spacing_factor = 1.4

[clean]
max_coordinate_m = 100.0
min_opacity = 0.02
max_scale_m = 0.5

[segment]
plane_distance_m = 0.04
max_planes = 8
max_object_points = 20000

[classify]
asset_min_height_m = 0.15
asset_max_height_m = 2.0

[nav]
cell_m = 0.10
robot_radius_m = 0.45
robot_height_m = 1.60
safety_margin_m = 0.10
standoff_m = 0.90

[export]
max_glb_mb = 40
```

No room-specific constant belongs in code. The supplied room may have its own
config file, but the default pipeline must run on another compatible capture.

## 7. Commands and Make targets

Proposed targets:

```
make pipeline-ingest     # raw PLY -> clean points and manifest
make pipeline-geometry   # clean points -> scene.glb or fallback
make pipeline-objects    # clean points -> objects.json
make pipeline-assets     # workbook + objects -> assets.json
make pipeline-nav        # clean points + obstacles -> nav.json
make pipeline            # all of the above, then publish
make pipeline-test       # offline pipeline tests
make web-build           # pnpm build
make demo                # static preview of app/web/dist
```

`make demo` must not start Python. The built client is the demo.

## 8. Validation and tests

Offline, deterministic tests:

- PLY header parsing rejects a wrong schema.
- The supplied-file fixture keeps exactly the sane prefix and reports the
  first-invalid row.
- A tiny synthetic PLY produces a known floor, known boxes and a known asset
  mapping.
- A second tiny scene with a different up axis proves the frame is not
  hard-coded.
- A route test proves the client grid blocks an obstacle and finds a detour.
- Artifact schema tests reject a missing field, a dangling asset id and a
  mismatched frame.

Property tests or golden tests:

- Two runs on the same fixture produce identical ids, boxes and counts.
- The published manifest hashes match the files.
- No artifact contains NaN or infinite coordinates.

## 9. Migration from the old server

1. Inventory reusable logic:
   - `app/server/src/plantpilot/splat.py` for PLY parsing;
   - `app/server/src/plantpilot/segment.py` for plane removal and clustering;
   - `app/server/src/plantpilot/nav.py` for grid and A* ideas;
   - the old client-side pathfinding experiment, replaced by the server route.
2. Copy logic into `pipeline/`, not import it. The old server will be deleted.
3. Replace the client's mock fixtures with published artifacts.
4. Replace the API fetch layer with static loads.
5. Delete `app/server/`, the Vite `/api` proxy, the mission view and the plate
   scan from the demo path.
6. Rewrite the README, acceptance and demo docs after the static path works.

Do not delete the old server until phase 5 passes: the robot walks to P-005 on
the static path, offline, from a clean build.

## 10. Failure policy

A pipeline run fails when:

- the PLY schema is not the standard 3DGS layout;
- no sane prefix exists;
- the floor cannot be fitted with enough inliers;
- the geometry export exceeds the budget and no fallback is configured;
- an asset id is dangling;
- P-005 has no candidate object or no reachable stand-off point;
- the published artifact set is incomplete.

A failed run must not publish. A partial scene is worse than a loud error
because the client would render a plausible but wrong plant.
