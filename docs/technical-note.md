# PlantPilot technical note

PlantPilot turns a supplied Gaussian splat capture into a framed, mapped and navigable plant scene, plans a route to the faulty target and shows a grounded diagnosis on arrival. It runs offline: Python for the pipeline, a browser for the room view.

## 1. Problem and scope

The brief describes plant context fragmented across space, condition data and documents, and raw captures with no meaning: no walkable floor, obstacles or machines. The demonstrator must frame assets, map the builder pack, plan a collision-free route to the faulty target, highlight nearby assets and deliver cited guidance on arrival. Scope: one static floor, offline. `Industrial Boiler Room (1).ply` is damaged, `Equipment Room.ply` is complete, both run the same stages.

## 2. Pipeline

Modules: `app/server/src/plantpilot/`.

- Ingest: `splat.py`; PLY to `scene.npz`; contiguous sane prefix, 2,000,000 gaussian budget.
- Extract: `segment.py`; `scene.npz` to `objects.json`; 4 cm band, 8 planes, voxel `max(3 cm, 1.4 x spacing)`, split, 150 cap.
- Pack: `pack.py`; workbook to `pack.json`; P-005 target.
- Map: `mapping.py`; pack, objects to `mapped.json`; 0.7 class plus 0.3 size prior, 0.6 and 0.5 gates.
- Route: `scripts/make_route.py` and `nav.py`; scene, objects and mapping to `route.json`; 0.10 m grid, 0.55 m body, 0.20 m radius plus 0.02 m margin, A*.
- Diagnose: `diagnose.py`; pack to `diagnosis.json`; joins by `asset_id`, evidence ids, citations.
- Splat asset: `scripts/make_splat_asset.py`; PLY to the viewer PLY; sane prefix, core properties.

Both captures are y down (up `-y`); ingest detects and records the axis, floor slab (+1.069 boiler, +1.167 equipment) and evidence in `scene.npz`.

The 4 cm band is wider than the 2 cm splat slab: a narrower band leaves a shell that keeps the room connected; 4 cm removed the same share (55.5 against 54.6 percent) with 8 planes, not 12, and 130 objects, not 111.

## 3. Semantic extraction

Extraction voxelises at `max(3 cm, 1.4 x floor spacing)`, because a 26-connected graph needs that scale. Components over 20,000 points or 3.0 m are cut recursively along the longest PCA axis at the widest histogram gap (6,000 target). Each piece gets a PCA box with 2nd to 98th percentile extents and a square-section rotation search. The class is a geometric proposal among 16 names (pipe, duct, beam, valve, pump, motor, machine, drum, pallet, cabinet, door, ladder, panel, surface, structure, unknown) from aspect ratio, extents, footprint and height. It is not an identity: shape is not function, no labelled reference was scored, and mapping decides whether a record may use it.

## 4. Mapping

Each of the 30 assets gets one record. Candidates score `0.7 x class + 0.3 x size compatibility`, with two hard gates: score at least 0.6 and size compatibility at least 0.5, so class alone cannot carry a wrongly sized object. A proposed object leaves the pool; one object never hosts two tags. Records are `proposed` or `unresolved`; unresolved has no object, no score and a reason. The score is an uncalibrated prior, not a probability, and nothing is confirmed. The brief allows random mapping; that is not an excuse for false claims: the assignment is still only class-and-size evidence.

## 5. Navigation

`route.json` comes from an occupancy grid built once from the extracted boxes and the residual capture. A cell is blocked when an object overlaps floor + 0.08 m to floor + 0.55 m, the robot body, not a person, and also when the capture's own points still fill that band, so walls and unboxed structure block too. The 0.10 m grid is inflated once by 0.20 m agent radius plus 0.02 m margin. A* is 8-connected and penalises low clearance. Clearance is the distance transform to the inflated boundary plus the radius, minimised over the corridor excluding the 0.9 m docking approach, so it is measured to the object surface; the artifact records `obstacles_from: objects+structure`, radius, margin. Before this, a saturated point grid fell back to empty and the route crossed equipment; `test_nav.py` keeps a regression.

## 6. Diagnosis

`diagnosis.json` joins `pack.json`, the converted workbook, on `asset_id`, carrying target, condition, health, issue, findings with evidence ids, telemetry, alarms, data-quality cases, citations and next check. For P-005: `attention_required`, health 44, `FOULING`, high urgency, 2 findings, 144 telemetry rows, 34 alarms, 9 data-quality cases, 2 cited documents, next check `inspect hydraulic path` cited to `DOC-FIELD-SAFETY`. It is retrieval plus rules, not a generative model: every statement is a join or template over a stable row id, and confidence is the pack's model confidence minus 0.05 per quality case, capped at 0.35. A generative model could write beyond the rows; this cannot invent a cause or explain one the pack lacks.

