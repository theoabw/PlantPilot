# Valmet, plan for the real brief: photos in, meaning out

Written Friday 16:10, after reading the full challenge description and after probing the capture stack on this machine. Supersedes the product shape in [valmet-build-plan.md](valmet-build-plan.md) and the synthetic-scan draft of this plan. The repo rules, seats, agent rules and briefing questions in the old plan still stand.

## 0. What the brief asks

A digital plant "where the environment does more than look real", one that "understands where machines are, what they are, how people or robots could move between them and which equipment needs attention". The premise: "today's 3D captures can be visually extraordinary, but they often lack the meaning needed for intelligent action". The menu: spatial perception, semantic 3D understanding, point-cloud intelligence, digital twins, robotics simulation, and "an assistant that can explain the context behind a maintenance decision".

Four capabilities: **locate, identify, navigate, explain**.

## 1. The product, in one line

Take four photos of a room with a phone. In about ten seconds you have a metric point cloud you can walk through: every machine placed and named, the ones that need service lit up, a route to one that goes around the equipment, and a cited reason behind its maintenance decision.

Photo in, meaning out. No scanner, no LiDAR, no GPU.

## 2. Probed and working before the event

Run on this machine on Friday afternoon, on a real photograph:

| Step | Tool | Cost | Result |
| --- | --- | --- | --- |
| Monocular depth | Depth Anything V2 Small, int8 ONNX, Apache-2.0 | 1.7 s at 518 px, CPU | clear near and far separation, object edges preserved |
| Depth refinement | OpenCV `ximgproc.guidedFilter` | 0.1 s | depth edges snap to image edges |
| Metric scale | OpenCV ArUco, 4x4 dictionary, scale card | instant | a 150 mm card printed at 100 percent measures 590 px against 591 expected |
| Back-projection | numpy pinhole, 60 degree FOV | 0.2 s | 241k coloured points at 2 cm voxels, bounded 0.1 to 20 m |
| Floor | RANSAC plane | 0.3 s | normal and offset, 9 to 54 percent inliers depending on the scene |

Whole path, photo to cloud: **3.2 s**. Model size: 27 MB, fetched once by `make models`, cached in `data/`, gitignored.

The stack is all open source and all local: OpenCV 5.0 (ArUco, guided filter, calibration), ONNX Runtime, Depth Anything V2 (Apache-2.0), numpy and scipy, three.js in the browser. No API key, no service, nothing on the network at demo time.

## 3. The 90 second demo

| # | Time | What the judge sees |
| --- | --- | --- |
| 1 | 0:00 | Four photos of the room on the table, taken with a laptop or phone. Click **Scan**. A point cloud builds in front of them, grey, colours off. |
| 2 | 0:15 | The cloud rotates. Points take colour: floor, wall, pipe, machine. Labels appear on the machines. Count and time on screen. |
| 3 | 0:28 | Click **Needs attention**. Three machines light red, each with its service interval and due date from the register. The rest stay grey. |
| 4 | 0:40 | Hold a printed plate to the camera. OCR reads it, the twin finds the same asset, the camera flies to it and pulses. The plate on the table and the machine in the model are the same object. |
| 5 | 0:55 | Ask for a route from the door to that machine. The straight line is drawn first and visibly cuts through a bench; the real route threads around it, with clearance in centimetres and 0 collisions against 2. |
| 6 | 1:12 | Ask why it needs attention. The answer cites the manual section, the page, the quote, and the VMR003 interval, and highlights the neighbour that shares the spare. |
| 7 | 1:25 | The numbers from section 6, then one line: "four photos, one laptop, no scanner". |

The moment that proves it: step 5. A path that visibly avoids an object is the brief's own "how people or robots could move between them", and nothing can fake it.

## 4. What is real, what is not

| | |
| --- | --- |
| Real | the photographs, the depth model, the guided filter, the camera scale from the ArUco card, the point cloud, the floor plane, the semantic rules, the instance extraction, the path solver, the printed plates and OCR, the corpus and its page anchors, the timing, the offline run |
| Synthetic | the asset register, the tag numbers, the service intervals, the plate text, the door and the "plant" framing. The room is the venue room, not a mill. |
| Not attempted | LiDAR, photogrammetry bundle adjustment, a real facility, physics simulation, robot control, a production digital twin platform |

The honesty sentence for the README and the closing card: **the room is real, the plant is a stand-in; every stage of the pipeline is the one that would run on a real site.**

## 5. Technical design

**Capture.** `scripts/scan.py` and `fieldplate/capture.py`, already in the repo: depth, refinement, ArUco scale, back-projection, clamping (sky and the far field are dropped, or z runs to kilometres), voxel downsample, RANSAC floor. Multi-photo: align two or three clouds by the marker pose when it is visible in more than one frame; if alignment is flaky, each photo is its own fragment and the viewer shows fragments side by side. Start with one photo, add the second only if time is left.

