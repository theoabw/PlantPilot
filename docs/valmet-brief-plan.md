# Valmet, plan for the real brief: a scanned plant made navigable

Written Friday 15:40 after reading the full challenge description. This supersedes the product shape in [valmet-build-plan.md](valmet-build-plan.md). The old plan's reasoning, seats, repo rules, agent rules and briefing questions still apply; its demo does not.

## 0. What the brief actually asks

The published description, in its own words: a digital industrial plant "where the environment does more than look real", one that "understands where machines are, what they are, how people or robots could move between them and which equipment needs attention". The premise it states: "today's 3D captures can be visually extraordinary, but they often lack the meaning needed for intelligent action". The menu it offers: spatial perception, semantic 3D understanding, point-cloud intelligence, digital twins, robotics simulation, and "an assistant that can explain the context behind a maintenance decision". The outcome it asks for: "find the right equipment faster, navigate complex facilities more intelligently and turn fragmented technical data into confident, context-aware action".

That is four capabilities, in one sentence: **locate, identify, navigate, explain**.

The old plan delivered identify and explain, with none of the space. It used a camera as a scanner for a text label, which is the smallest possible reading of "connect the physical and digital worlds". The rewrite is not a different project; it is the same project with the space put back and the camera demoted from the product to one input.

## 1. What survives, and what changes

| Piece | Fate |
| --- | --- |
| The manual corpus (57 sections, page anchors, quotes, FTS) | survives, becomes the "grounded context" layer behind a maintenance question |
| The nameplate OCR, gate and field resolver | survives, becomes the physical anchor: a real plate identifies a real asset in the twin |
| The 48 row register | survives and gains a position, orientation and zone per asset |
| The API and the React shell | survive, with a plant view replacing the four stacked cards as the centre of the screen |
| The plates and the A4 sheet | survive, they are how the judge holds the physical half |
| The plate-to-page timing claim | replaced by a find-the-asset claim, see section 6 |
| "The user is a technician at a valve" | replaced by "a service expert at a door, or a robot with a route" |

## 2. The product, in one line

A scan of a plant room becomes a model you can ask questions of, walk through, and act on: every machine placed and named, the equipment that needs attention lit, a route to it drawn around the equipment, and an answer with a citation for why it needs attention.

The demo uses a **synthetic scan** (a point cloud sampled from a modelled plant) because a real capture of a real facility is not available in one night. We say that out loud in the demo and in the README, and the pipeline we build is the same pipeline a real scan would enter. Claiming a real scan would be the one dishonesty this brief would punish hardest.

## 3. The 90 second demo

| # | Time | What the judge sees |
| --- | --- | --- |
| 1 | 0:00 | A grey point cloud of a plant room, rotating slowly. No colour, no labels. On screen: "a scan is a picture without meaning". |
| 2 | 0:08 | Click **Understand**. Points take colour by class: floor, wall, pipe, pump, tank, valve. 40 assets get tags, and the count appears: "40 assets, 12 classes, 4.2 s". |
| 3 | 0:22 | Click **Needs attention**. Six assets light red, each with an interval and a due date from the register. The rest stay grey. |
| 4 | 0:34 | Photograph a plate with the laptop webcam. The app matches the asset and the camera flies to that exact machine in the plant model, which pulses. The physical plate and the model are now the same object. |
| 5 | 0:48 | Ask for a route from the door to that asset. A straight line is drawn first and visibly cuts through a tank; the real route threads around it, 23 m with 0 collisions against 14 m with 2. |
| 6 | 1:05 | Click the asset and ask why it needs attention. The answer cites the manual section, the page and the VMR003 interval, and the camera highlights the two neighbours that share the same spare. |
| 7 | 1:20 | Closing card: the number from section 6, and the sentence "the scan was synthetic, the pipeline is not". |

The moment that proves it works is step 5: a planned path that visibly avoids a machine is something no dashboard can fake, and it is the brief's own "how people or robots could move between them".

## 4. What is real, what is synthetic

| | |
| --- | --- |
| Real | the manual corpus and its anchors, the OCR and the gate, the asset register, the semantic classes and their geometry rules, the navigation mesh and the path solver, the citations, the offline run, the measured times |
| Synthetic | the point cloud (sampled from a modelled room), the machine shapes, the tags and positions, the scan noise and occlusion we add on purpose |
| Not attempted | photogrammetry or LiDAR capture, a real mill, physics simulation, robot control |

The honesty rules: the README names the synthetic scan in its first paragraph; the demo says it at step 1 and step 7; no screenshot implies a real facility.

## 5. Technical design

**Scan.** A procedural plant room, modelled in code: 12 by 8 metres, machines placed on a grid, pipes overhead, a door and a corridor. Sample it into 60k points with normals, add scanner noise, dropout and an occlusion shadow behind large objects. Store as a compact binary or JSON in `data/` (gitignored) and generate it with `make scan`. Ship a 20k point sample as a fixture so a clean clone runs without the full scan.

