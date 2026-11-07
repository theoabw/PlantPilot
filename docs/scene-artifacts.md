# Scene artifacts

> This is the contract for the artifacts the pipeline writes and the API the
> room view reads today. [scene-pipeline.md](scene-pipeline.md) describes a
> different, unbuilt pipeline; where the two disagree, this page and the code
> are correct.

Generated artifacts are written into `data/` and never committed:

| File | Written by | Read by |
| --- | --- | --- |
| `data/scene/pack.json` | `make pack` (`plantpilot.pack`) | mapping, diagnosis, API |
| `data/scene/mapped.json` | `make map` (`plantpilot.mapping`) | route, API, viewer |
| `data/scene/diagnosis.json` | `make diagnose` (`plantpilot.diagnose`) | API, viewer, video |
| `data/scene/scene.npz` | `make scene` (`plantpilot.splat`) | objects, route, API, viewer |
| `data/scene/objects.json` | `make objects` (`plantpilot.segment`, then `plantpilot.classes`) | mapping, route proximity, API, viewer |
| `data/scene/assets.json` | `make assets` (`plantpilot.assets`) | API, viewer (proposal layer) |
| `data/scene/anchors.json` | `make anchors` (`scripts/make_anchors.py`) | API, viewer (the default reviewed layer) |
| `data/objects/splats/<capture>/` | `make object-splats` (`scripts/make_object_splats.py`) | API, viewer (recognizable objects for the atlas and explode) |
| `data/objects/meshes/<capture>/` | `make object-meshes` (`scripts/make_object_meshes.py`, optional Open3D) | API, viewer (silhouette and solid atlas fallback) |
| `data/viewer/filters/<capture>/` | `make filter-assets` (`scripts/make_filter_assets.py`) | API, viewer (derived channels) |
| `data/viewer/equipment.ply`, `data/viewer/boiler.ply` | `make splat-asset` (`scripts/make_splat_asset.py`) | the browser splat renderer |

[plantpilot-plan.md](plantpilot-plan.md) fixes the artifact names and the module
boundaries. This page fixes the exact shape, because the stages are written in
parallel and a silent change to a key breaks another seat's work.

## Regenerate

```
make pipeline                       # build every artifact the room view needs
make demo                           # build, then serve the API and the web page
make demo CAPTURE=boiler            # the same stages on the named capture
make scene                          # ingest the capture as delivered
make objects                        # extract the framed objects, then refine their classes
make splat-asset                    # the sanitised capture as a viewer PLY
```

`CAPTURE` selects the capture and every artifact path that follows it:
`equipment` is the default and the complete capture the organiser re-uploaded
after the delivered file was found truncated, `boiler` is the capture the brief
names as delivered. The server reads the matching
directory through `PLANTPILOT_SCENE` and the viewer asset through
`PLANTPILOT_SPLAT`, so one `make demo CAPTURE=...` runs either scene with no
other overrides. The table above names the named capture's `data/scene/` paths;
the default run writes the same files under `data/equipment/`.

`make pack` reads `data/supplied/builder_pack.xlsx` and writes
`<capture>/pack.json`. It preserves the tables needed by mapping and
diagnosis, merges the asset master, scene anchors and current state into
`assets`, and records P-005 (`ASSET-017`) as the fixed demo target.

`make map` reads the pack and object artifacts and writes `<capture>/mapped.json`. Each
assignment records its object id, class proposal, mapping method, confidence,
and current state. The target mapping is exposed as `target_object_id`; no
scene-anchor coordinates are used as physical positions.

`make diagnose` reads `pack.json` and writes `diagnosis.json`. It joins P-005's
condition, telemetry, alarms, maintenance history, data-quality cases and
knowledge documents. Findings refer only to stable row evidence IDs, confidence
is reduced when data-quality cases touch the target, and the next safe check is
cited to `DOC-FIELD-SAFETY`.

