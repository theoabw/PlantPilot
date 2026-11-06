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
```

`make scene` reads the file it is given and filters it itself, so the counts it
prints are the counts in the delivered file. The supplied capture declares
1,506,136 vertices and fills the first 502,483: the tail is uninitialised
memory, and the loader keeps only the contiguous sane prefix. It prints the
declared, sane and rendered counts, the detected up axis and the timing.

`make objects` prints the planes removed, the floor, the component and object
counts, the largest object share, the class counts and the extraction time.

Both stages are deterministic: the decimation seed, the plane sampler and the
splitter are fixed. Two runs on one input produce the same planes, floor,
objects and counts; only the `timing_s` field differs.

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

## `scene.npz`

Arrays, all the same length `n`:

| Key | Type | Meaning |
| --- | --- | --- |
| `xyz` | float32 `(n, 3)` | position in the splat frame |
| `rgb` | uint8 `(n, 3)` | colour from the SH DC term, `0.5 + 0.282 * f_dc`, clipped |
| `size` | float32 `(n, 3)` | gaussian scale per axis, `exp(scale)` |
| `alpha` | float32 `(n,)` | opacity, `sigmoid(opacity)` |
| `meta` | JSON string | the block below |

`meta` carries:

- `artifact` (`scene`), `version` (1)
- `source`: file name and path, bytes, sha256, the property list, the declared,
  sane and dropped counts, the first invalid row, rows not read
- `frame`: `up_axis`, `up_axis_index`, `up_axis_sign`, `up_axis_source`,
  `up_axis_evidence`, `units`
- `counts`: `declared`, `sane`, `rendered`, `budget`, `dropped`
- `bounds`: `min`, `max`, `p1`, `p99` per axis
- `gaussians`: `median_size`, `alpha_median`, `alpha_p95`
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
| `parameters` | every threshold in force, so a run can be reproduced |
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
| Points removed as planes | 274,220 (54.6 percent) | `make objects` |
| Floor height | -0.880, rms 0.013 | `make objects` |
| Components at 3 cm | 25,385 | `make objects` |
| Objects framed | 111 | `make objects` |
| Largest object share | 3.8 percent of points | `make objects` |
| Extraction time | 3.4 s | `make objects` |

## Not in these artifacts

The mapping of package records to objects, the route, the diagnosis, and the
HTTP API are other stages with their own artifacts. The `class` proposal, the
box and the point count are what they get to work with.
