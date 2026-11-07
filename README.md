<picture>
  <source media="(prefers-color-scheme: dark)" srcset="docs/brand/plantpilot-horizontal-on-dark.svg">
  <img src="docs/brand/plantpilot-horizontal-on-light.svg" alt="PlantPilot" width="320">
</picture>

# PlantPilot

**From scan to service.**

PlantPilot is an offline semantic scene pipeline for the Valmet challenge. It ingests a supplied 3D Gaussian splat capture, extracts and 3D-frames industrial objects, maps the supplied builder-pack assets onto them, plans a collision-free route to the faulty asset P-005, and serves a browser room view where a robot drives to P-005, highlights nearby assets and opens a grounded diagnosis on arrival. The demo runs on the complete capture the organisers re-uploaded after the first delivery was found truncated; the capture the brief names is also processed, with its numbers reported. There is no network at demo time.

## Problem

Industrial field-service teams and inspection robots work in plants where the physical space, the machine data and the maintenance documents are separate systems. A scan alone is blind: it has no walkable floor, no equipment instances and no identity. The Valmet brief asks for a demonstrator that closes that gap on a supplied Gaussian splat capture, and this repository answers that brief.

## Demo path

1. The room view opens on the capture, with the extracted 3D frames.
2. The builder panel lists the supplied pack's assets, with the faulty target P-005 marked.
3. Open Mission and press Send robot. The robot follows the planned route; assets within 2.5 m brighten and their tags and states are listed.
4. On arrival the diagnosis card opens with the finding, its evidence counts, the next safe check and the document it is grounded in.
5. `?perf=1` on the URL adds a draw and render-time overlay for performance checks.

## Run it

Requirements: Python 3.12+ with `uv`, Node 20+ with `pnpm`.

From a fresh clone:

```bash
uv sync
cd app/web && pnpm install && cd ../..
```

The captures and workbook are supplied separately, not committed. Create `data/supplied/` and put them there:

```
data/supplied/Equipment Room.ply               the complete capture, the demo default
data/supplied/Industrial Boiler Room (1).ply   the named capture, as delivered
data/supplied/builder_pack.xlsx                the supplied Valmet builder workbook
```

Build and serve the complete capture:

```bash
make demo
```

Open <http://127.0.0.1:8000>. The browser opens the room view. That target builds everything the demo path needs. The object atlas and explode view stay empty until `make object-splats` or `make object-meshes` has run for the capture; the rest of the room view works without them. The room view needs a browser with WebGL2; without it the page says so instead of drawing the capture. If port 8000 is taken, serve elsewhere with `make demo PORT=8001`.

The first delivery declares 1,506,136 gaussians in the file the brief names and only 502,483 rows hold data; the rest is unreadable, so the loader keeps the contiguous sane prefix and that scene covers part of the room. The complete capture was re-uploaded by the organisers and is the demo default. Build and serve the named capture instead:

```bash
make demo CAPTURE=boiler
```

The demo video uses the complete capture. The deck names the capture on every slide that quotes a number; the numbers below cover both captures.

## What it does

The six requirements in the brief:

- **Real.** It extracts and 3D-frames industrial objects: 122 in the boiler room, 150 in the complete room.
- **Real supplied data, proposed mapping.** It proposes builder-pack records onto distinct objects, marks each `proposed` or `unresolved`, and fixes P-005 as the target: 28 of 30 proposed on the boiler room, all 30 on the complete capture.
- **Real plan, viewer robot.** It plans a collision-free route to a stand-off point beside P-005; the robot follows the planned polyline.
- **Real.** During a trip, it highlights nearby assets in the scene and lists their mapped metadata. The highlights follow object boxes, not precise masks.
- **Real, grounded in the pack.** Arrival opens P-005's diagnosis: health 44, `FOULING` at high urgency, two findings with evidence ids, and a cited next safe check.
- **Real.** It serves the room view from FastAPI on 127.0.0.1:8000 with no network calls.

## How it works

The pipeline is in `app/server/src/plantpilot/`; the room view is in `app/web/src/room/`.