`reasoning` is computed in the same stage and explains the condition rather than
restating it. `facts` holds the first and last value of six channels over the
asset's window and their percentage change, taken from the same rows as the
evidence. Five claims are generated from those facts, each citing evidence IDs
the artifact already publishes: the flow falls at a steady speed, pressure holds
so the head has not collapsed, motor current rises so the pump works for less
flow, bearing temperature and vibration do not pair as a bearing fault would,
and the next check stays a check. Three hypotheses follow, with verdicts
computed from the facts against named thresholds (`FOULING_FLOW_DROP_PCT`,
`FOULING_SPEED_STABLE_PCT`, `FOULING_PRESSURE_STABLE_PCT`,
`SENSOR_DRIFT_CURRENT_RISE_PCT`): hydraulic path fouling supported, a restricted
suction line or a partly closed valve less likely because the head holds, and
flow sensor drift less likely because the load rises. A verdict drops to
`cannot separate` when the data does not clear its bar. `guardrail` counts the
claims, the cited ones and the unsupported ones, so the artifact states its own
coverage.

`make scene` reads the file it is given and filters it itself, so the counts it
prints are the counts in the delivered file. The supplied capture declares
1,506,136 vertices and fills the first 502,483: the tail is uninitialised
memory, and the loader keeps only the contiguous sane prefix. It prints the
declared, sane and rendered counts, the detected up axis and the timing.

`make objects` prints the planes removed, the floor, the measured point spacing,
the voxel size, the component and object counts, the largest object share, the
class counts, the class refinement counts and the extraction time.

Both stages are deterministic: the decimation seed, the plane sampler and the
splitter are fixed. Two runs on one input produce the same planes, floor,
objects and counts; only the `timing_s` field differs.

## Voxel size follows the capture

A voxel grid only holds a surface together when the voxel is at least as large
as the distance between neighbouring points, and captures differ in density by
an order of magnitude. So the stage measures the spacing on the largest flat
surface it found (the floor: points on the plane divided by the occupied cell
area it covers) and uses `max(voxel_m, 1.4 * spacing)` for the connected
component pass. The requested `voxel_m` is a minimum resolution, not a claim
about this room.

Both numbers are in `parameters`, and `make objects` prints them:

- `parameters.voxel_m`: the requested voxel size.
- `parameters.voxel_m_effective`: the size used for this capture.
- `parameters.spacing`: `spacing_m`, `floor_points`, `floor_area_m2`,
  `density_per_m2` and the method, or a reason when it could not be measured.

## Rendering the room

A gaussian is an anisotropic ellipsoid. A renderer projects its 3D covariance
`R diag(size) diag(size)^T R^T` through the camera Jacobian to a 2D covariance,
draws `alpha * exp(-0.5 * d^T covariance_2d^-1 * d)` per pixel and blends back
to front. That is how the web splat viewers draw a capture, and it is what turns
a cloud of points into textured surfaces.

`plantpilot/splat_render.py` is that renderer in numpy. It is the CPU reference
used for the filter-channel contour rendering and optional previews, not the
product viewer, which draws the same artifact on the GPU:

- it reads the artifact, so it uses the per-gaussian orientation, size, opacity
  and DC colour the ingest stored;
- the camera's up vector comes from the artifact's `up_axis`, so a capture
  whose frame is y-down renders upright;
