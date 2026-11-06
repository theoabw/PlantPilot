# Revised roadmap: static scene pipeline and Three.js client

Status: proposal, 2026-11-06. Branch: `revised-roadmap`. This branch changes
documentation only.

This roadmap replaces the FastAPI-based plan. The product becomes an offline
scene pipeline plus a Three.js client that loads generated scene geometry and
semantic data directly. There is no HTTP service on the demo path.

The detailed artifact and module contract is in
[scene-pipeline.md](scene-pipeline.md).

## 1. Decision

1. Remove the FastAPI service from the demo path.
2. Put all analysis in a standalone Python package under `pipeline/`.
3. Convert the supplied Gaussian splat PLY into geometry that Three.js can load.
4. Segment the scene into walkable floor, industrial assets and obstacles.
5. Publish static artifacts for the client: geometry, object boxes, obstacle
   boxes and an occupancy grid.
6. Let the client plan the robot route and animate the robot from a start point
   to a selected asset, avoiding the marked obstacles.
7. Keep the runtime offline: no API, no database, no network request.

## 2. Why this replaces the backend

The current FastAPI service carries OCR, corpus search, a synthetic plant,
capture code and a scene API. Most of that is outside the new challenge. The
parts that matter are geometry, semantics and navigation.

A runtime service also adds failure modes that do not help the demo:

- the demo needs two processes and a proxy;
- the front end depends on API shapes that change while the scene work changes;
- the service hides whether an artifact is reproducible;
- the supplied scene is static, so the data does not need a live server.

Static artifacts are simpler to inspect, diff, test and serve. The pipeline is
the product. The client is a viewer plus a route planner.

## 3. Target architecture

```
data/supplied/
  Industrial Boiler Room.ply
  builder_pack.xlsx
        |
        v
pipeline/  (offline Python, uv)
  ingest -> clean -> geometry -> segment -> classify -> map -> nav -> export
        |
        v
data/derived/
  scene.manifest.json
  scene.glb
  scene.points.bin
  objects.json
  assets.json
  obstacles.json
  nav.json
        |
        v
app/web/public/scene/  (published copies, gitignored)
        |
        v
app/web/  (React + three.js, no API)
  load geometry, objects, obstacles and grid
  plan A* route in the browser
  animate the robot and show nearby assets
```

The pipeline is the only place that reads the raw PLY and the workbook. The
client is the only place that renders and plans a route. The boundary is a
small set of files with versioned schemas.

## 4. Scope

### In scope

- PLY parsing and validation for the standard 3D Gaussian Splatting schema.
- Filtering of invalid rows and floaters.
- Conversion to a Three.js-loadable scene representation.
- Floor and wall detection.
- Object clustering and oriented boxes.
- Asset and obstacle classification.
- One-to-one mapping of Excel asset records to scene objects where a match
  exists.
- Occupancy grid and stand-off points.
- Client-side A*, robot animation, proximity display and asset panels.
- A reproducible command from raw files to published artifacts.

### Out of scope

- FastAPI, HTTP APIs and API clients.
- OCR, printed tags, photo capture, corpus download and PDF search.
- The synthetic reference plant as a demo path.
- Android, AR, multiplayer, cloud services and user accounts.
- Physics, robot dynamics and full 3D collision checking.
- LLM calls on the answer path.
- A full BIM or multi-room plant model.

## 5. Repository layout

```
pipeline/
  pyproject.toml
  README.md
  configs/
    default.toml
  src/scene_pipeline/
    __init__.py
    cli.py
    config.py
    io/
      ply.py
      artifacts.py
    clean/
      filter.py
      frame.py
    geometry/
      voxel.py
      mesh.py
      decimate.py
    segment/
      floor.py
      cluster.py
      obb.py
    classify/
      features.py
      rules.py
      assets.py
    nav/
      occupancy.py
      route.py
    export/
      glb.py
      json.py
  tests/
    fixtures/
app/web/
  public/scene/          generated, gitignored
  src/scene/             loader, route planner, robot, labels
  src/scene-lab/         existing UI shell
data/
  supplied/              raw inputs, gitignored
  derived/               pipeline output, gitignored
docs/
  roadmap.md             this plan
  scene-pipeline.md      artifact and module contract
```

`pipeline/` is its own uv project. It can be run without importing the web app
or the old server package. If the old server package is deleted, `pipeline/`
still runs.

## 6. Pipeline stages

