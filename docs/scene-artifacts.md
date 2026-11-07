# Scene artifacts

> This is the contract for the artifacts the pipeline writes and the API the
> room view reads today. [scene-pipeline.md](scene-pipeline.md) describes a
> different, unbuilt pipeline; where the two disagree, this page and the code
> are correct.

Generated artifacts are written into `data/` and never committed:

| File | Written by | Read by |
| --- | --- | --- |
| `data/scene/pack.json` | `make pack` (`plantpilot.pack`) | mapping, diagnosis, API |
| `data/scene/mapped.json` | `make map` (`plantpilot.mapping`) | route, diagnosis, API, viewer |
| `data/scene/diagnosis.json` | `make diagnose` (`plantpilot.diagnose`) | API, viewer, video |
| `data/scene/scene.npz` | `make scene` (`plantpilot.splat`) | objects, route, API, viewer, preview renderer |
| `data/scene/objects.json` | `make objects` (`plantpilot.segment`) | mapping, route proximity, API, viewer |
| `data/scene/assets.json` | `make assets` (`plantpilot.assets`) | API, viewer (proposal layer) |
| `data/scene/anchors.json` | `make anchors` (`scripts/make_anchors.py`) | API, viewer (the default reviewed layer) |
| `data/objects/splats/<capture>/` | `make object-splats` (`scripts/make_object_splats.py`) | API, viewer (recognizable objects for the atlas and explode) |
| `data/objects/meshes/<capture>/` | `make object-meshes` (`scripts/make_object_meshes.py`, optional Open3D) | API, viewer (silhouette and solid atlas fallback) |
| `data/viewer/filters/<capture>/` | `make filter-assets` (`scripts/make_filter_assets.py`) | API, viewer (derived channels) |
| `data/viewer/room.ply` | `make splat-asset` (`scripts/make_splat_asset.py`) | the browser splat renderer |

[plantpilot-plan.md](plantpilot-plan.md) fixes the artifact names and the module
boundaries. This page fixes the exact shape, because the stages are written in
parallel and a silent change to a key breaks another seat's work.

## Regenerate

```
make pipeline                       # build every artifact the room view needs
make demo                           # build, then serve the API and the web page
make demo CAPTURE=equipment         # the same stages on the complete capture
make scene                          # ingest the capture as delivered
make objects                        # extract the framed objects
make splat-asset                    # the sanitised capture as a viewer PLY
make generality                     # the same stages on the reference plant, scored
```

`CAPTURE` selects the capture and every artifact path that follows it:
`equipment` is the default and the complete capture the organiser re-uploaded
after the delivered file was found truncated, `boiler` is the capture the brief
names as delivered. The server reads the matching
directory through `PLANTPILOT_SCENE` and the viewer asset through
`PLANTPILOT_SPLAT`, so one `make demo CAPTURE=...` runs either scene with no
other overrides.

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

`make scene` reads the file it is given and filters it itself, so the counts it
prints are the counts in the delivered file. The supplied capture declares
1,506,136 vertices and fills the first 502,483: the tail is uninitialised
memory, and the loader keeps only the contiguous sane prefix. It prints the
declared, sane and rendered counts, the detected up axis and the timing.

`make objects` prints the planes removed, the floor, the measured point spacing,
the voxel size, the component and object counts, the largest object share, the
class counts and the extraction time.

Both `scene` and `objects` render their preview PNGs with the native splat
renderer (below). `SPLAT_GAUSSIANS`, `PREVIEW_WIDTH` and `PREVIEW_HEIGHT` set
how much of the capture goes into a preview: the default draws 500,000
gaussians at 1400 by 900 in about 15 seconds, and `SPLAT_GAUSSIANS=0` draws all
of them for a still. `--mode points` keeps the old fast debug view.

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
used for the preview PNGs, the deck and the stills, not the product viewer,
which draws the same artifact on the GPU:

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
is what the walkthrough footage shows. The synthetic reference plant is `+y`
because our own generator builds it that way, which is why nothing may hardcode
a sign: the renderer and the viewer both take the axis from the artifact.

### The browser viewer

