# Roadmap, Friday 20:00 to Sunday 10:00

The plan is in [plantpilot-plan.md](plantpilot-plan.md). This page is the execution order: what exists, what gets built when, and what must be true at each gate before the next thing starts. It replaces the 16:40 roadmap, which was built on the synthetic plant.

## Where we are

| Piece | State | Verified by |
| --- | --- | --- |
| Supplied scene | `Industrial Boiler Room.ply`, 1.5 M gaussians, 502,483 sane, y up, dense core about 9 by 4 by 2.5 in file units (assumed metres until the door-height check) | measured with numpy on Friday evening; projections checked |
| Supplied pack | 30 assets, 20,160 telemetry records, 1,000 events, 300 work orders, 38 documents, 120 data quality cases | converted to text and read Friday 19:50 |
| Faulty target | P-005 (ASSET-017), pump, fouling, health 44, high urgency | `Current_State` |
| Reusable code | `Grid`, `astar`, inflation, clearance in `nav.py`; FastAPI shape in `main.py`; viewer shell in `app/web/` | read Friday 19:55 |
| Seat A extraction | `make scene` ingests the delivered file and `make objects` frames 130 objects: 1,506,136 declared, 502,483 sane, largest object 3.7 percent, extraction 2.7 s | measured Friday 21:10; artifact shape in [scene-artifacts.md](scene-artifacts.md) |
| Second scene | `make generality` runs the same stages on the reference plant: 141,575 points, effective voxel 0.058 m from a measured 0.042 m spacing, 62 objects framed, 10 of 10 assets framed against ground truth, PASS | measured Friday 21:10; the plan's generality claim is now supported by a check, not only designed |
| Off demo path | printed plates, OCR identity, register, photo capture, public PDF corpus, `fixtures/plant/plant.json` | the new rubric names none of them; the reference plant is kept only as the generality fixture |
| Stale docs | `README.md`, `docs/submission-copy.md`, `docs/video-script.md` still describe the synthetic-plant product | rewrite on Saturday, before the video |

Contracts freeze at 21:00: scene frame (metres, the up axis reported in the scene metadata, y for the supplied scene), artifact names, module boundaries.

## Seats

| Seat | Owns | First output | Rubric weight |
| --- | --- | --- | --- |
| A | Ingest, segment, objects. Owns the scene-agnostic CLI | `data/scene/scene.npz`, `objects.json` | 30 percent extraction, part of 15 percent backend |
| B | Floor, occupancy grid, A*, route, proximity | `route.json` with path, length, clearance | 25 percent navigation |
| C | Viewer: points, boxes, arrows, avatar, panels | the room on screen with boxes | 10 percent clarity, display of the other 25 |
| D | Pack, mapping, diagnosis, evidence, API glue | `pack.json`, `mapped.json`, `diagnosis.json` | 20 percent diagnostics, part of 30 mapping, 15 backend |

Rules: A, B and D write disjoint modules. C owns `app/web/`. Nobody edits another seat's file without saying so. `make pipeline` is the integration point, owned by D. Seat A keeps every constant from this room out of the ingest: bounds, up axis, floor height and point count are outputs, never defaults.

## Tonight, 20:00 to 02:00

| Window | A | B | C | D |
| --- | --- | --- | --- | --- |
| 20:00 to 21:00 | filter and decimate the splat, scene.npz, screenshot | floor fit and grid prototype on the sane prefix | viewer loads the scene points from the API | pack.json from the xlsx, 30 assets and states |
| 21:00 to 22:30 | plane removal, voxel clustering, split oversized components, boxes | occupancy from points above the floor, inflation | boxes render, selection works | mapping 30 records to 30 objects, faulty target chosen |
| 22:30 to 00:30 | class proposals, object counts, tests | A* to the target waypoint, smoothing, length and clearance | path arrows, avatar marker, follow camera | diagnosis template, evidence IDs, confidence |
| 00:30 to 02:00 | integration fixes, numbers | proximity query along the path | nearby-asset labels, diagnosis panel | end-to-end wiring, `make pipeline` green |