```
capture PLY --> ingest --> segment and frame --> objects
                                              |
builder workbook --> pack ------------------- + --> mapping --> route
                                              |
                                              + --> diagnosis

objects, mapping, route, diagnosis, viewer PLY --> FastAPI room view
```

**Ingest.** `splat.py` reads the 3DGS PLY header, keeps the first contiguous sane run, and writes `scene.npz`, which every later stage reads. `scripts/make_splat_asset.py` writes the core-property PLY the browser loads.

**Segmentation and framing.** `segment.py` removes the room's planes before it clusters anything. A horizontal plane is gated: a gaussian leaves only when it is inside the band and either its own surface normal matches the plane or the column of points through it is a thin sheet inside the band. That gate is what stops a plane from slicing a machine in half, and on the machine's cross-section band it takes removal from 100 percent to 14 percent while the floor is still removed at 90 percent. Vertical planes are proposed from the gaussians' own normals with their own budget and removed with their whole band, because a wall is a surface the room should not keep: removing walls whole stopped a wall welding everything that stands against it, and the largest component fell from 24 percent of the capture to 3.8 percent. The rest is voxelised at `max(3 cm, 1.4 x floor spacing)`, grouped by connectivity, cut at a measured gap or a thin neck before any counted quota cut, and fitted with an upright box when the object stands on the floor. 69 boxes on the complete capture were completed down to the floor. The boiler room yields 122 objects; the complete room yields 150 from 272 clusters.

**Class names.** `classes.py` runs after extraction and makes only the identity claims the geometry can support. A valve needs pipework within half a metre to be fitted into, and a pump, motor, machine, drum, cabinet or pallet needs the floor or a supporting box underneath. Otherwise the class becomes `object` and the reason says which test failed, so a chair seat is not presented as a valve. Where an object matches an instance from the multi-view fusion, that instance's class and score are used. On the complete capture this names 8 objects by fusion and turns 25 unsupported identity labels into `object`.

**Mapping.** `pack.py` converts the workbook into `pack.json`. `mapping.py` assigns the 30 records one-to-one to distinct objects with a class-and-size prior and two hard gates. Every record is `proposed` or `unresolved`, the score is a match score, not a calibrated probability, and no object gets two tags. P-005 maps to OBJ-034 in the boiler room and OBJ-037 in the complete room. The viewer draws all mapped records as faint proposal frames and lists them with their status under `Synthetic pack records` in the Equipment browser, so the whole proposal set is visible beside the eight brighter reviewed anchors.

**Route planning.** `nav.py` builds an occupancy grid from four independent layers. A cell is walkable ground only when it holds a gaussian near the floor plane, which is what holds the planner inside the truncated capture; on the complete capture the object and overhead layers hold the perimeter and the floor layer changes one reachable cell. A cell is blocked when a near-vertical surface crosses the robot's body, which it detects from the gaussians' own normals: a wall runs the height of the room, an overhead pipe does not, and a machine body still blocks. Object boxes block their footprints when the envelope is plausible for one object, overhead structure blocks a taller robot, and the grid is closed by one cell and then inflated once with a 0.20 m agent radius and a 0.02 m margin. A* searches it to a stand-off waypoint beside the target, and the artifact records each layer's cell count and the rule behind it. Reported clearance is the smallest distance from the smoothed path to the uninflated cells, over the whole route. From the doorway, the Compact AMR and the Humanoid reach all 38 mapped assets and anchors; a destination with no ground reachable beside it stops on the nearest ground that is.

The complete Equipment Room capture starts inside the room, about one fifth of the capture depth inward from the previous doorway position, using [route_starts.json](./fixtures/scene/route_starts.json). Live reroutes use the robot's current position instead, and the same grid rules apply.

Choose the Humanoid or Compact AMR from **Character** in the header, without selecting equipment first. Changing character stops the current trip and returns it to the original start before replanning. During a mission, use **Follow** to track the selected character while orbiting with the pointer. Select **Move camera** to stop following and move the view with W/A/S/D or the arrow keys; select **Follow** again to resume tracking. **Manual control** lets you drive the selected character with W/A/S/D or the arrow keys, within the route's supported floor area. Choose **Third person** or **First person** in the camera controls; drag in first-person mode to look around. Starting an autonomous mission exits manual control.

