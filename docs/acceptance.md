# Acceptance

What has to be true, not what we hope is true. Two parts: the rules we do not negotiate, and one checkable criterion per beat of the demo, plus one for the scene-agnostic claim. Rewritten Friday evening for the supplied splat and the builder pack.

## The constitution

1. **The demo is offline.** No request leaves the machine. The splat and the pack are on disk.
2. **No number without a command.** Every figure in the README, the video or the submission comes from the app or from a `make` target.
3. **Say what is real and what is mapped.** The scene is Valmet's supplied splat. The metadata is synthetic and the mapping is procedural, and the interface says both, once, quietly.
4. **The scene frame is the splat frame.** The up axis is detected or declared once and reported, no rescaling and no mirroring after 21:00. A distance is quoted in metres only after the door-height scale check; otherwise it is quoted in file units.
5. **The splat is points.** It is not called a mesh, a scan with triangles, or a reconstructed surface. Rendering uses point size and alpha.
6. **The faulty device is P-005 and it does not move.** The mapping may be re-tuned, the target does not silently change.
7. **Mapping never guesses silently.** Every mapped object carries a method and a confidence, and the card shows them.
8. **No NaN reaches the viewer.** The .ply tail is uninitialised memory. The loader filters, and the count of dropped vertices is printed.
9. **One demo path.** A second scene, a second UI or a second target waits until the first path runs three times clean.
10. **The product is not the pitch.** Extraction counts, timings and accuracy claims belong in the video, the README and the submission. Provenance (which scene, which mapping method, which pack) is product information and appears once.

## The eight checks

Each criterion is written so a person who did not build the feature can check it. Seven cover the demo beats; the eighth covers the scene-agnostic claim.

### 1. The room is on screen

**Given** the supplied `.ply` in `data/supplied/`,
**when** `make scene` runs,
**then** it prints the total vertices, the sane vertices and the rendered vertices, and the viewer shows the room with points at a stable frame rate.

**Pass:** total 1,506,136, sane about 502,483, rendered at least 300,000, no NaN warning, first frame under 5 s on the demo laptop.
**Check:** `make scene`; open the app.

### 2. Objects are framed

**Given** the sane points,
**when** `make objects` runs,
**then** it writes boxes for the objects it extracted, and each box has an id, an oriented frame, a size in metres and a class proposal.

**Pass:** at least 40 objects framed normally, or a disclosed fallback of at least 30, which is the number of mapped records; below 30 the check fails, because the mapping cannot be complete. No single object holds more than 40 percent of the points, floor and dominant walls are removed, every box has a size and a class proposal, and the viewer draws every box.
**Check:** `make objects`; the box overlay in the viewer.

### 3. The pack is mapped onto the objects

**Given** the builder pack,
**when** `make map` runs,
**then** 30 asset records are assigned to 30 distinct objects, each with a method, a confidence and the state from `Current_State`, and P-005 is assigned to a pump-like object.

**Pass:** 30 mapped, all with a method and a confidence, P-005 marked as the faulty target, no duplicate object and no duplicate record. Selecting P-005 turns it red and opens its card with the mapped state, method and confidence.
**Check:** `make map`; select P-005 in the viewer.

### 4. The avatar reaches the faulty device without clipping

**Given** the occupancy grid and the target waypoint,
**when** `make route` runs,
**then** a path is returned with a length in metres and a minimum clearance, and the path crosses no blocked cell.

**Pass:** route exists, length over 2 m, clearance at least 0.3 m (both after the door-height scale check), A* under 500 ms, the waypoint is at least 0.6 m from the object's box and inside a free cell. The path is drawn as floor arrows, with the length and clearance visible.
**Check:** `make route`; replay the path in the viewer and follow the arrows.

### 5. Nearby objects are shown as the avatar moves

**Given** the route,
**when** the avatar walks it,
**then** objects within 2.5 m are highlighted with a box, a tag and a state, and the set changes along the path.

**Pass:** at three sampled points the highlighted set differs, the nearest three are labelled, and the label shows the mapping method.
**Check:** scrub the path; compare the three samples.

### 6. The diagnosis is grounded in the pack

**Given** the target P-005,
**when** the avatar arrives,
**then** the panel shows the condition, the health, the issue, the telemetry evidence, the alarms, the cited documents, a confidence and a safe next check.

**Pass:** every finding carries an evidence ID that exists in the pack, at least two documents are cited, the confidence drops when a data quality case touches the asset, and the next check matches the field safety document.
**Check:** `make diagnose`; compare the panel to `Current_State`, `Alarms_Events` and `Knowledge_Docs`.

### 7. The demo is one reliable take

**Given** the whole pipeline built,
**when** the 120 second sequence runs three times in a row with the network unplugged,
**then** every beat plays in order and the numbers do not change between runs.

**Pass:** every mandatory beat plays in order: the room, the frames, P-005 turning red with its card and the route, the avatar travelling with proximity labels, the diagnosis, and the end card that names the scene source, the mapping method and the offline status. The isolate view is P1; if it is cut, the script selects a nearby asset instead. Three clean runs, no manual retry, no network request, the same counts and route length each time.
**Check:** unplug, run three times, note the numbers.

### 8. The same command runs on a second scene

**Required whenever the plan, the README or the pitch claims scene-agnostic generality.** If the second-scene run is cut, the claim is downgraded everywhere to "designed for compatible 3DGS PLY inputs, tested on one scene", and this check is not claimed.

**Given** the reference plant written as a `.ply` with the same gaussian schema,
**when** `make pipeline PLY=... PACK=...` runs on it with no code change,
**then** it produces the scene, the objects and a route, and with the pack supplied it also maps and diagnoses. The object count is compared with the plant's ground truth.

**Pass:** the command completes, at least 8 of the 10 reference assets are framed with a box that contains their true position, no box is more than three times the asset's footprint, and the count is printed. A hard-coded room constant anywhere in the ingest or nav path fails this check.
**Check:** run it on the second scene; compare the boxes with `fixtures/plant/plant.json`.