The app renders the same capture with [Spark](https://github.com/sparkjsdev/spark)
(MIT), a WebGL gaussian splat renderer that lives inside the three.js scene, so
the room and the extracted boxes share one camera and one depth order. The room
view is the default view; the scene lab with its provisional room stays behind
the `scene lab` button.

- `make splat-asset` writes `data/viewer/room.ply`: the sane prefix with the 14
  core properties only, 28 MB for the supplied capture instead of 355 MB, so the
  browser loads it in seconds.
- `GET /api/splat` serves that file, `GET /api/scene/anchors` serves the
  reviewed demo layer, `GET /api/scene/meshes` serves the object mesh manifest
  and `GET /api/mesh/<anchor-id>` serves one mesh, `GET /api/scene/assets` serves the automatic proposal
  layer, `GET /api/scene/objects` serves the raw extraction and
  `GET /api/scene/mapped` serves the mapping when `make map` has run. Everything
  is local, so the demo makes no network calls.
- The room view draws the reviewed anchors by default, as thin outlines, and
  shows labels and provenance only on selection. If a capture has no reviewed
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
- Spark needs `three >= 0.180`; the web package is on that version and the
  preview renderer here is unchanged.

## Why the plane band is 4 cm

The splat surface is a slab about 2 cm thick, not a mathematical plane. A
removal band narrower than the slab cuts through it and leaves a shell of the
same wall or floor behind, and that shell is what connects unrelated parts of
the room. Measured on the delivered capture with this stage, same voxel:

| band | planes | removed as planes | objects | pipes | ducts | points in objects | largest object |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 2.5 cm | 12 | 54.6 percent | 111 | 1 | 6 | 37.2 percent | 3.8 percent |
| 4.0 cm (default) | 8 | 55.5 percent | 130 | 8 | 16 | 37.0 percent | 3.7 percent |

The wider band removes the same share of the capture with fewer planes, and more
of what is left becomes a pipe or a duct frame instead of a strip welded to a
wall. Reproduce the narrow row with

```
uv run python -m plantpilot.segment --plane-distance 0.025 --planes 12 \
  --max-objects 120 --out /tmp/objects-narrow.json
```

`--voxel` lowers the requested voxel size the same way. At 2 cm the delivered
capture frames 163 objects instead of 130; the default 3 cm is what the demo
draws at and keeps one machine from becoming several.

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
- The extents are the 2nd to 98th percentile of the object's points along each
  axis, so they fit the shape rather than one stray gaussian. A few points of
  the object therefore sit just outside its own box; select points with a small
  margin (5 cm, or 5 percent of the largest extent) when isolating an object.

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

- `artifact` (`scene`), `version` (1)
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
| `counts` | `components`, `components_split`, `clusters`, `objects`, `capped`, `points_in_objects`, `points_in_objects_fraction`, `largest_object_share`, `median_points_per_object`, `objects_by_class` |
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
| `class` | a geometric proposal: `pipe`, `duct`, `beam`, `valve`, `pump`, `motor`, `machine`, `drum`, `pallet`, `cabinet`, `door`, `ladder`, `panel`, `surface`, `structure`, `unknown` |
| `class_confidence` | 0 to 1, from the rule that fired |
| `class_reason` | the sentence the interface can show |
| `height_above_floor` | centre height above the floor plane, along the up axis |
| `volume_m3` | product of the extents |
| `planarity` | smallest eigenvalue share, 0 for a perfect plane |

The class is a proposal, not an identification. The challenge does not score
label accuracy against a labelled reference, so the rule is geometric and says
so. The mapping stage decides which proposal a package record may use, and the
interface shows the confidence next to the class.

## `assets.json`

The refined object layer. The raw extraction is a segmentation of point
clusters, and a cluttered room merges neighbouring machines into long boxes and
splits equipment into fragments. This artifact is the representation the room
view draws by default.

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
corrected to what the box actually contains.

The input is a small committed fixture, `fixtures/scene/anchors_<capture>.json`,
which also records the audit verdict and a note per anchor. `make anchors` fits
nothing; it validates each fixture box against the capture, adds the number of
gaussians inside and the mean colour, and writes `anchors.json`. A capture with
no fixture is skipped and the viewer falls back to the proposal layer.

Each anchor: `id` (`AN-` plus the proposal id suffix), `asset_id`, `class`,
`label`, `reviewed`, `verdict` (A or B from the audit), `note`, `centre`,
`axes`, `extents`, `points` and the `source_object_ids` it came from. Labels are
deliberately generic where the geometry cannot prove a machine class
(`equipment`, `red painted equipment`), because the audit found the shape rules
were being used as class rules.

## Object meshes

The reference videos turn each detection into a complete 3D asset and then move
it. `make object-meshes` does the same for the reviewed anchors, from the PLY
alone: for each anchor it takes the owned gaussians, uses the thinnest ellipsoid
axis as the normal, drops faint and fog gaussians, downsamples, reconstructs a
surface with Open3D Poisson, trims the density fringe, crops to the anchor box,
decimates to at most 20,000 triangles and copies gaussian colours onto the
vertices. Seven anchors bake in about six seconds and the manifest is
byte-identical across runs when Poisson runs single threaded.

The output is a binary PLY per object with vertex colours plus `manifest.json`
with the world bounding box, triangle and vertex counts, owned gaussians and the
anchor box. The meshes are coloured surfaces, not watertight solids: the density
trim and the box crop open the surface, and there is no hole filling. They are
meant for the object atlas and explode view, not for a claim of surveyed
geometry. Open3D is optional; the stage fails with an install hint when it is
missing, and every other stage runs without it.

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

Run on the delivered `Industrial Boiler Room (1).ply`, Friday evening:

| Number | Value | Printed by |
| --- | --- | --- |
| Declared vertices | 1,506,136 | `make scene` |
| Sane prefix | 502,483 | `make scene` |
| Rendered gaussians | 502,483 | `make scene` |
| First invalid row | 502,483 | `make scene` |
| Up axis | `-y`, two slabs, floor slab at +1.069 (the brighter one) | `make scene` |
| Points removed as planes | 278,931 (55.5 percent) | `make objects` |
| Planes removed | 8 | `make objects` |
| Floor height | -1.074 in the up coordinate (scene y +1.074), rms 0.012 | `make objects` |
| Point spacing on the floor | 0.014 m | `make objects` |
| Components at 3 cm | 23,952 | `make objects` |
| Objects framed | 130 | `make objects` |
| Points inside objects | 37.0 percent | `make objects` |
| Largest object share | 3.7 percent of points | `make objects` |
| Median points per object | 431 | `make objects` |
| Extraction time | 2.9 s | `make objects` |
| Clear height | 1.95 m between the floor (scene y +1.074) and the ceiling (scene y -0.877) | `make objects` |

The 1.95 m clear height matters for the scale check: a 2 m door does not fit
under a 1.95 m ceiling, so the capture units are at least a few percent larger
than metres, or the ceiling plane is a suspended one. The door check still has
not been performed and distances stay in scene units.

## The second scene

`make generality` writes the synthetic reference plant (16 by 12 by 5 m, 10
assets with ground truth) as a 3DGS PLY, runs the same ingest and segmentation
on it, and scores the boxes against the asset positions. The plant is our own
synthetic capture, labelled as such; it is not a Valmet asset.

Run on the plant, Friday evening:

| Number | Value |
| --- | --- |
| Points in the capture | 141,575 |
| Measured spacing on the floor | 0.042 m |
| Effective voxel size | 0.058 m (requested 0.030 m) |
| Components | 763 |
| Objects framed | 62 |
| Largest object share | 4.2 percent of points |
| Extraction time | 0.9 s |
| Assets framed against ground truth | 10 of 10, bar is 8 |
| Command result | PASS |

Two honest details. The tank boxes frame the lower part of each tank, because
the tanks (4 m tall) merge with the pipe run and the size limit cuts the merged
shell; the check asks that a box contain the asset's centre and stay inside
three times its footprint, not that the box be the whole asset. And the asset
classes on this scene are weaker than on the delivered capture (a pump is
framed as `motor`), which the check does not score.

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
| Floor | +1.173 in the scene frame, rms 0.016 | `make objects` |
| Point spacing on the floor | 0.016 m | `make objects` |
| Points removed as planes | 705,418 (42.1 percent) | `make objects` |
| Components at 3 cm | 73,673 | `make objects` |
| Objects framed | 150 (capped from 380 clusters) | `make objects` |
| Points inside objects | 47.4 percent | `make objects` |
| Largest object share | 1.2 percent of points | `make objects` |
| Extraction time | 10.2 s | `make objects` |

Run it with its own paths, so the boiler room artifacts stay where the other
stages expect them:

```
make scene PLY="data/supplied/Equipment Room.ply" SCENE=data/equipment/scene.npz \
  PREVIEW=data/equipment/preview.png
make objects SCENE=data/equipment/scene.npz OBJECTS=data/equipment/objects.json \
  OBJECTS_TOP=data/equipment/objects_top.png OBJECTS_VIEW=data/equipment/objects_view.png
```

Both captures are in `data/supplied/`, and both are gitignored. Switching the
demo to the equipment room is a team decision: the mapping, route and diagnosis
stages read the artifact paths, so it is a change of `SCENE` and `OBJECTS`, not
of code.

## Not in these artifacts

The mapping of package records to objects, the route, the diagnosis, and the
HTTP API are other stages with their own artifacts. The `class` proposal, the
box and the point count are what they get to work with.