**Semantics.** Because the scan is generated, the class labels are known by construction; the interesting part is the rules that recover them: height bands for floor and ceiling, planarity for walls, cylinder fitting for pipes, bounding box plus aspect ratio for tanks, pump and valve. That is a real geometric segmentation pipeline, and it is what would run on a real cloud. Each detected instance becomes an asset candidate; the register supplies its tag, interval and position error.

**Navigation.** Project the cloud to a 2D occupancy grid at 5 cm, mark machine footprints as obstacles, compute a distance field, and run A* from the door to the asset. Draw both the naive straight line and the path, with clearance in centimetres. A moving marker walks the path, which reads as a person or a robot without pretending to be one.

**Anchor.** The existing OCR path, unchanged: plate to fields to register row to a position in the model. This is the only physical input and it is real.

**Assistant.** The existing corpus search, unchanged: question plus asset, top sections with page anchors, a quote, and the VMR003 row. No LLM on the answer path; the citation is the product.

**Rendering.** three.js with 60k points, render on demand rather than per frame, orbit plus scripted fly-to. If WebGL is unavailable on the demo laptop, a canvas 2D orthographic projection of the same points is the fallback, and an isometric SVG plan is the last resort. The camera must never be the reason the demo dies.

## 6. The proof number

Primary claim: **from a plate in frame to the asset located and highlighted in the plant model, median under 12 seconds, against 95 seconds finding the same asset by scrolling a 40 row CMMS table on the same laptop.** Same stopwatch protocol as before, 15 trials per arm, target set fixed in advance.

Supporting numbers, all printed on screen and in the README:

- **Semantic pass**: 60k points to 40 labelled assets in under 5 seconds, with instance recall against the known ground truth of the generated room (a real number, because the generator knows every object).
- **Navigation**: path clearance minimum in centimetres, and 0 collisions against the 2 that the straight line produces.

If the semantic recall or the timing misses, the claim is rewritten to what was measured, not the other way round.

## 7. Scope, cuts, and the two gates

The build window is unchanged: H+0 is 19:30, freeze is Saturday 22:00, sleep 02:45 to 07:45.

| Gate | Time | Must be true |
| --- | --- | --- |
| G1 | 02:00 | A grey cloud renders and rotates; clicking Understand colours it and lists detected assets; one plate flies the camera to its asset. This is the demo without the path. |
| G2 | 07:45 | The path, the attention layer and the citation answer work in one flow, offline |
| G3 | 12:30 | The 90 seconds runs three times in a row on the demo laptop |
| G4 | 16:00 | The numbers from section 6 measured; video script locked |
| Freeze | 22:00 | No code change after this |

Cut order, decided now: the straight-line comparison at 07:45 if the path solver is late; the assistant citations at 10:00, keeping one static cited card instead of a live query; the fly-to animation at 12:00, keeping a cut; the point cloud density down to 25k at any time it makes the laptop stutter. Never cut: the grey-to-semantic toggle, the plate anchor, the path, the number.

## 8. The four seats, re-cut

| Seat | Owns | First handover |
| --- | --- | --- |
| A Scan and semantics | the generator, the class rules, instance extraction, the cloud in the browser | grey cloud by 22:30, coloured by 02:00 |
| B Navigation and geometry | occupancy grid, A*, clearance, the path and the marker | grid and A* by 02:00, clearance numbers by 12:30 |
| C View and interaction | three.js scene, fly-to, attention layer, the six states, the on-screen copy | cloud view by 22:30, the whole 90 seconds by 12:30 |
| D Lead | merges, the plate anchor, the assistant wiring, the proof harness, the video, README, submission | anchor working by 02:00, numbers by 16:00 |

The old plan's rule stands: one writer per file, the lead merges, no automerge.

## 9. Risks

1. **WebGL on the demo laptop.** Test at 19:45 on the actual machine. Fallbacks as in section 5. If none works, the demo becomes the isometric plan with the same interactions, which still answers locate, identify, navigate and explain.
2. **The scan looks fake to a 3D person.** Mitigation: noise, dropout, occlusion shadows, and a textureless grey start; the fidelity that matters is the semantics, and we say so.
3. **Too much to build in one night.** G1 is deliberately a complete demo by 02:00 without the path, so a bad night still ships something off-brief rather than on-brief but broken.
4. **A judge asks "is this a real scan?"** The answer is written above and in the README: synthetic, and the pipeline is what we claim.

## 10. What we do not build

Photogrammetry, LiDAR capture, a real facility, physics simulation, robot control, a full digital twin platform, multi-room sites, VR, mobile AR, a login, a cloud service, an LLM on the answer path.

## 11. The 20 minutes at 19:30

1. Read the full brief in the app and check it against section 0 of this document. If it adds a scored criterion we have not covered, name it and re-cut there, not later.
2. Confirm the demo path of section 3 with the room, out loud, once.
3. Assign the four seats by name.
4. Freeze the data contracts: cloud format, asset record with position, path request and response, plate response.
5. Test WebGL on the demo laptop. If it fails, the fallback is chosen at 19:45, not at midnight.