Gate G1 at 01:00: `make pipeline` produces all six artifacts from the supplied files, and the viewer shows the room, the boxes and a route to P-005. If the boxes are missing at 01:00, G1 has failed: ship the route and the diagnosis on the raw points so the demo can start Saturday, and put extraction first on Saturday morning. Do not record G1 as passed.

02:00: commit, clean run, no half-merged state. Sleep.

## Saturday

| Time | Work | Gate |
| --- | --- | --- |
| 08:30 to 10:00 | integration bugs, the faulty target must be reachable and visible | the avatar walks to P-005 |
| 09:00 | ask Valmet in the channel for a clean .ply export, quote the 502,483 sane vertices, and ask whether a second small capture exists. Timebox: one message, no waiting | sent |
| 10:00 to 12:30 | proximity display, evidence panel, confidence from data quality cases, isolate view | G2 at 12:30: the 120 s runs three times in a row, offline, unplugged |
| 12:30 to 16:00 | numbers, README, the technical note, the 5 to 8 slides, submission copy, video script locked. If G2 is green, the second-scene run gets 90 minutes, no more | G3 at 16:00 |
| 16:00 to 19:30 | record at real speed, voice, render, upload to YouTube unlisted | the link works logged out |
| 19:30 to 22:00 | fix what the recording exposes, then freeze | G4 at 22:00: no code changes after this |

Sunday: wake 07:00, clean clone, `make test`, `make demo`, submission saved by 07:30, links checked logged out by 08:00, every member accepts the IP terms by 09:00, done by 09:30. Deadline 10:00.

## Gates

| Gate | Time | Must be true | If it fails |
| --- | --- | --- | --- |
| G0 | 21:00 | contracts frozen, scene.npz on screen, pack.json parsed with 30 assets and a chosen faulty target | fix the loader, not the plan. No seat starts on a different scene |
| G1 | 01:00 | six artifacts produced, boxes and route visible | cut proximity to nearest object only, keep frames and route |
| G2 | 12:30 | 120 s sequence runs three times offline | cut the follow camera, then the avatar animation; keep frames, route, diagnosis |
| G3 | 16:00 | every printed number measured and on screen | print the strongest three and label the rest as future work |
| G4 | 22:00 | video uploaded unlisted, README and submission text final | README and submission first, then sleep |

## Numbers and checks

- Ingest counts: total, sane, rendered gaussians. `make scene` prints them.
- Objects framed, median points per object, extraction seconds. `make objects` prints them.
- Mapping: 30 mapped, confidence, target id. `make map` prints them.
- Route: length, minimum clearance, A* milliseconds. `make route` prints them.
- Diagnosis: evidence items, telemetry records behind the finding, documents cited. `make diagnose` prints them.
- Generality: objects framed on the reference plant against its 10-asset ground truth, and the same commands run on both scenes.

## Risks and triggers

| Risk | Trigger | Response |
| --- | --- | --- |
| Segmentation collapses the room | measured Friday evening: 74 percent of points in one component at 3 cm; fewer than 15 objects after splitting | split every component over 20 k points with k-means. Set a disclosed fallback of 30 framed objects, the mapping count, and never go below 30; below 30 the mapping is incomplete and the check fails |
| The floor plane is wrong | the occupancy grid blocks the whole room | a disclosed per-scene override: a hand-checked floor polygon, with the run labelled assisted. An assisted run does not count toward the scene-agnostic check |
| The target is unreachable | A* returns no path | remap P-005 to the pump-like object with the best clearance |
| The viewer drops frames | under 20 fps on the demo laptop | render a 400 k point subset for the demo and say the number honestly |
| Valmet never sends a clean export | no reply by Saturday 12:30 | ship what the sane prefix shows, and say it on screen and in the limitations |

## What we are not doing

Android, an emulator, AR, a 3DGS rasteriser, SAM or CLIP, an LLM on the answer path, mesh reconstruction, interactive rerouting, robot dynamics, physics, multi-user, cloud services, invented multi-room geometry. One extra supplied-style scene is allowed, as the generality proof, and only after G2.
