# PlantPilot: a scanned boiler room that runs an inspection mission

> Superseded 2026-11-06 by [roadmap.md](roadmap.md) and
> [scene-pipeline.md](scene-pipeline.md). Kept for history. The FastAPI path
> described here is not the current plan.

The plan we build against, rewritten Friday evening after the Valmet material arrived. This is the only plan document in the repository. It replaces the synthetic-plant plan from 16:40.

One line: **the supplied Gaussian splat becomes a semantic plant, and the pipeline is scene-agnostic.** Many objects are extracted and 3D-framed, the builder pack's metadata is mapped onto them, an avatar walks a collision-free route to the faulty device, and an evidence-backed diagnosis explains it. The same command is designed to run on any compatible 3D Gaussian splat with the standard PLY properties.

## 1. What changed when the material arrived

| We assumed at 16:40 | What arrived | Consequence |
| --- | --- | --- |
| A scan or mesh we might get, else the generated reference plant | `Industrial Boiler Room.ply` is a 3D Gaussian Splatting file, 1.5 M gaussians, 59 float properties, no triangles | The splat is the scene. Point rendering with size and alpha, not a mesh, not a 3DGS rasteriser. The synthetic plant, the photogrammetry path and its fixture leave the demo path |
| Identity from a printed tag and OCR against our register | The builder pack uses procedural mapping; no tags in the scene; mapping may be random or rule-based | Identity is a mapping decision, recorded with method and confidence. The OCR, ArUco and register modules leave the demo path |
| Grounding from the two public Valmet PDFs | The pack carries 38 knowledge documents, telemetry, alarms, events, service history and data quality cases | Diagnostics cite the pack's own evidence IDs, not the public manual |
| A curated five confirmed assets | The challenge scores extraction density: "the more assets extracted, framed and mapped, the better" | Extraction targets tens of framed objects, not five. The count is a measured number |
| Select an asset, pick a work order, block an aisle | The rubric asks for navigation to a pre-determined faulty device plus proximity display, not interactive rerouting | The faulty device is designated from the pack. The interactive blocker leaves the demo path |
| A tablet or Android client was hinted | The brief says the opposite: "rather than spending time building a mobile or Android frontend" | Web viewer on the demo laptop. No Android, no emulator |

## 2. The supplied data, as measured

The two supplied inputs are not committed. Place them in `data/supplied/` (gitignored) before running the pipeline; derived artifacts stay in `data/` (gitignored). A clean clone can run the code, not the demo, until those two files are in place.

| File | Fact | Consequence for us |
| --- | --- | --- |
| `Industrial Boiler Room (1).ply` | 1,506,136 vertices, 59 float properties, row major. 502,483 vertices are sane; the rest of the file is uninitialised memory (NaN and values around 1e26) | The loader filters every vertex. Use the sane prefix. Report the defect to Valmet and ask for a clean export; do not block on it |
| Same | x in -6.1 to 6.0, y in -4.5 to 3.9 (98 percent between -1.4 and 1.1), z in -7.6 to -0.7; y is up; gaussians about 7 mm; alpha median 0.12; colour in the SH DC coefficient | y is up. The dense core measures about 9 by 4 by 2.5 in file units; a few sparse outliers reach further. There is no scale reference in the file, so treating those units as metres is an assumption from the room proportions; verify it against a known dimension (a standard door is about 2 m) before quoting distances in metres. Render colour from `0.5 + 0.282 * f_dc` |
| `..._Builder_Pack.xlsx` | 30 assets (12 control valves, 6 pumps, 6 motors, 3 pressure transmitters, 3 vibration sensors), 4,320 telemetry rows (the 3-day sample sheet), 1,000 events, 300 work orders, 38 documents, 120 data quality cases | The diagnostic layer is a lookup and a computation over these tables, not an LLM guess |
| Same, `Scene_Anchors` | 30 anchor rows on a synthetic 30 by 16 m grid, `mapping_status = placeholder_until_valmet_scene_received` | The anchors cannot be used as scene positions. Our extracted boxes are the positions; the mapping is procedural and says so |
| Same, `Current_State` | Faulty candidates with high urgency: P-002 cavitation risk (health 45), P-005 fouling (44), M-006 overheating (45), CV-003 position deviation (52) | We designate **P-005 (ASSET-017, PROCESS_PUMP, fouling, health 44)** as the pre-determined faulty device and map it to a pump-like object that is reachable |
| `semantic extraction demo 1.mp4` | refinery scene, objects pulled out of the scene, framed and labelled | The expected output is per-object instances with frames, not a segmentation mask overlay |
| `semantic extraction demo 2.mp4` | warehouse with racking, IBC tanks, a wall of valves, a forklift | Same idea at room scale. Objects stay in place; frames and labels identify them |
| `Industrial Boiler Room (1).mp4` | 1080p walkthrough of the real room | Reference footage for the pitch and for sanity-checking the splat. Not part of the demo path |

