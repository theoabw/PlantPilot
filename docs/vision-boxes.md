# Vision boxes

Geometry alone cannot separate objects that touch in a cluttered room, so the
segment stage's boxes on the Equipment Room are often blobs, scraps or halves.
`scripts/make_vision_boxes.py` finds the objects on the floor and walls with an
outline model instead, offline, as a build step. The demo never runs the model:
it reads `fixtures/scene/vision_boxes_equipment.json`.

The results are for Classify mode only. They do not replace `objects.json` and
must not feed mapping or routing: replacing `objects.json` is what broke the
robot route before.

## Method

1. Render posed views from inside the room with `plantpilot.splat_render`,
   leaving out everything above the service line (0.85 of the measured ceiling
   height, 1.97 m on this capture). Eyes sit on a 1.2 m grid at 0.55 m and
   1.25 m, over captured floor and clear of the capture, looking 8 ways.
2. Outline everything in each view with `facebook/sam2.1-hiera-large`. It is
   openly downloadable. It outlines but does not name.
3. Lift each outline onto the gaussians it covers through a depth buffer built
   from the gaussians the renderer actually draws.
4. Join outlines from different views that hold the same 3 cm voxels, and keep
   what at least 3 views agree on.
5. Fit an upright box to each object's gaussians, leaving out the gaussians
   removed as walls and floor.

## Running it

The model needs packages the project does not depend on (torch, torchvision,
transformers, accelerate), so it runs in its own environment. On a CUDA 12.6
machine:

```
uv venv .venv-vision
uv pip install --python .venv-vision torch torchvision --index-url https://download.pytorch.org/whl/cu126
uv pip install --python .venv-vision transformers accelerate numpy pillow opencv-python-headless
```

Then, with `make scene` already run for the Equipment Room:

```
PYTHONPATH=app/server/src .venv-vision/bin/python scripts/make_vision_boxes.py \
  --scene data/equipment/scene.npz --objects data/equipment/objects.json \
  --out data/equipment/vision_boxes.json --work data/equipment/vision_work
```

`--limit-views 8` runs a trial of 8 views that all look at one spot (`--focus`
picks it) and writes outline overlays to the work folder. `--plan-only` reports
how much of the room the camera plan sees, without the model.

On an RTX 4090 the full run is 216 views and took 34 minutes, nearly all of it
the numpy renderer. Renders are cached as PNG, because SAM found 337 outlines in
8 fresh renders and 232 in the same renders saved as JPEG. The lifted outlines
are cached too, so changing the join or filter settings reruns in seconds with
no model.

The run writes the results JSON and, next to it, `vision_boxes_members.npz`:
the exact gaussians of each result (`indices[offsets[i]:offsets[i + 1]]` for
`ids[i]`). The viewer lights up everything inside a box, so a box alone also
lights up its surroundings; the membership file is what a precise highlight
needs. It is 349 KB of binary, so it stays in `data/` with the other generated
artifacts and is not committed.

## Results

Graded by eye from two-view contact sheets (`scripts/vision_contact_sheets.py`)
by Claude, the AI model that also built and tuned the pipeline. The grades are
in `fixtures/scene/vision_review_equipment.txt` and
`fixtures/scene/vision_review_equipment_tuned.txt`. They are not measured truth
and not independent, many renders are blurry, and the tuned setting was chosen
against the same grades, so the tuned counts are optimistic.

| | First full run (465) | Tuned (193) |
|---|---|---|
| whole | 80 (17%) | 71 (37%) |
| part of an object | 127 (27%) | 67 (35%) |
| merged | 38 (8%) | 15 (8%) |
| clutter | 220 (47%) | 40 (21%) |
| real objects split across several results, at least | 19 in 50 results | 8 in 20 results |

For comparison, an earlier visual review of 33 sampled segment boxes found 2
whole, 6 part, 17 merged and 8 clutter, and at least 11 of the 33 held a piece
of an object split across several boxes. That review used lower resolution
renders, so the comparison is indicative only.

The worst split is a wall cabinet column, still in 5 results: SAM outlines its
doors one by one in every view. A vacuum cleaner is one whole result plus two
overlapping part results.

## Tuning

`scripts/tune_vision_boxes.py` sweeps the settings on the cached outlines and
scores each against the first run's grades by membership. The first run used at
least 2 views, 150 gaussians, a longest side under 3.2 m and a join at overlap
0.35. The tuned run uses at least 3 views, 400 gaussians, a longest side under
2.0 m and a join at overlap 0.45 or containment 0.7.

Merging and splitting pull against each other. With the filters fixed, on the
first run's 80 whole, 220 clutter and 19 split objects:

| Join at overlap / containment | whole kept | clutter kept | splits joined | new merges |
|---|---|---|---|---|
| 0.45 / 0.7 (tuned) | 65 | 39 | 3 | 6 |
| 0.35 / 0.7 | 65 | 46 | 3 | 6 |
| 0.25 / 0.7 | 59 | 42 | 7 | 12 |
| 0.2 / 0.7 | 55 | 44 | 8 | 19 |
| 0.35 / 0.5 | 57 | 42 | 7 | 11 |

Joining more fixes about one split for every one or two new merges and loses
whole results, so the split count fell mostly because the filters drop small
pieces. Splits come from the outlines themselves, and changing the join step will
not fix them.

## Not covered

- No class names: SAM 2.1 outlines without naming.
- Nothing in the viewer reads the fixture yet.
- SAM 3 might outline whole objects better, but it is gated behind a licence
  acceptance and was not tried.