**Diagnosis.** `diagnose.py` joins P-005's current state, telemetry, alarms, data-quality cases and knowledge documents from the pack. It writes `diagnosis.json` with the condition `attention_required`, health 44, the `FOULING` issue at high urgency, two findings with evidence ids, a next safe check (`inspect hydraulic path`, document `DOC-FIELD-SAFETY`) and citations. The join is deterministic, not a model call: 144 telemetry rows, 34 alarms, 9 data-quality cases and 2 documents feed it. The same stage writes a `reasoning` block: the computed deltas behind the condition, five claims that each cite an evidence id, three alternative causes with a verdict, and a guardrail count. The card opens it on arrival, so it says why fouling is the reading and why a suction restriction or a drifting flow sensor is not.

**Viewer.** `main.py` serves the built React app and the room endpoints (`/api/scene/objects`, `/api/scene/mapped`, `/api/scene/route`, `/api/splat`). The room view draws the capture with Spark inside three.js, takes the up axis from the artifact, draws the reviewed anchors, the mapped proposal frames and the route, and moves the robot along the planned segments at 0.5 m/s with an obstacle-aware follow camera. A frame, the route line and the robot can be hidden by whatever the capture has in front of them, which is the occlusion the ARCore Depth API exists to give. It comes from a second, colourless draw of the capture into the depth buffer with a high opacity cut, so the faint gaussians that are not a surface cannot punch holes in the picture. That draw is fill bound like the colour pass, so it draws every second gaussian and costs half of a fill. Selecting an object adds light to splats within its box and a small boundary margin. This is an approximation, not an object mask, and can include nearby surfaces or miss parts outside the box. On arrival it fetches `/api/diagnosis`, shows the pack evidence references and a citation, and opens the service panel.

In **Layers**, use **Only splats in equipment boxes** to hide splats whose centres are outside all reviewed equipment boxes. Toggle it again to restore the capture. This is a visual box filter, not object segmentation: background inside a box can remain, and splats that overlap a box but have centres outside it are hidden. The control is unavailable when there are no reviewed boxes.

**Top down** hides splats whose centres are above an adjustable height from the
detected floor, initially 1.5 scene units. Tall equipment and overhead services
are cut too, and splats below the cutoff can still overlap it. Sending the robot
keeps this view while it moves; **Follow** switches back to the robot camera and
**Overview** restores the original view.

## Numbers

Every number comes from a run on the two supplied captures in `data/supplied/`; ingest and segmentation read the PLY, mapping and route read the generated artifacts. Times are single runs, not a benchmark.

| Measurement | Industrial Boiler Room | Equipment Room |
| --- | --- | --- |
| Sane gaussians kept | 502,483 of 1,506,136 declared (33 percent) | 1,676,481, none dropped |
| Up axis and floor slab | `-y`, scene y +1.069 | `-y`, scene y +1.167 |
| Planes removed | 16, 8 horizontal and 8 vertical, 63.3 percent of points | 16, 8 horizontal and 8 vertical, 42.8 percent of points |
| 3D-framed objects | 122, nothing capped | 150 from 272 clusters, 122 capped |
| Objects under 0.40 m tall | 61 of 122 | 23 of 150 |
| Objects with nothing under them | 84 of 122 | 65 of 150 |
| Points inside exactly one box | 48.8 percent | 52.4 percent |
| Largest object share | 1.5 percent of points | 4.2 percent of points |
| Extraction time | 3.7 s | 22.0 s |
| Builder-pack mapping | 28 proposed, 2 unresolved, P-005 to OBJ-034 | 30 proposed, 0 unresolved, P-005 to OBJ-037 |
| Route | 1.08 m, 2 path points, 0.51 m minimum clearance | 0.22 m, 2 path points, 0.79 m minimum clearance |
| Reviewed anchors | none | 8, washing machine box 0.88 m tall |
| Viewer asset | 428,991 gaussians, 24,023,947 B | 1,386,351 gaussians, 77,636,108 B |

The boiler capture is truncated, so only 15.2 square metres of its floor was reconstructed; 83 percent of its grid is not walkable ground, just under the 85 percent at which it would be flagged `saturated`, and its route to the service waypoint is 1.08 m. The complete Equipment Room capture is the demo default and the capture every claim about navigation refers to.