The challenge brief also states that mapping may be random or procedural, that an easy UI is preferred over a polished mobile app, and that the evaluation is 30 percent extraction density, 25 percent navigation and proximity, 20 percent diagnostics and grounding, 15 percent backend, 10 percent demo clarity.

## 3. The product

Four verbs, in the order the rubric scores them:

1. **Extract.** Turn 502 k gaussians into objects. Remove the floor and the dominant wall planes, voxelise at 3 cm, cluster with a connected-component pass, then split every oversized component (the measured failure mode: 74 percent of points in one blob) and fit an oriented box per piece. A pipe run, a valve stack, a pump, a door, a pallet, a drum and a fire extinguisher should each become a frame.
2. **Frame and map.** Every object gets a box, a class proposal and a size. The 30 package records are assigned to 30 of those objects by class and size prior, with a recorded method and confidence. Every other object stays framed and unlabelled.
3. **Navigate.** Fit the floor, build a 10 cm occupancy grid from everything standing above it, inflate by the agent radius, run A* from a derived start position at the edge of the captured area to a service position 0.9 m beside P-005. The avatar walks the smoothed path; the camera follows; floor arrows mark the route.
4. **Explain.** As the robot moves, highlight nearby objects within 2.5 m. On arrival, diagnose P-005 from the pack: condition, health, issue, telemetry deviation, alarms, cited knowledge documents, a confidence and a safe next check.

## 4. Pipeline and contracts

Package: `app/server/src/plantpilot/`. Stages run as commands and as `make pipeline`. The coordinate frame is the splat frame, metres; the up axis is reported in the scene metadata (y for the supplied scene). Frozen at 21:00.

| Stage | Module | Output |
| --- | --- | --- |
| pack | `pack.py` | `data/scene/pack.json`: 30 assets, states, telemetry summaries, alarms, documents. Reads the xlsx; nothing derived is committed |
| ingest | `splat.py` | `data/scene/scene.npz`: filtered and decimated cloud (xyz, rgb, size, alpha) plus metadata. Reports total, sane and rendered counts |
| objects | `segment.py` | `data/scene/objects.json`: objects with id, centre, oriented box, extents, class proposal, point count, confidence |
| mapping | `map.py` | `data/scene/mapped.json`: 30 records on 30 objects, mapping method and confidence, the faulty target, unmapped frames listed |
| route | `nav.py` | `data/scene/route.json`: floor height, grid summary, path polyline, length, minimum clearance, start, target waypoint, nearby objects along the path |
| diagnosis | `diagnose.py` | `data/scene/diagnosis.json`: findings, evidence IDs, citations, confidence, next safe check |
| serve | `main.py` | `/api/scene`, `/api/points`, `/api/objects`, `/api/mapped`, `/api/route`, `/api/diagnosis`, `/api/assets/{id}` |
| view | `app/web/` | three.js scene: points, boxes, arrows, avatar, panels |

Reuse from the 16:40 code: the `Grid`, `astar`, inflation and clearance code in `nav.py` behind a new constructor that takes a blocked mask instead of a plant spec; the FastAPI shape in `main.py`; the viewer shell. Everything built on the synthetic reference plant fixture, the printed plates, OCR identity and the PDF corpus comes off the demo path and is not claimed in the README; the reference plant was kept only as the generality fixture for the second-scene run.

**Scene-agnostic is the keyword.** The answer to "one room is not impressive" is not a bigger fake plant, it is a pipeline that takes any compatible plant capture. Every stage takes a path to a Gaussian splat and derives the rest: bounds, up axis, floor, occupancy, objects, waypoints. No constant from this boiler room lives in the code. The command is `make pipeline PLY=path/to/scene.ply PACK=path/to/pack.xlsx`. The loader accepts the standard 3DGS PLY property set (position, scale, rotation, SH DC, opacity, optional SH rest); a file with a different schema fails loudly instead of silently.

