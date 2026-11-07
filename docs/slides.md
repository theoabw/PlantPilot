# PlantPilot: six slides for the Valmet evaluator

## Slide 1: A capture is not a map

**On the slide**
- Raw 3DGS shows surfaces; it does not name equipment, walkable floor or service need.
- Valmet supplies Industrial Boiler Room.ply and a builder pack of 30 assets with status, telemetry and service notes.
- The brief asks for dense 3D framing, a collision-free route to a faulty device, mapped metadata and a grounded diagnosis.
- Weights: extraction 30 percent, navigation 25, diagnosis 20, backend 15, clarity 10.

**Visual**
Split frame: grey raw splat left, the same view with coloured boxes and labels right.

**Speaker notes**
The visual gap is the problem, not a missing renderer. A photorealistic capture still cannot say which cluster is a pump or which aisle is clear, and the brief turns that into four demo beats.

## Slide 2: One chain, five artifacts

**On the slide**
- `make scene` reads the capture, keeps the sane prefix, detects the up axis and floor.
- `make objects` removes dominant planes, clusters the rest, fits oriented boxes and refines each class against context.
- `make map` proposes the 30 builder-pack records onto distinct objects.
- `make route` plans to P-005; `make diagnose` grounds the fault in the pack.
- Commands in the Makefile, code in `app/server/src/plantpilot`, viewer in `app/web`.

**Visual**
Left-to-right diagram: PLY, then `scene.npz`, `objects.json`, `mapped.json`, `route.json`, `diagnosis.json`, ending at the viewer.

**Speaker notes**
Every stage writes a file, so any number here can be opened and checked. The artifacts exist before the browser opens, and a fixed input produces the same chain twice.

## Slide 3: 122 frames from a damaged capture

**On the slide**
- The named capture declares 1,506,136 gaussians; only 502,483 rows hold data, so the loader keeps the 33 percent sane prefix.
- Plane removal, voxel clustering and oversized-component splits produce 122 framed objects.
- Largest object holds 1.5 percent of points, median 330 points, extraction 3.71 s.
- Classes such as valve, pump, duct and motor are proposals from shape and context, with a confidence, never identifications.
- The brief allows procedural mapping; the interface shows confidence.

**Visual**
Box overlay render with the count of 122, a class histogram, and one selected frame with its class and confidence.

**Speaker notes**
Density is the first rubric line at 30 percent, and 122 frames is the answer to it. The loader reports what it dropped from the damaged file rather than hiding it, and the class label stays a proposal on screen.

## Slide 4: The route avoids the boxes it extracted

**On the slide**
- Obstacle cells come from four layers: the extracted object boxes, the floor the capture never saw, near-vertical surfaces that run the room's height, and overhead structure; the artifact records each layer's cell count.
- The grid is built once and inflated once, with a 0.20 m agent radius and a 0.02 m margin.
- The route to P-005 on the named capture is 1.08 m with 2 path points and 0.51 m minimum clearance; A* takes 1.57 ms.
- Before this, a saturated point grid fell back to an empty one and the route ran through machines.

**Visual**
Top-down occupancy grid with blocked cells, the 1.08 m path, and the 0.51 m clearance at its tightest point.

**Speaker notes**
This fixes the failure easiest to see in a demo: a robot walking through a boiler. The boxes we draw are the boxes the planner avoids, and so are the floor the capture never saw and the walls it does show; the clearance is measured to the object surface.

## Slide 5: The demo a judge can drive

**On the slide**
- On the complete capture, the robot follows the planned polyline at 0.5 m/s with a follow camera in the browser room view.
- Nearby mapped assets highlight as it passes; the panel shows tag, class and state.
- Arrival triggers the diagnosis card: `attention_required`, health 44, `FOULING` with high urgency.
- The card rests on 144 telemetry rows, 34 alarms, 9 data-quality cases and 2 cited documents; next safe check: inspect the hydraulic path.
- Viewer asset on the complete capture: 1,386,351 gaussians, 77,636,108 bytes, local only.

**Visual**
Screenshot with the robot mid route, one nearby asset highlighted, the diagnosis card open, and the evidence line inset.

**Speaker notes**
The judge drives three moments: send the robot, watch assets light up, read the diagnosis on arrival. The card's numbers come from the supplied pack, not a prompt, and the demo runs offline.

## Slide 6: What we claim, and what we do not

**On the slide**
- Mapping is proposed, not confirmed: 28 of 30 records are proposed and 2 unresolved on the boiler room, all 30 proposed on the complete capture, one object is never proposed for two tags, and the score is a match score, not a probability.
- No door-height scale check has run; distances are scene units treated as metres, and the 1.95 m clear height shows the units are not exact.
- Classes are proposals from shape and context; open-vocabulary vision models were tried and were not reliable enough for labels.
- More time would buy a metric scale, human-confirmed associations and a frame-rate benchmark.
- Architecture: the Python pipeline in `app/server/src/plantpilot` writes artifacts that a local FastAPI process serves to a three.js and Spark viewer.

**Visual**
Two columns, proposed and confirmed: proposed lists mapping and classes, confirmed is nearly empty, with a next-steps list beside it.

**Speaker notes**
The empty confirmed column is the honest picture and the reason the mapping status appears in the demo. The next steps are the work that would move items into it.

Content only; the visual pass comes later.
