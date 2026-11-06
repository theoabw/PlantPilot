# Scene artifacts

Two files, both generated into `data/` and never committed:

| File | Written by | Read by |
| --- | --- | --- |
| `data/scene/scene.npz` | `make scene` (`plantpilot.splat`) | objects, route, API, viewer, preview renderer |
| `data/scene/objects.json` | `make objects` (`plantpilot.segment`) | mapping, route proximity, API, viewer |

[plantpilot-plan.md](plantpilot-plan.md) fixes the artifact names and the module
boundaries. This page fixes the exact shape, because the stages are written in
parallel and a silent change to a key breaks another seat's work.

## Regenerate

```
make scene                          # ingest the capture as delivered
make objects                        # extract the framed objects
make scene PLY=path/to/other.ply    # the same code on another capture
make generality                     # the same stages on the reference plant, scored
```

`make scene` reads the file it is given and filters it itself, so the counts it
prints are the counts in the delivered file. The supplied capture declares
1,506,136 vertices and fills the first 502,483: the tail is uninitialised
memory, and the loader keeps only the contiguous sane prefix. It prints the
declared, sane and rendered counts, the detected up axis and the timing.

`make objects` prints the planes removed, the floor, the measured point spacing,
the voxel size, the component and object counts, the largest object share, the
class counts and the extraction time.

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
- `up_axis` is a signed axis string (`+y` for the supplied capture). It is
  detected from the densest flat slab in the capture and the evidence is in
  `frame.up_axis_evidence`; `--up` declares it instead. Every later stage reads
  the axis from the artifact and never from a constant.
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

## Numbers from the supplied capture

Run on the delivered `Industrial Boiler Room (1).ply`, Friday evening:

| Number | Value | Printed by |
| --- | --- | --- |
| Declared vertices | 1,506,136 | `make scene` |
| Sane prefix | 502,483 | `make scene` |
| Rendered gaussians | 502,483 | `make scene` |
| First invalid row | 502,483 | `make scene` |
| Up axis | `+y`, floor slab at -0.894 | `make scene` |
| Points removed as planes | 278,931 (55.5 percent) | `make objects` |
| Planes removed | 8 | `make objects` |
| Floor height | -0.877, rms 0.020 | `make objects` |
| Point spacing on the floor | 0.014 m | `make objects` |
| Components at 3 cm | 23,952 | `make objects` |
| Objects framed | 130 | `make objects` |
| Points inside objects | 37.0 percent | `make objects` |
| Largest object share | 3.7 percent of points | `make objects` |
| Median points per object | 431 | `make objects` |
| Extraction time | 2.7 s | `make objects` |
| Floor to next horizontal plane | 1.95 m (floor -0.877, next plane +1.074) | `make objects` |

The 1.95 m clear height is the distance to the next strong horizontal plane, not
to a confirmed ceiling: at +1.074 the points look like a pipe tray or duct. It
matters for the scale check, because a 2 m door does not fit under a 1.95 m
ceiling, so the units cannot be exactly metres unless that plane is not the
ceiling.

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

## Not in these artifacts

The mapping of package records to objects, the route, the diagnosis, and the
HTTP API are other stages with their own artifacts. The `class` proposal, the
box and the point count are what they get to work with.