The generality claim is conditional. It holds only if the second-scene run passes by G3: convert the old reference plant (the generator wrote 10 assets, 141 k points and per-object ground truth) to a `.ply` with the same gaussian schema and run the same command on it. That run gives one honest number nobody else will have: objects framed against known ground truth. It is a 90 minute item and a 5 second clip in the video, not a second product. If it is cut, the plan, the README and the pitch say "designed for compatible 3DGS PLY inputs, tested on one scene". The generator, its fixture and `make generality` were later deleted from the repository, so that run is a recorded measurement in [roadmap.md](roadmap.md), not a command a reader can still run.

## 5. The 120 second demo

| Time | What the judge sees | What it proves |
| --- | --- | --- |
| 0 to 12 s | The boiler room, points alive, orbit. A quiet line names the source and the number of gaussians rendered | We processed their scene, not ours |
| 12 to 30 s | Boxes appear across the room: pipes, valves, pumps, door, drums, pallet. Sweep the count | Extraction density, 30 percent |
| 30 to 45 s | Select the faulty pump P-005. It turns red. The route appears as floor arrows with length and clearance | Metadata mapped to space, and navigation under way |
| 45 to 80 s | The avatar walks. Nearby objects light up with tag, class and state as it passes. The camera follows | Proximity display, 25 percent |
| 80 to 100 s | Arrival. The diagnosis panel: condition, health, issue, telemetry evidence, alarms, cited documents, confidence, next safe check | Diagnostics and grounding, 20 percent |
| 100 to 115 s | P1: select a framed object, lift it out of the room, show what the mapping knows and what it does not. If the isolate view is cut, select a nearby asset and show its card | Per-object framing in the spirit of demo 1, and honest confidence |
| 115 to 120 s | End card: repository, stack, offline | Clarity, 10 percent |

No interactive blocker, no printed tag, no photo capture, no second screen.

## 6. Numbers we must be able to print

Every number comes from a command or from the app, never typed by hand.

- Ingest: total gaussians, sane gaussians, rendered gaussians, bounding box, axis percentiles, median gaussian size, alpha percentiles, ingest seconds. This is also what makes the measured scene numbers in section 2 reproducible.
- Extraction: objects framed, median points per object, extraction seconds, how many were removed as floor and wall planes.
- Mapping: records mapped, mapping confidence, faulty target id.
- Route: length in metres, minimum clearance in centimetres, A* milliseconds, grid cells blocked and free.
- Proximity: objects within 2.5 m at the busiest point on the path.
- Diagnosis: evidence items cited, telemetry records behind the finding, documents cited.
- Generality: objects framed on the second scene against its ground truth, from the same command.

## 7. Not building

No Android app, no emulator, no AR. No 3D Gaussian rasteriser: screen-space splats sized from the gaussian scale with a minimum pixel size, not bare points. No SAM or CLIP: geometric proposals, and the challenge evaluation does not score label accuracy against a labelled reference. No LLM on the answer path: retrieval plus template, so every sentence has an evidence ID. No robot dynamics, no physics, no multiplayer, no login, no cloud. No interactive rerouting. No mesh reconstruction. No invented multi-room geometry: one captured bay is the demo, and the plant layer is the pack's metadata, not rendered. The scene-agnostic pipeline plus the second-scene run is how we answer "one room is not a plant", without fabricating a plant.

## 8. Risks and responses

| Risk | Trigger | Response |
| --- | --- | --- |
| Splat coverage is thinner than the video suggests | the sane prefix covers only part of the room | Frame what is there, disclose the coverage, ask Valmet for a clean export Saturday morning |
| Clustering merges the boiler room into one blob | floor and walls connect everything | Measured Friday evening: after 8 planes removed, connected components at 3 cm still leave 74 percent of points in one component (87 percent at 4 cm). Splitting large components is mandatory: k-means per oversized component, or patch segmentation. The loader is the easy half |
| Floor is poorly captured | the camera rarely looks down | Estimate the floor from the lowest dense band and disclose it; the occupancy grid only needs obstacles, not floor texture |
| The faulty target lands on an unreachable object | A* returns no path | Choose the pump-like object with the best clearance as the mapping for P-005, and record the choice |
| The tail of the .ply crashes the viewer | NaN or 1e26 in the buffer | The filter is mandatory, and the loader asserts finite bounds |
| The point render reads as dust, not a room | the splat is rendered with bare points | screen-space splats with a minimum pixel size and a 500 k budget; the boxes, the route and the diagnosis carry the demo if the room looks coarse |
| Time | nothing end to end by 01:00 | Cut the follow camera, then the walking animation (the avatar still slides), then proximity labels to the nearest two. Never cut the frames, the route, the moving avatar or the diagnosis evidence |