- metre-wide low-opacity gaussians (the capture's fog) are culled, because they
  cover whole image regions and wash the render out;
- colour is blended in display space, with no gamma conversion.

Both supplied captures are `-y` up: their frames are the usual 3DGS axes with y
pointing down. The floor is the bright concrete slab at positive y and the
ceiling is the dark slab that carries the pipes and trays at negative y, which
is what the walkthrough footage shows. Nothing may hardcode a sign: the
renderer and the viewer both take the axis from the artifact.

### The browser viewer

The app renders the same capture with [Spark](https://github.com/sparkjsdev/spark)
(MIT), a WebGL gaussian splat renderer that lives inside the three.js scene, so
the room and the extracted boxes share one camera and one depth order. The room
view is the only view; the old provisional scene lab, plate scan and plant
mission demo screens have been removed from the frontend.

- `make splat-asset` writes `data/viewer/equipment.ply` for the default capture
  and `data/viewer/boiler.ply` for the named one: the sane prefix with the 14
  core properties only and the fog gaussians dropped, 77,636,108 bytes for the
  complete capture instead of 395,651,019, and 24,023,947 bytes for the supplied
  one instead of 355,449,599, so the browser loads it in seconds.
- `GET /api/splat` serves that file, `GET /api/scene/anchors` serves the
  reviewed demo layer, `GET /api/scene/meshes` serves the object mesh manifest
  and `GET /api/mesh/<anchor-id>` serves one mesh, `GET /api/scene/assets` serves the automatic proposal
  layer, `GET /api/scene/objects` serves the raw extraction and
  `GET /api/scene/mapped` serves the mapping when `make map` has run. Everything
  is local, so the demo makes no network calls.
- The robot is not tied to one destination. Selecting any reviewed equipment and
pressing Send robot here plans a new route from where the robot is standing to a
walkable waypoint beside that machine, and the arrival card keeps the robot in
place, ready for the next leg. The mapped fault target still gets the diagnosis
card; an arbitrary visit gets a plain arrival card and an invitation to choose
the next machine. The follow camera keeps its framing at arrival instead of
cutting to a new view.

The room view is a contextual product shell: a minimal header, a mission card
  with one primary action, an equipment browser on demand, an object card on
  selection, a layers menu for the derived channels, and a developer drawer for
  raw detections, confidence, occupancy and builder diagnostics. Only the
  reviewed anchors are outlined, labels appear on selection or in developer
  mode, and navigation markers exist only while a mission is running.
- The room view draws the reviewed anchors as brighter outlines. The synthetic
  pack mapping is a separate layer, off by default and labelled synthetic: the
  workbook has no physical coordinates, so its records are placed procedurally
  and must not be read as the identity or condition of the object they land on. The Equipment browser lists every
  pack record by tag and state under `Synthetic pack records`, so every proposal and its
  status is visible without presenting it as reviewed equipment.
  Labels and provenance appear on selection. If a capture has no reviewed
  fixture it falls back to the automatic proposal layer, and the raw extraction
  stays one toggle away in the Objects panel.
- `PLANTPILOT_SCENE` and `PLANTPILOT_SPLAT` point the room view at another
  capture, for example `PLANTPILOT_SCENE=data/equipment
  PLANTPILOT_SPLAT=data/viewer/equipment.ply`. The supplied boiler-room delivery
  only holds 502,483 real rows of the 1,506,136 it declares, and those rows
  cover a diagonal band of the room, so the improved `Equipment Room.ply`
  capture (1,676,481 rows, 377 MiB) is the one that shows a whole room.
- The viewer takes the camera up axis from `source.up_axis` in `objects.json`
  and opens at the hero view the extraction records in `camera`: eye, target
  and up in scene coordinates. That view stands at 1.45 m above the detected
  floor and looks down the longest open sightline, so the browser and the
  rendered stills show the same room.
- The route is drawn as a moving arrow trail on a centripetal Catmull-Rom curve
  through the planned polyline, and the robot follows the same curve with a
  damped heading and a damped follow camera, so corners do not snap.
- `GET /api/scene/route` serves the route `make route` writes. The room view
  draws it on the detected floor (the artifact's path carries heights in the up
  axis, the viewer places the line and the robot on the floor plane), sends the
  robot along it with a follow camera, and shows the planned distance and
  clearance. The mapping and diagnosis panels read the matching artifacts when
  they exist.
- The splat URL carries the capture's point count (`/api/splat?v=<points>`) and
  the response is `no-cache`: without that, the browser keeps the previous
  capture under the same URL and draws, say, the boiler room while the artifact
  describes the equipment room. The renderer's splat budget is raised to the
  artifact's count too, because Spark accumulates 2^19 splats by default and
  silently truncates a larger capture.
- Spark needs `three >= 0.180`; the web package is on that version.

## Why the plane band is 4 cm

The splat surface is a slab about 2 cm thick, not a mathematical plane. A
removal band narrower than the slab cuts through it and leaves a shell of the
same wall or floor behind, and that shell is what connects unrelated parts of
the room. Measured on the delivered capture with this stage, same voxel:

| band | planes | removed as planes | objects | pipes | ducts | points in objects | largest object |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 4.0 cm (default) | 16 | 63.3 percent | 122 | 4 | 10 | 29.0 percent | 1.5 percent |

The wider band removes the slab whole, and the gate is what keeps the removal
from slicing a machine that sits across it. Reproduce the default run with

```
uv run python -m plantpilot.segment --plane-distance 0.04 \
  --out /tmp/objects-default.json
```

`--voxel` lowers the requested voxel size the same way, and smaller voxels split
merged machines into several objects; the default 3 cm is what the demo draws at
and keeps one machine from becoming several.

## The frame

- Coordinates are the splat frame. Nothing is rotated, translated, rescaled or
  mirrored. The viewer draws the numbers as they are.
- `up_axis` is a signed axis string. It is detected from the horizontal slabs
  of the capture and the evidence is in `frame.up_axis_evidence`; `--up`
  declares it instead. When two dominant slabs bound the room, the floor is the
  brighter one (light concrete below, dark services above) and the sign points
  from the floor to the other slab. A capture with a single slab uses the side
  the room is on. Every later stage reads the axis from the artifact and never
  from a constant.
- Units are the file's units. A distance is quoted in metres only when
  `scale_check.units_are_metres` is true.

## Box convention

An object box is `centre`, `axes` and `extents`:

- `axes` is a list of three unit vectors, `axes[i]` is the i-th box axis.
- `extents[i]` is the full length along `axes[i]`, not the half length.
- The eight corners are `centre + sum_i (sign_i * extents[i] / 2) * axes[i]`
  for every `sign_i` in `{-1, +1}`.
- The extents are the 0.5th to 99.5th percentile of the object's points along
  each axis, so they fit the shape rather than one stray gaussian. A few points
  of the object therefore sit just outside its own box; select points with a
  small margin (5 cm, or 5 percent of the largest extent) when isolating an
  object.

## Isolating an object

`objects.json` does not carry point indices, on purpose: the artifact stays
small and the point set stays one array. To isolate an object, take the points
of `scene.npz` inside its box (transform into the box frame with `axes`, compare
against `extents / 2` plus the margin above). That is also what the boxes draw,
so the two views cannot disagree.

## `scene.npz`

Arrays, all the same length `n`:

| Key | Type | Meaning |
| --- | --- | --- |
| `xyz` | float32 `(n, 3)` | position in the splat frame |
| `rot` | float32 `(n, 4)` | unit quaternion `(w, x, y, z)`, the gaussian's orientation |
| `rgb` | uint8 `(n, 3)` | colour from the SH DC term, `0.5 + 0.282 * f_dc`, clipped |
| `size` | float32 `(n, 3)` | gaussian scale per axis, `exp(scale)` |
| `alpha` | float32 `(n,)` | opacity, `sigmoid(opacity)` |
| `meta` | JSON string | the block below |

Version 1 artifacts predate `rot`; `load_scene` still reads them and returns
`rot=None`. Everything written now is version 2.

`meta` carries:

- `artifact` (`scene`), `version` (2)
- `source`: file name and path, bytes, sha256, the property list, the declared,
  sane and dropped counts, the first invalid row, rows not read
- `frame`: `up_axis`, `up_axis_index`, `up_axis_sign`, `up_axis_source`,
  `up_axis_evidence`, `units`
- `counts`: `declared`, `sane`, `rendered`, `budget`, `dropped`
- `bounds`: `min`, `max`, `p1`, `p99` per axis
- `gaussians`: `median_size`, `alpha_median`, `alpha_p95`, `rotation` and
  `colour` notes
- `render`: decimation method and seed
- `timing_s`

`plantpilot.splat.load_scene(path)` reads this back, returns a `Scene` with
`xyz`, `rgb`, `size`, `alpha`, `meta` and the `up_index`, `up_sign` and
`height()` helpers, and refuses a file with a missing array, disagreeing shapes
or non-finite coordinates.

The loader accepts the standard 3DGS PLY property set: `x y z scale_0..2
rot_0..3 f_dc_0..2 opacity`, with `f_rest_0..44` optional and ignored. A file
with another schema fails loudly and names what is missing, rather than being
read as a different layout.

## `objects.json`

Top level:

| Key | Meaning |
| --- | --- |
| `artifact`, `version` | `objects`, 1 |
| `source` | the scene path, point count, up axis, units note |
| `parameters` | every threshold in force, plus `voxel_m_effective` and the `spacing` measurement, so a run can be reproduced |
| `planes` | `removed`, `removed_points`, `removed_fraction`, `items` (normal, offset, inliers, rms, horizontal, kind) |
| `floor` | `detected`, `height` (signed, in the up axis), `normal`, `inliers`, `rms_m` |
| `counts` | `components`, `components_kept`, `components_split`, `clusters`, `clusters_dropped_min_points`, `objects`, `capped`, `capped_points`, `floor_snapped`, `points_in_objects`, `points_in_objects_fraction`, `largest_object_share`, `median_points_per_object`, `objects_by_class`, `labels_generic`, `labels_fused`, and the split counters (`splits_by_gap`, `splits_by_neck`, `splits_by_quota`) |
| `classes` | the class refinement: its rules, the structural, standing and fitted class lists, the decisions and the `rewritten` and `named_by_fusion` counts |
| `scale_check` | `performed`, door heights, median, assumed door height, `scale`, `units_are_metres`, reason |
| `timing_s` | extraction time |
| `objects` | the list below, sorted by centre x, then y, then z, ids assigned in that order |

Each object:

| Key | Meaning |
| --- | --- |
| `id` | `OBJ-001` upwards, stable for a deterministic run |
| `centre` | box centre in the splat frame |
| `axes`, `extents` | the box, as fixed above |
| `points` | points inside this piece, after plane removal |
| `class` | a proposal from shape and context: `pipe`, `duct`, `beam`, `valve`, `pump`, `motor`, `machine`, `drum`, `pallet`, `cabinet`, `door`, `ladder`, `panel`, `surface`, `structure`, `seat`, `object`, `unknown` |
| `class_confidence` | 0 to 1, from the rule that fired |
| `class_reason` | the sentence the interface can show |
| `height_above_floor` | centre height above the floor plane, along the up axis |
| `volume_m3` | product of the extents |
| `planarity` | smallest eigenvalue share, 0 for a perfect plane |

The class is a proposal, not an identification. The challenge does not score
label accuracy against a labelled reference, so the rule is geometric and
contextual and says so: `classes.py` keeps a valve only when pipework is within
half a metre, keeps a standing class only with floor or a supporting box under
it, and turns anything else into `object` with the reason. A matching fused
instance may name an object instead. The mapping stage decides which proposal a
package record may use, and the interface shows the confidence next to the
class.

## `assets.json`

The refined object layer. The raw extraction is a segmentation of point
clusters, and a cluttered room merges neighbouring machines into long boxes and
splits equipment into fragments. This artifact is the automatic proposal layer
the viewer falls back to when a capture has no reviewed fixture, and the layer
the developer drawer lists.

Top level: `artifact` (`assets`), `version` (1), `source` (scene and objects
paths), `counts` (`raw_objects`, `colour_instances`, `geometry_candidates`,
`suppressed`, `assets`, `verified`), and `assets`.

Each asset:

| Key | Meaning |
| --- | --- |
| `id` | `AS-` plus eight hex characters of a hash over the centimetre-rounded centre and extents, so the id is stable across runs |
| `class`, `label` | the equipment class and the human label, for example `red pressure vessel` |
| `confidence` | 0 to 1, from the support, compactness and colour evidence; documented in the module |
| `verified` | whether the instance passed the colour or geometry gates, and so may be drawn by default |
| `centre`, `axes`, `extents` | the oriented box, same convention as `objects.json` |
| `points` | gaussians in the instance |
| `rgb` | mean colour of those gaussians |
| `source_object_ids` | the raw objects the instance was built from, so the mapping, the route and the raw layer still line up |
| `method` | `colour_instance` or `geometry_box` |
| `reason` | the sentence the interface can show |

Colour instances are built by region-growing gaussians of one hue in a 5 cm
voxel grid, which is what turns the painted vessels into single objects. The
rest come from compact geometric boxes. Overlaps are resolved with a 3D
oriented-box IoU rule, and a box whose centre falls inside a kept instance is
suppressed. `assets.json` is additive: `objects.json` keeps every raw detection.

## `anchors.json`

The reviewed demo layer. An audit of the proposal layer found that of the 20
boxes it drew by default, 4 matched one object, 5 were partial, 7 wrapped
several things and 4 sat on empty space, and 14 of 20 labels did not fit the
content. The anchors are the boxes that survived that audit, with labels
corrected to what the box actually contains, plus the office chair that
instance fusion recovered.

The input is a small committed fixture, `fixtures/scene/anchors_<capture>.json`,
which also records the audit verdict and a note per anchor. `make anchors` fits
nothing; it validates each fixture box against the capture, adds the number of
gaussians inside and the mean colour, and writes `anchors.json`. A capture with
no fixture is skipped and the viewer falls back to the proposal layer.

Each anchor: `id` (`AN-` plus the proposal id suffix), `asset_id`, `class`,
`label`, `reviewed`, `verdict` (A or B from the audit), `note`, `centre`,
`axes`, `extents`, `points`, `mean_rgb`, the `source_object_ids` it came from,
and the `fused` instance described below. Every anchor that came from the
proposal layer keeps the box the review accepted under `reviewed_box`; the
washing machine is the one whose drawn box is the fused one. Labels are
deliberately generic where the geometry cannot prove a machine class
(`equipment`, `equipment cluster`), because the audit found the shape rules
were being used as class rules.

Every anchor carries the multi-view fusion under `fused`: the method, the
support views, the score, the vertical coverage, the floor gap, the visible
fraction and the fused box. The six reviewed boxes the fusion agreed with stay
in place; the washing machine's reviewed box was the top band of the body, so
the viewer draws its fused box and keeps the reviewed one under `reviewed_box`.
The office chair was recovered by fusion, so its box is the recovered one and it
has no separate `reviewed_box`. The equipment card shows the change as a fusion
check: the views, the score, the stand gap and the percent visible.

The eight anchors also separate observation from inference. Each carries
`observed_type` (what the reviewed box visibly contains), `inferred_function`
(what it is probably used for), `category`, `classification_confidence` and the
`evidence` sentence behind the call. The Equipment card shows the observation
first, then the likely use marked with its confidence, then the evidence. The
builder pack record, where one exists, is shown separately as a pack record and
its condition is labelled as the pack's condition rather than as the scene's.

This is deliberately not an open-vocabulary naming pass. The red Reflex
expansion vessels and the Grundfos pump station visible in the source video are
not enclosed by reviewed anchors, and brand text on a tank is not proof that a
particular reviewed box is that tank. Labels only claim what the box itself
shows: a front-load drum appliance, a vertical vessel, a pump-and-motor body, a
pipe run, a door or cabinet, a floor-level hose and cover, an office chair, and
an unidentified floor cluster. Inferred functions stay unconfirmed in the UI.

## Object meshes

The reference videos turn each detection into a complete 3D asset and then move
it. `make object-meshes` does the same for the reviewed anchors, from the PLY
alone: for each anchor it takes the owned gaussians, uses the thinnest ellipsoid
axis as the normal, drops faint and fog gaussians, downsamples, reconstructs a
surface with Open3D Poisson, trims the density fringe, crops to the anchor box,
decimates to at most 20,000 triangles and copies gaussian colours onto the
vertices. Eight anchors bake in seconds each and the manifest is
byte-identical across runs when Poisson runs single threaded.

The output is a binary PLY per object with vertex colours plus `manifest.json`
with the world bounding box, triangle and vertex counts, owned gaussians and the
anchor box. The meshes are coloured surfaces, not watertight solids: the density
trim and the box crop open the surface, and there is no hole filling. They are
meant for the object atlas and explode view, not for a claim of surveyed
geometry. Open3D is optional; the stage fails with an install hint when it is
missing, and every other stage runs without it.

## Robot profiles and clearance

The room view offers a walking humanoid (0.18 m radius, 1.35 m standing), a
compact AMR (0.20 m, 0.55 m tall) and a cargo AMR (0.45 m, 0.90 m tall).
Choosing a profile replans the same grid with that radius and height, so the
route, the clearance and even the reachable set change with the robot rather
than with a cosmetic model swap. A developer slider covers the clearance value
by hand.

Height matters in this basement: pipework crosses the aisles above AMR height
but through a standing humanoid's torso. The wall layer runs to the room's
working height rather than the robot's, and a separate overhead layer blocks
the horizontal patches inside the robot's own body band above 0.35 m, so the
tall robot plans around that pipework and the low robot plans under it. If the
standing height cannot reach the target, the humanoid falls back to a crouched
height (0.95 m), the route reports that it ducks under low pipework, and the
model visibly crouches for that mission. A route the robot could not physically
take is never drawn.

The robot itself is procedural: a hi-vis humanoid with pelvis, two-segment legs
and arms, joined knees, elbows and hips, a backpack, helmet and visor, or a
wheeled AMR with chassis, four wheels, deck rails, mast, spinning lidar, camera
bar and e-stop. Both are animated from distance travelled, so the walk or the
wheel rotation matches the route speed.

## Robot occlusion

The splat pass is transparent and writes no depth, so overlays such as the
robot used to be drawn on top of every machine. The viewer now draws the same
splats a second time, colourless, into the depth buffer before the colour pass,
so a frame, the route line and the robot are hidden by whatever the capture has
in front of them. The splat image itself is unchanged: the colour pass still
blends in painter's order and writes no depth.

The depth pass reads the capture's own surface, so tanks, cabinets, pipework and
railings all occlude alike. A faint veil of large, low-alpha gaussians is not a
surface, so the depth pass cuts it at a higher opacity than the colour pass
does; without that, the veil would punch invisible holes in anything behind it.

## Camera avoidance

The follow camera would otherwise sit behind the robot through a tank or a pipe.
The route document now carries a second occupancy layer at eye level: the
capture's own gaussians between 1.15 m and 1.85 m above the floor, blocked when
a 0.10 m cell holds at least 50 points. It is deliberately separate from the
robot grid: the robot's body band tops out at 0.55 m and says nothing about
pipework at camera height. The layer is derived from the capture like every
other obstacle, so it is scene agnostic.

In follow mode the camera first tries its ideal position behind the robot. If
that spot is blocked or too close to structure, it samples yaw, distance and
height alternatives and scores them by clearance to the nearest blocked cell,
preferring an open sight line. The previous choice is sticky as a robot-relative
offset, not a world position, so hysteresis prevents flicker without freezing
the camera. The chosen target is damped, camera movement is capped per frame,
and while following the viewer aims the camera itself instead of letting
OrbitControls recompute it from a moving target. A camera already inside
structure is pulled out over a short ramp rather than teleported. Focus, reset,
the arrival camera and the initial framing pass through the same check. If no
candidate is free, the camera escapes above the robot, so it can always re-enter
the scene; Overview also drops follow and restores the room view. Dragging or
zooming chooses a follow angle that stays with the robot, including across
replans, until follow mode is restarted. Avoidance can temporarily adjust it
while the robot moves; a stationary robot keeps the user-selected orbit.

## Live replanning and the area view

The route document carries the occupancy grid it planned on: origin, cell size,
row and column counts, the two horizontal scene axes, and the blocked cells
packed as base64 bits. The viewer uses it for two things.

Placing an obstacle on the floor sends a POST to `/api/scene/reroute` with the
transient blocker rectangles and the robot's current scene position. The server
replans the same grid with `agent_radius_m` 0.20, one inflation pass, and the
same four obstacle layers, then returns a route document with the new path,
distance and clearance. The whole call is about 150 ms, so the path redraws
immediately and the robot resumes from where it stood. When no alternative
exists the response is honest: `reachable` false and the viewer says the path is
blocked.

The route never substitutes another object for its target. When the target is
unresolved in `mapped.json` or its object is not in `objects.json`, the document
has `reachable` false, `target_waypoint_from` `unresolved_target` and a `reason`,
and `make route` exits non-zero. A reroute with an explicit `target` still plans,
because it names its own destination. A missing or unreadable artifact raises
`nav.RouteInputError`, which fails `make route` and makes the reroute endpoint
answer 500 with the file in `detail`.

The area view draws every blocked cell from `grid` as a faint tile on the floor,
so the walls, machine bodies and structural obstacles the planner understands
are visible next to the path. It is the same grid the route uses, not an
illustration.

## Information channels

`make filter-assets` bakes four channels over the same gaussian geometry. Height
is inferno over the 2nd to 98th percentile with photo luminance mixed back in and
a neutral band under 0.15 m. Normals are the thin-axis normal after two voxel
averaging passes and encode as 0.5 + 0.5 n with a headlight term. The edges
channel is the photo at 30 percent luminance plus a contour overlay of 1.2 px
points from depth discontinuity and instance boundaries, each point coloured by
the object that owns it. Semantics is the same dim base plus a pastel overlay of
the anchor gaussians (opacity 0.55) and the contour overlay, so object regions
are tinted while the room still reads as a photograph. The viewer draws the
contours as screen-space points and hides the wireframe boxes in these channels.

## Object splats

`make object-splats` writes one core-property 3DGS PLY per reviewed anchor with
the anchor's own gaussians, the same layout the full-room asset uses. The object
channel renders each of these as an independent splat mesh, so an object keeps
the captured appearance when it is lifted out of the room and shown in the
explode atlas. This is the recognizability that matters for a movable object; a
Poisson surface from the same gaussians is lumpy and is not watertight.

## Object meshes

## Numbers from the supplied capture

Run on the delivered `Industrial Boiler Room (1).ply`:

| Number | Value | Printed by |
| --- | --- | --- |
| Declared vertices | 1,506,136 | `make scene` |
| Sane prefix | 502,483 | `make scene` |
| Rendered gaussians | 502,483 | `make scene` |
| First invalid row | 502,483 | `make scene` |
| Up axis | `-y`, two slabs, floor slab at +1.069 (the brighter one) | `make scene` |
| Points removed as planes | 317,938 (63.3 percent) | `make objects` |
| Planes removed | 16 | `make objects` |
| Floor height | -1.072 in the up coordinate (scene y +1.072), rms 0.011 | `make objects` |
| Point spacing on the floor | 0.014 m | `make objects` |
| Components at 3 cm | 24,358 | `make objects` |
| Objects framed | 122 from 122 clusters, nothing capped | `make objects` |
| Points inside objects | 29.0 percent | `make objects` |
| Largest object share | 1.5 percent of points | `make objects` |
| Median points per object | 330 | `make objects` |
| Extraction time | 3.71 s | `make objects` |
| Clear height | 1.95 m between the floor (scene y +1.072) and the ceiling (scene y -0.878) | `make objects` |

The 1.95 m clear height matters for the scale check: a 2 m door does not fit
under a 1.95 m ceiling, so the capture units are at least a few percent larger
than metres, or the ceiling plane is a suspended one. The door check still has
not been performed and distances stay in scene units.

## The improved capture

Valmet delivered a second, complete export, `Equipment Room.ply`, on Friday
night. It is the same 3DGS schema and it is not damaged: 1,676,481 declared
vertices, every row sane, no tail. It is a different, larger room, so it is a
second scene in its own right, and it is the better demo material.

| Number | Value | Printed by |
| --- | --- | --- |
| Declared vertices | 1,676,481 | `make scene` |
| Sane prefix | 1,676,481, none dropped | `make scene` |
| Up axis | `-y`, floor slab at +1.167 (15.5 percent of points) | `make scene` |
| Dense bounds | x -4.84 to 4.16, y -1.29 to 1.26, z -3.76 to 3.49 | `make scene` |
| Floor | +1.174 in the scene frame, rms 0.015 | `make objects` |
| Point spacing on the floor | 0.016 m | `make objects` |
| Points removed as planes | 717,640 (42.8 percent) | `make objects` |
| Components at 3 cm | 76,200 | `make objects` |
| Objects framed | 150 from 272 clusters, 122 capped | `make objects` |
| Points inside objects | 48.8 percent | `make objects` |
| Largest object share | 4.2 percent of points | `make objects` |
| Extraction time | 22.04 s | `make objects` |

Run it with its own capture argument, so the boiler room artifacts stay where
the other stages expect them:

```
make scene CAPTURE=equipment
make objects CAPTURE=equipment
```

Both captures are in `data/supplied/`, and both are gitignored. The demo runs
on the equipment room by default and the boiler room keeps its own artifact
paths, so switching between them is a change of `CAPTURE`, not of code.

## Not in these artifacts

The mapping of package records to objects, the route, the diagnosis, and the
HTTP API are other stages with their own artifacts. The `class` proposal, the
box and the point count are what they get to work with.