The viewer asset holds fewer gaussians than the sane count because `scripts/make_splat_asset.py` drops the fog gaussians before serving: 428,991 of the boiler capture's 502,483 and 1,386,351 of the complete capture's 1,676,481 reach the browser.

## What is real and what is synthetic

- The capture is a real supplied scan. Both PLY files are supplied captures; the boiler file's readable prefix is 502,483 rows.
- The builder pack is supplied synthetic data: its assets, telemetry, alarms, data-quality cases and documents are synthetic Valmet data, not measured plant data.
- The mapping is proposed, not confirmed, and it has no physical coordinates from the pack: the workbook ships synthetic records, not measured positions. Every record has `status: proposed` or `status: unresolved`; the score is a match score, not a calibrated probability.
- The viewer keeps that distinction visible. Pack frames are off by default and labelled synthetic; the equipment card calls out a procedural pack record separately from the observed object; the arrival diagnosis is marked as a synthetic scenario. A pack condition is never presented as a measurement of the physical machine it was assigned to.
- Class labels are geometric proposals, not identifications. The brief allows geometric heuristics, and no open-vocabulary model is in the demo path.
- Units are scene units treated as metres. No door-height scale check has been performed, and the 1.92 m clear height between the boiler room's floor and its ceiling plane means the units are not exact metres.
- The robot is a viewer marker, not a physical simulation: it follows the planned segments at 0.5 m/s.
- The diagnosis is grounded and cited, but it is deterministic retrieval and templates over the pack, not a model at runtime. The reasoning sentences are generated from the computed deltas at build time, not by a model either.

## Technology

- **Pipeline**: Python 3.12 or newer with uv; numpy, OpenCV for geometry and clustering, FastAPI and uvicorn for the local service, pydantic for the API models. The workbook reader uses the standard library.
- **Viewer**: React 18, Vite 5, TypeScript 5, Tailwind CSS, three.js 0.180 and `@sparkjsdev/spark` 2.4 for the splat renderer. Pre-existing open source, not written for this submission.
- **Data**: two supplied Gaussian splat captures and the supplied synthetic Valmet builder pack (assets, telemetry, alarms, work orders, documents). No public dataset and no network call at demo time.
- **AI and models**: none at runtime. Extraction and classification are geometric heuristics with a class-and-size prior, which the brief allows. Open-vocabulary vision models (Grounding DINO, SAM 2.1, SAM 3) were tried on rendered views during the event. SAM 3 text prompts do not identify pumps and valves reliably enough to place assets, so no vision label is produced at runtime. Instance fusion does reach the artifact: masks from sixteen posed views, plus three close-ups for a corner object, are lifted into 3D through the splat's own depth and fused by containment, which gives all seven of the original anchors a fused instance and recovered the office chair that the box layer had labelled a valve, so the reviewed layer has eight objects. Where the fused box disagreed with the box the visual review accepted, both are kept in the fixture. Depth models were evaluated separately and not integrated: Google's ARCore Depth API is a device runtime with no offline path for a trained capture, and the closest downloadable Google model, TIPSv2-B/14 with a DPT depth head, loses to the splat's own depth at every boundary measure tested (0 percent of anchor silhouette pixels within one pixel against 52 percent, occlusion-boundary F1 0.021 against 0.137, Spearman 0.14 median). The splat is already the multi-view reconstruction, so the work went into using its depth, not into estimating depth again.
- **Verification**: pytest with httpx for the API, TypeScript type checking and a Vite production build for the viewer.
- **Build**: `uv sync`, `pnpm install`, and the `make` targets in this repository.

## Docs

- `docs/scene-artifacts.md`: the artifact and API contract.
- `docs/technical-note.md`: the technical note for the submission.
- `docs/slides.md`: the six-slide deck content and speaker notes.
- `docs/video-script.md`: the shooting script for the demo video.
- `docs/acceptance.md`: the checks the pipeline is held to.
- `docs/brand/README.md`: the logo, colours and the assets for the deck and video.

The code is MIT, see `LICENCE`.
