# PlantPilot

PlantPilot is an offline semantic scene pipeline for the Valmet challenge. It ingests a supplied 3D Gaussian splat capture, extracts and 3D-frames industrial objects, maps the supplied builder-pack assets onto them, plans a collision-free route to the faulty asset P-005, and serves a browser room view where a robot drives to P-005, highlights nearby assets and opens a grounded diagnosis on arrival. The demo runs on the complete capture the organisers re-uploaded after the first delivery was found truncated; the capture the brief names is also processed, with its numbers reported. There is no network at demo time.

## Problem

Industrial field-service teams and inspection robots work in plants where the physical space, the machine data and the maintenance documents are separate systems. A scan alone is blind: it has no walkable floor, no equipment instances and no identity. The Valmet brief asks for a demonstrator that closes that gap on a supplied Gaussian splat capture, and this repository answers that brief.

## Demo path

1. The room view opens on the capture, with the extracted 3D frames.
2. The builder panel lists the supplied pack's assets, with the faulty target P-005 marked.
3. Press Send robot and the robot follows the planned route; assets within 2.5 m brighten and their tags and states are listed.
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

Open <http://127.0.0.1:8000>. The browser opens the room view. That target builds everything it serves.

The first delivery declares 1,506,136 gaussians in the file the brief names and only 502,483 rows hold data; the rest is unreadable, so the loader keeps the contiguous sane prefix and that scene covers part of the room. The complete capture was re-uploaded by the organisers and is the demo default. Build and serve the named capture instead:

```bash
make demo CAPTURE=boiler
```

The demo video and the deck use the complete capture; the numbers below cover both captures.

## What it does

The six requirements in the brief:

- **Real.** It extracts and 3D-frames industrial objects: 130 in the boiler room, 150 in the complete room.
- **Real supplied data, proposed mapping.** It proposes builder-pack records onto distinct objects, marks each `proposed` or `unresolved`, and fixes P-005 as the target: 26 of 30 proposed on the boiler room, all 30 on the complete capture.
- **Real plan, viewer robot.** It plans a collision-free route to a stand-off point beside P-005; the robot follows the planned polyline.
- **Real.** It highlights the 3D frames and mapped metadata of assets near the robot.
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

**Segmentation and framing.** `segment.py` removes the dominant planes, clusters the rest in a voxel grid, splits oversized clusters, and fits an oriented box using 2nd to 98th percentile extents. Each box gets a geometric class proposal, a confidence and a reason. The boiler room yields 130 objects; the complete room yields 150 from 380 clusters.

**Mapping.** `pack.py` converts the workbook into `pack.json`. `mapping.py` assigns the 30 records one-to-one to distinct objects with a class-and-size prior and two hard gates. Every record is `proposed` or `unresolved`, the score is a match score, not a calibrated probability, and no object gets two tags. P-005 maps to OBJ-113 in the boiler room and OBJ-068 in the complete room.

**Route planning.** `nav.py` builds an occupancy grid on the detected floor, marks obstacles from the object boxes at the robot body height of 0.55 m, and inflates once with a 0.20 m agent radius and a 0.02 m margin. A* searches that grid to a stand-off waypoint beside the target, and the artifact records `obstacles_from: objects`. The boiler route is 5.19 m with 0.58 m clearance; the complete room route is 6.14 m with 0.32 m.

**Diagnosis.** `diagnose.py` joins P-005's current state, telemetry, alarms, data-quality cases and knowledge documents from the pack. It writes `diagnosis.json` with the condition `attention_required`, health 44, the `FOULING` issue at high urgency, two findings with evidence ids, a next safe check (`inspect hydraulic path`, document `DOC-FIELD-SAFETY`) and citations. The join is deterministic, not a model call: 144 telemetry rows, 34 alarms, 9 data-quality cases and 2 documents feed it.

**Viewer.** `main.py` serves the built React app and the room endpoints (`/api/scene/objects`, `/api/scene/mapped`, `/api/scene/route`, `/api/splat`). The room view draws the capture with Spark inside three.js, takes the up axis from the artifact, draws the frames and route on the floor, and moves the robot marker along the polyline at 1.15 m/s with a follow camera and a readout. On arrival it fetches `/api/diagnosis` and opens the panel.

## Numbers

Every number comes from a run on the two supplied captures in `data/supplied/`; ingest and segmentation read the PLY, mapping and route read the generated artifacts. Times are single runs, not a benchmark.

| Measurement | Industrial Boiler Room | Equipment Room |
| --- | --- | --- |
| Sane gaussians kept | 502,483 of 1,506,136 declared (33 percent) | 1,676,481, none dropped |
| Up axis and floor slab | `-y`, scene y +1.069 (21.7 percent of points) | `-y`, scene y +1.167 |
| 3D-framed objects | 130 | 150 from 380 clusters |
| Largest object share | 3.7 percent of points | 1.2 percent of points |
| Extraction time | 3.35 s | 10.2 s |
| Builder-pack mapping | 26 proposed, 4 unresolved, P-005 to OBJ-113 | 30 proposed, 0 unresolved, P-005 to OBJ-068 |
| Route | 5.19 m, 3 path points, 0.58 m minimum clearance | 6.14 m, 6 path points, 0.32 m minimum clearance |
| Viewer asset | 502,483 gaussians, 28,139,499 B | 1,676,481 gaussians, about 94 MB |

## What is real and what is synthetic

- The capture is a real supplied scan. Both PLY files are supplied captures; the boiler file's readable prefix is 502,483 rows.
- The builder pack is supplied synthetic data: its assets, telemetry, alarms, data-quality cases and documents are synthetic Valmet data, not measured plant data.
- The mapping is proposed, not confirmed. Every record has `status: proposed` or `status: unresolved`; the score is a match score, not a calibrated probability.
- Class labels are geometric proposals, not identifications. The brief allows geometric heuristics, and no open-vocabulary model is in the demo path.
- Units are scene units treated as metres. No door-height scale check has been performed, and the 1.95 m clear height means the units are not exact metres.
- The robot is a viewer marker, not a physical simulation: it follows the planned polyline at 1.15 m/s.
- The diagnosis is grounded and cited, but it is deterministic retrieval and templates over the pack, not a model at runtime.

## Technology

- **Pipeline**: Python 3.12 or newer with uv; numpy, OpenCV for geometry and clustering, FastAPI and uvicorn for the local service, pydantic for the API models. The workbook reader uses the standard library.
- **Viewer**: React 18, Vite 5, TypeScript 5, Tailwind CSS, three.js 0.180 and `@sparkjsdev/spark` 2.4 for the splat renderer. Pre-existing open source, not written for this submission.
- **Data**: two supplied Gaussian splat captures and the supplied synthetic Valmet builder pack (assets, telemetry, alarms, work orders, documents). No public dataset and no network call at demo time.
- **AI and models**: none at runtime. Extraction and classification are geometric heuristics with a class-and-size prior, which the brief allows. Open-vocabulary vision models (Grounding DINO, SAM 2.1) were tested on rendered views during the event and did not reach label quality, so they are not on the demo path.
- **Verification**: pytest with httpx for the API, TypeScript type checking and a Vite production build for the viewer.
- **Build**: `uv sync`, `pnpm install`, and the `make` targets in this repository.

## Docs

- `docs/scene-artifacts.md`: the artifact and API contract.
- `docs/technical-note.md`: the technical note for the submission.
- `docs/slides.md`: the six-slide deck content and speaker notes.
- `docs/video-script.md`: the shooting script for the demo video.
- `docs/acceptance.md`: the checks the pipeline is held to.

The code is MIT, see `LICENCE`.