`reasoning` explains the condition instead of restating it. `facts` holds the first and last value of six channels over the asset's window and their percentage change, read from the same rows as the evidence. Five claims are generated from those facts, each citing evidence ids the artifact already publishes. Three hypotheses follow, with verdicts computed from the facts against named thresholds: `FOULING_FLOW_DROP_PCT` 10, `FOULING_SPEED_STABLE_PCT` 1, `FOULING_PRESSURE_STABLE_PCT` 1 and `SENSOR_DRIFT_CURRENT_RISE_PCT` 3, each chosen from the window change a fault makes against the scatter this pack carries. Hydraulic path fouling is supported when flow falls while speed and pressure hold; a restricted suction line or a partly closed valve is less likely when the head does not collapse; flow sensor drift is less likely when the motor load rises with a falling flow. A verdict falls back to `cannot separate` when the data does not clear its bar, and the sentence then says what the series does not show. `guardrail` reports how many claims carry a resolvable evidence id, so the artifact states its own coverage, and the test suite recomputes every fact from the pack and asserts the two agree.

## 7. Viewer

The room view is React and Vite in `app/web/src/room/`. One three.js scene with three.js 0.180 and `@sparkjsdev/spark` 2.4: `SparkRenderer` draws the `SplatMesh` from `/api/splat`. Boxes, route, robot and proximity colours are drawn in the same scene by the same camera. The robot is a 0.44 x 0.30 x 0.32 m marker at 0.5 m/s; the follow camera sits 2.6 m behind and 1.4 m above it. Every 500 ms the viewer highlights frames within 2.5 m. On arrival it fetches the diagnosis. It reads `/api/scene/objects`, `/api/scene/mapped`, `/api/scene/route`, `/api/splat` and `/api/diagnosis`, served by `main.py`; the panel calls the assignment a proposal, not a confirmed identification.

## 8. Verification

`make test` runs the offline pytest suite; `make web-build` runs `tsc --noEmit` and `vite build`; `make check` runs `scripts/sinceai_check.mjs`.

Boiler room: 1,506,136 declared and 502,483 sane (33 percent), `-y` up with the floor slab at +1.069 (21.7 percent), 130 objects, largest 3.7 percent, median 431 points, 2.73 s, 26 proposed and 4 unresolved with P-005 to OBJ-113, route 5.19 m with 3 path points and 0.58 m clearance, A* 20.0 ms, viewer 428,991 gaussians and 24,023,947 B.

Equipment room: 1,676,481 sane and none dropped, `-y` up with the floor slab at +1.167, 150 objects from 380 clusters, largest 1.2 percent, 10.71 s, 30 proposed and none unresolved with P-005 to OBJ-068, route 6.38 m with 9 path points and 0.32 m clearance, A* 12.7 ms, viewer 1,386,351 gaussians and 77,636,108 B.

## 9. Limits and what we would do next

No scale check has passed: no door-like box was framed, so `units_are_metres` is false and distances are scene units; the 1.95 m clear height means the units are not exact metres. Identities are proposed, never confirmed; classes are geometric heuristics, not learned labels. The reviewed anchors add an observed type, an inferred function, a confidence and the evidence sentence behind each label, and the viewer shows them as observation versus likely use rather than as facts. Open-vocabulary vision models were tried on rendered views but did not reach label quality, so none is imported. The robot is a marker, not physics. No frame rate or browser benchmark was run. Next: a scale check, a labelled class sample, a visibility gate before any vision label enters an artifact, and a viewer benchmark.

## 10. Dependencies and how to run

Python 3.12 or newer with uv. The demo path uses numpy, OpenCV (`cv2`), FastAPI, uvicorn and pydantic; the workbook reader uses the standard library. The web build uses React 18, Vite 5, TypeScript 5, three.js 0.180 and `@sparkjsdev/spark` 2.4; tests use pytest. Nothing runs on the network at demo time. Put the capture and `builder_pack.xlsx` in `data/supplied/`. `make demo` defaults to `CAPTURE=equipment` (the complete `Equipment Room.ply`), builds every artifact and the page, and serves both at `http://127.0.0.1:8000`; `make demo CAPTURE=boiler` runs the capture the brief names. `make test` and `make check` run the checks; `npm run build` also works; the Makefile uses pnpm.