| Stage | Input | Output | Responsibility |
| --- | --- | --- | --- |
| ingest | raw `.ply` | clean point set plus source metadata | parse the header, validate the property schema, keep the sane prefix, compute colour from SH DC, keep scale and opacity |
| clean | point set | `scene.clean.ply` | remove non-finite rows, outliers, invisible gaussians and disconnected floaters; estimate floor and up axis |
| geometry | clean point set | `scene.glb`, optional `scene.points.bin` | build a Three.js-loadable representation, simplify it to a budget, keep vertex colours |
| segment | clean point set | raw clusters and boxes | remove floor and dominant planes, voxelise, cluster, split oversized components, fit oriented boxes |
| classify | clusters, boxes | class proposals | label assets and obstacles from geometry and scene context |
| map | Excel workbook, class proposals | `assets.json` | assign the 30 asset records to candidate objects, one to one, with confidence |
| nav | clean point set, obstacles, floor | `nav.json` | build the walkable grid, inflate by robot radius, compute stand-off points |
| export | all artifacts | manifest plus published copies | validate schemas, write the manifest, copy to `app/web/public/scene/` |

Every stage is deterministic. Timings may differ between runs; geometry,
counts, ids and boxes must not.

## 7. Object model

The scene has three semantic layers:

1. **Walkable floor.** The floor plane and free cells that the robot may use.
2. **Industrial assets.** The primary objects described by the workbook.
3. **Obstacles.** Everything else that blocks the robot or that the robot must
   route around.

### Primary assets

The workbook defines the asset vocabulary. It contains 30 records in five
classes:

| Class | Count |
| --- | ---: |
| `CONTROL_VALVE` | 12 |
| `PROCESS_PUMP` | 6 |
| `ELECTRIC_MOTOR` | 6 |
| `PRESSURE_TRANSMITTER` | 3 |
| `VIBRATION_SENSOR` | 3 |

The workbook is the authority. If an object looks industrial but has no record
in the workbook, it is an obstacle for navigation. A tank, boiler or drum is
not an asset unless a future workbook adds that class.

Mapping is one to one. Each scene object gets at most one asset record and each
asset record gets at most one object. The mapper records one of:

- `matched`: a confident class and size match;
- `provisional`: a plausible match with lower confidence;
- `unmapped`: an asset record with no candidate in the scene;
- `extra`: a framed industrial-looking object with no workbook record.

The demo target is P-005 (`ASSET-017`, process pump, fouling, health 44). It
must be mapped to a reachable pump-like object. If no such object exists, the
run fails loudly rather than silently moving the target.

### Obstacles

Obstacles are clustered objects in the robot height band that are not the floor
and not the mapped asset. The obstacle vocabulary can be coarse:

- `wall`, `column`, `beam`;
- `pipe`, `duct`, `cable_tray`;
- `tank`, `boiler`, `drum`;
- `cabinet`, `pallet`, `crate`;
- `railing`, `stair`, `floor_edge`;
- `equipment`, `clutter`, `unknown`.

A class label is a proposal with a confidence. Navigation treats every obstacle
box as blocking regardless of its label. The label is for the interface and for
debugging, not for deciding whether to collide.

## 8. Navigation and robot

The pipeline does not need to compute the demo route. It provides the map and
the client plans on it.

- Grid resolution: 10 cm by default, configurable.
- Height band: from `floor + 0.10 m` to `floor + robot_height`. Points above the
  robot height do not block the floor route.
- Inflation: `robot_radius + safety_margin`, default 0.45 m total.
- Start: the largest free region near the captured entrance, or an explicit
  start recorded in the manifest.
- Goal: a stand-off point beside the selected asset, not its centre.
- Planner: A* with 8 neighbours, no corner cutting, line-of-sight smoothing.
- Output: `nav.json` holds the grid, frame, floor plane, start and stand-off
  points. The client holds the route.
- Collision: the client tests the route against the inflated grid, not against
  the visual mesh. The visual mesh may be incomplete or noisy; the grid is the
  contract.

The robot is a simple kinematic marker. No physics and no dynamic obstacles.

## 9. Client integration

The client stops calling `/api`. It loads static files from
`/scene/`:

- `scene.manifest.json`;
- `scene.glb`, or the fallback representation named by the manifest;
- `objects.json`;
- `assets.json`;
- `obstacles.json`;
- `nav.json`.

The viewer:

- loads the geometry once and keeps it in the Three.js scene;
- draws asset boxes and obstacle boxes from `objects.json`;
- highlights the selected asset and nearby assets along the route;
- plans a route when the user selects an asset;
- animates the robot along the route;
- shows the selected asset's metadata from the workbook;
- marks obstacles that force a detour.

The old API client, mission view and plate scan are removed from the demo path.
Their UI can stay in the repository until the replacement is ready, but the
default route must not depend on a server.

Performance budget for the demo laptop:

- scene geometry under 40 MB after compression;
- first render under 3 seconds from local disk;
- route planning under 100 ms on the occupancy grid;
- stable 30 fps or better with boxes and labels visible.

If the mesh budget cannot be met, the manifest may point to a decimated point
cloud or splat representation for visual fidelity. Navigation still uses
`nav.json`, so the fallback does not change the route.

## 10. Work plan and gates