**Semantics.** Three layers, weakest to strongest, in this order:
1. **Geometry**: floor from RANSAC, walls from vertical planes, pipes from cylinder runs, machines as boxes above the floor. Cheap, deterministic, explainable.
2. **Appearance**: CLIP (ONNX, open weights) over object proposals to label each box as valve, pump, tank, cabinet, bench or pipe. This is the "AI-grounded" layer.
3. **Tags**: the printed plate on a machine is recognised by OCR and matched to the register. Tags beat guesses: a tagged machine is certain, an untagged one is a hypothesis, and the UI shows the difference.

If CLIP is too slow or too vague on the venue photos, layer 2 is cut and the demo runs on geometry plus tags. Say which is running on screen.

**Navigation.** Occupancy grid at 5 cm from points between 0.2 and 1.5 m above the floor, machine boxes as obstacles, A* from the door to the asset, clearance reported in centimetres, and the naive straight line drawn for contrast.

**Answer.** The existing corpus and register: question plus asset, top three sections with page anchors, a quote, and the VMR003 interval. No LLM on the answer path.

**Rendering.** three.js, one buffer of points, render on demand. Fallback: canvas 2D projection of the same buffer. Last resort: isometric SVG plan. WebGL is tested at 19:45 on the demo laptop.

## 6. The proof number

Primary: **four photos to a labelled, navigable cloud in under 12 seconds, measured on screen**, and **from a plate in frame to that machine highlighted, median under 10 seconds, against 95 seconds finding the same asset by scrolling a 40 row CMMS table.**

Supporting, printed on screen and in the README: depth time per frame (1.7 s measured), point count, scale error against a tape measure on the scale card (target under 5 percent), semantic recall on a hand-labelled set of 20 objects in the room (target 15 of 20), and path clearance plus collision count against the straight line.

If a number misses, the claim is rewritten to what was measured.

## 7. Gates and cuts

| Gate | Time | Must be true |
| --- | --- | --- |
| G0 | 19:45 | WebGL runs on the demo laptop, and one venue photo becomes a cloud on screen |
| G1 | 02:00 | Three photos to a cloud, coloured by height and geometry, machines boxed, one plate flies the camera to its asset |
| G2 | 07:45 | Attention layer, path with clearance, cited answer, all in one flow, offline |
| G3 | 12:30 | The 90 seconds runs three times in a row |
| G4 | 16:00 | Numbers from section 6 measured, video script locked |
| Freeze | 22:00 | No code changes after this |

Cut order: multi-photo alignment at 02:00 if it fights back; CLIP labels at 07:45, keeping geometry plus tags; the straight-line comparison at 10:00; the fly-to animation at 12:00, keeping a cut; point density down to 50k at any stutter. Never cut: the photos-to-cloud moment, the plate anchor, the path, the number.

## 8. The four seats

| Seat | Owns | First handover |
| --- | --- | --- |
| A Capture | depth, refinement, ArUco scale, multi-photo, cloud format | venue photo to cloud by 22:30 |
| B Semantics | geometry classes, instance boxes, CLIP labels, plate matching | boxes by 02:00, labels by 07:45 |
| C View and navigation | three.js scene, attention layer, route and marker, the six states | cloud on screen by 22:30, path by 07:45 |
| D Lead | integration, assistant wiring, proof harness, the demo run and video, README, submission | plumbed photo to screen by 22:30 |

One writer per file, the lead merges, no automerge.

## 9. Risks

1. **Depth on flat, low-texture surfaces** (white walls, glass) comes out blobby. Mitigation: photograph with texture in frame, keep the guided filter, and lean on the tag where a machine matters.
2. **Scale error.** A misprinted card makes every metre wrong. Mitigation: measure the printed card with a ruler and pass the real length to `scan.py`; the number is one field.
3. **Semantics look confident and are wrong.** Mitigation: tags are certain, geometry is probable, CLIP is a hypothesis, and the UI says which. Never merge the three into one unlabelled number.
4. **WebGL on the venue laptop.** Tested at 19:45 with two fallbacks.
5. **Too much for one night.** G1 is a complete demo without the path, so a bad night still ships on-brief.

## 10. Not building

LiDAR or photogrammetry capture, a real facility scan, physics simulation, robot control, a multi-room twin platform, VR or AR, a login, a cloud service, an LLM on the answer path.

## 11. The 20 minutes at 19:30

1. Check the brief against section 0; name any scored criterion we are missing and re-cut there.
2. Confirm the demo of section 3 out loud once.
3. Assign the four seats by name.
4. Freeze contracts: photo upload, cloud buffer, asset with position and label source, route request and response.
5. WebGL test on the demo laptop. Fallback chosen at 19:45, not at midnight.