| Phase | Work | Gate |
| --- | --- | --- |
| 0 | Freeze the old backend. List the code worth moving into `pipeline/`. Do not delete anything yet. | A written inventory exists in the PR description |
| 1 | Create `pipeline/` with uv, CLI, config, schemas and tests. Port the PLY parser and the sane-prefix filter. | `make pipeline-ingest` produces a clean point set and a manifest from the supplied PLY |
| 2 | Add cleaning, floor detection and geometry export. Try a mesh; keep a point-cloud fallback. | The scene opens in the browser with correct scale and up axis |
| 3 | Port segmentation and oriented boxes from the old segmenter. Add asset and obstacle classification. | `objects.json` frames the room and marks a usable obstacle set |
| 4 | Parse the workbook into `assets.json`, map records to objects, choose P-005, build `nav.json`. | P-005 is mapped to a reachable pump-like object |
| 5 | Swap the client from mock fixtures and API data to published artifacts. Plan routes in the browser. | The robot walks from start to P-005 without crossing an obstacle |
| 6 | Delete the API calls and the server from the demo path. Update README, acceptance and demo docs. | `make demo` runs offline from a clean build with no Python server |
| 7 | Record the demo and freeze. | The 5 minute recording repeats on a clean clone |

The order is deliberate. Geometry and navigation are the risky parts. Asset
metadata and UI polish come after the robot can move through the real scene.

## 11. Acceptance criteria

A run is acceptable when all of these are true:

- `make pipeline` reads the supplied PLY and workbook and writes every artifact
  in `scene-pipeline.md` without manual edits.
- The manifest records the source hash, declared and sane vertex counts, frame,
  floor, schema version and artifact names.
- The geometry loads in Three.js with Y up, metres (after the declared scale
  check), and no visible floaters from the invalid tail.
- At least 30 objects are framed. The 30 workbook records are each classified as
  `matched`, `provisional` or `unmapped`.
- Every framed object has a stable id, an oriented box and a class proposal.
- P-005 maps to a reachable object and has a stand-off point.
- `obstacles.json` covers the non-walkable cells in the robot height band.
- A route exists from the start to P-005, and its minimum clearance is at least
  the robot radius.
- The client loads only local files. Disconnecting the network changes nothing.
- A clean build passes `make web-build`.
- The pipeline is deterministic: a second run produces the same ids, boxes and
  counts.

## 12. Risks and mitigations

| Risk | Trigger | Mitigation |
| --- | --- | --- |
| Meshing a 3DGS capture produces blobs | the mesh has holes or inflated surfaces | Do not block on a perfect mesh. Ship a point-cloud or splat visual layer and a separate collision grid. Record the choice in the manifest |
| The invalid PLY tail reaches the client | a viewer shows a huge bounding box or NaNs | Keep the sane-prefix filter and assert finite bounds in ingest and export |
| Floor or units are wrong | the robot sinks, floats or is the wrong size | Detect the up axis and floor from data, record them, and require a scale check against a known dimension |
| Segmentation merges the room into one cluster | one component holds most points | Remove planes first, split oversized components, and fall back to smaller voxels or k-means patches |
| Asset mapping is ambiguous | many similar valves or pumps | One-to-one assignment by class and size, confidence recorded, manual override allowed |
| Proposed obstacles block the only route | A* returns no path | Obstacles are proposals; allow a reviewed override and choose a different stand-off point |
| Geometry is too large for the browser | long download or low frame rate | Decimate, compress, use LOD, and keep a 40 MB budget |
| Time runs out mid-migration | both API and static path are half-built | Land the static path first, then delete the API. Do not keep two data paths |

## 13. Open decisions

These are intentionally left for the implementation PRs:

1. **Geometry representation.** Screened Poisson on the cleaned cloud, a
   surface-aligned splat method, or a decimated point cloud with splat discs.
   The decision gate is visual quality and load time on the demo laptop.
2. **Asset mapping policy.** Pure rule-based matching first. A vision-language
   check can be added later as a proposal, not as the only path.
3. **Obstacle band.** The default robot height is 1.6 m. Industrial robots may
   need a different band; keep it in `configs/default.toml`.
4. **Start point.** A detected entrance, the largest free region, or a
   hand-reviewed point. The manifest must say which.
5. **Deletion of the old backend.** Do it in phase 6, after the static path
   passes the route gate. Do not delete working code before the replacement is
   demonstrable.

## 14. Documentation status

- `docs/scene-pipeline.md` defines the artifact and module contract.
- `docs/plantpilot-plan.md` and `docs/scene-artifacts.md` describe the old
  FastAPI pipeline. They are kept for history and should not be used for new
  work.
- `README.md`, `docs/acceptance.md`, `docs/features.md`,
  `docs/submission-copy.md` and `docs/video-script.md` still describe the old
  prototype. Rewrite them when the static path is real, not before.
