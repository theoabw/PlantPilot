# PlantPilot: a scanned plant that runs an inspection mission

The plan we build against, written Friday 16:40, and the only plan document in the repository.

One line: **a work order becomes a mission.** Pick the order, the plant identifies the machine, explains why it needs attention, computes a route to its inspection position, and reroutes when an aisle is blocked.

## 0. The brief, in four words

Locate, identify, navigate, explain. The description's own premise is that a scan is "visually extraordinary" but lacks "the meaning needed for intelligent action", and it asks for a plant that knows where machines are, what they are, how people or robots move between them, and which equipment needs attention. PlantPilot is that sentence as a product.

## 1. Review of the supplied plan

Verdict: the product shape is better than our previous draft and we are taking it. Three assumptions do not survive our data and our clock, and each has a concrete replacement.

**Taking, unchanged.**

- The mission as the unit of the demo: work order, asset, route, blocked aisle, reroute, evidence. This is stronger than "look at our labels".
- The four missing pieces, as the spine of the pitch and of the build: meaning, identity, accessibility, context.
- The blocked aisle as the reveal. Spatial reasoning is obvious in a second and impossible to fake.
- A route to a **reviewed service position beside the machine**, never the machine centre.
- Evidence states: "AI proposal" and "operator confirmed" are different things and the UI says which.
- An occupancy grid on the floor plane, obstacles inflated by agent width, unobserved areas never treated as free, A* to the waypoint.
- The evaluation list: correct asset selection, routes found, blocked handling, response time, and how much of it was prepared by hand.
- Out of scope: robot simulation, predictive maintenance, pipe connectivity, whole plant understanding.

**Rejecting or replacing.**

| The supplied plan says | What we do instead | Why |
| --- | --- | --- |
| Assume a supplied scan, mesh or Gaussian splat | Build a data adapter and decide at 19:30. If Valmet supplies a scan, load it; if not, our depth pipeline turns venue photos into a cloud | We have not seen any dataset. Architecting around one is how a night is lost |
| 36 to 48 hours | 26 hours to the freeze, 4 people, one sleep block, about 86 person-hours | The event clock, not an estimate |
| SAM 3, with SAM 2 as fallback | Geometry proposals, CLIP zero-shot labels, plate OCR for identity, one-click operator confirmation | SAM 3 checkpoints are gated and SAM 2 is heavy on CPU. The evidence states survive without SAM |
| Render views from the scan, then associate pixels to 3D | Segment the photo directly: every pixel already owns the point it generated, so a mask lifts to a 3D object for free | Fewer moving parts, and it is honest about where the geometry came from |
| A language model API for explanations | Retrieval plus template with citations; the LLM is optional, cached, and off the demo path | No network in the demo, and a citation beats a paraphrase |
| "An impressive industrial scan" | Say which source is on screen: a supplied scan or a captured room standing in for a plant | The one claim a Valmet 3D person will test first |

## 2. The product

| Missing information | What PlantPilot establishes | Where it comes from |
| --- | --- | --- |
| Meaning | this cluster of geometry is a pump, a tank, a valve | geometry classes plus CLIP labels, marked as proposals |
| Identity | this particular pump is P-204 | the printed tag and OCR, confirmed by an operator; the plate is the evidence |
| Accessibility | a person reaches the inspection position through these passages | floor plane, occupancy grid, A*, agent radius |
| Context | this work order and these documents explain the visit | the asset record, the manual corpus, the VMR003 intervals |

The contribution is the join: one asset record that binds a 3D selection, its evidence, its inspection point, its documents and its work order, so a route and an explanation can both be computed from the same object.

## 3. The 120 second demo

| Time | What the judge sees | What it proves |
| --- | --- | --- |
| 0 to 15 s | The scan, unlabelled, rotating. | the starting material |
| 15 to 35 s | Equipment highlights. Select P-204, see its evidence: tag photo, confidence, "operator confirmed". | meaning and identity |
| 35 to 60 s | Pick the inspection request. P-204 lights up, a route appears, distance and clearance shown. | records, equipment and space joined |
| 60 to 80 s | Block an aisle with a click. The route vanishes and a new one appears, longer, around the obstruction. | the reveal: spatial reasoning |
| 80 to 100 s | Follow the route to the waypoint, open the reason and the manual page. | the mission is useful, not just pretty |
| 100 to 120 s | A judge picks another destination or blocks another aisle. | it generalises live |

If the area has only one approach, the blocked case becomes "no route available" with the reason shown, and the demo says so. That is a real result, not a failure.

## 4. What each beat costs

| Beat | Needs | Cost | Risk | Fallback |
| --- | --- | --- | --- | --- |
| scan on screen | cloud or mesh + viewer | 3 h | WebGL on the demo laptop | canvas 2D projection, then isometric SVG |
| labels + identity | proposals, plate OCR, confirm click, asset store | 5 h | proposals are wrong for a machine | ship only operator-confirmed assets and label the rest unconfirmed |
| route | floor plane, grid, inflate, A*, waypoint | 4 h | noisy floor from a photo cloud | reviewed floor polygon drawn once by hand, disclosed |
| blocked aisle | obstacle insert + recompute | 1 h | none, it is the same solver | none needed |
| evidence | corpus retrieval, asset record | 2 h | citation does not match the asset | one static cited card |
| route following | camera path + marker | 2 h | camera work eats Saturday | a cut and a highlighted waypoint |

## 5. The data decision at 19:30

Two branches, one adapter.

1. **Valmet supplies geometry** (scan, mesh, splat, or images with poses). Inspect it in the first hour: format, units, axes, one room, scale sanity. Crop it with Open3D or CloudCompare, convert to the app format, and keep the source file out of the repo.
2. **Valmet supplies nothing.** Photograph the most machine-like room in the venue with the laptop or a phone, and run `make scan`. The room is a stand-in for a plant and every screen that shows it says so.

The app contract does not change: a cloud of points with colours and, where available, triangles; a set of asset records with positions; a walkable floor; waypoints. The source is a field in the metadata, printed on screen.

## 6. Architecture

```
photos or supplied scan
   |
   v
[ingest]  depth + ArUco scale (ours) or file import (theirs)
   |
   v
[geometry]  floor plane, occupancy grid, obstacle inflation
   |
   v
[semantics]  geometry classes -> proposals -> CLIP labels -> plate OCR identity -> operator confirm
   |                                                        |
   v                                                        v
[asset store]  id -> 3D selection, evidence, waypoint, documents, work orders
   |                                   |
   v                                   v
[mission]  pick order -> asset -> route (A*) -> blocks -> reroute
   |                                   |
   v                                   v
[viewer]  three.js            [answer]  retrieval + citations, template, optional cached LLM
```

Key choices: the asset store is JSON on disk (small, inspectable, no migration); the walkable layer is explicit and can be hand-corrected; the planner is pure Python with a deterministic seed; the viewer never computes a route.

## 7. The re-cut schedule, 26 hours

| Gate | Time | Must be true |
| --- | --- | --- |
| G0 | 19:45 | data decision made, one area loads on the demo laptop, WebGL verified |
| G1 | 02:00 | 5 confirmed assets with waypoints, a route to each from one start, viewer flies to the asset |
| G2 | 07:45 | blocked aisle reroutes or reports unreachable, evidence panel cites the manual, all offline |
| G3 | 12:30 | the 120 seconds runs three times in a row, with a judge-chosen destination |
| G4 | 16:00 | evaluation numbers measured, video script locked |
| Freeze | 22:00 | no code changes after this |

Their stage plan of 2h inspect, 6h wire, 12h segmentation, 10h obstructions, rest present maps onto this as: inspect in G0, wire in G1, proposal-to-asset in G2, obstructions and evidence in G2, presentation from G3. The difference is that the stages run in parallel across four people, not one.

Cut order: CLIP labels at 02:00 if they are vague, keeping geometry plus tags; the follow-the-route camera at 12:00, keeping the waypoint highlight; the judge-chosen destination at 12:30 if the UI is not ready; point density down to 50k at any stutter. Never cut: the blocked aisle, the waypoint beside the machine, the evidence citation.

## 8. The four seats

| Seat | Owns | First handover |
| --- | --- | --- |
| A | ingest, depth or import, segmentation proposals, plate identity | one area loads with 5 assets by 22:30 |
| B | floor, grid, A*, obstruction and reroute, waypoints | a route to one asset by 22:30, blockage by 07:45 |
| C | viewer, selection, highlights, camera, the mission UI | scan on screen by 22:30, mission flow by 07:45 |
| D | integration, asset store, evidence panel, evaluation, video, submission | plumbed order to asset by 22:30 |

One writer per file. The lead merges. No automerge.

## 9. What we claim, and how we measure it

- **Correct asset selection** on 5 to 8 destinations from a work order: n correct out of n tried, with the mistakes shown, not hidden.
- **Routes found**: how many of those destinations have a route, and the response time in milliseconds.
- **Blocked handling**: for each aisle blocked, either a new route (and how much longer) or a clear unreachable verdict.
- **Manual preparation**, stated as a number: how many objects were confirmed by hand, how many metres of floor were drawn by hand, how many documents were attached by hand.
- **The demo itself**: three clean runs in a row on the demo laptop.

No claim about predictive maintenance. The alert is simulated and labelled simulated, because a scan cannot establish that a bearing is failing.

## 10. Risks

1. **No supplied data and a boring room.** Mitigation: scout the venue for pipes, cabinets and plant; bring three tagged objects to stage the area; say "stand-in" on screen.
2. **Depth quality on flat walls and glass.** Mitigation: textured views, guided filter, plate tags on the assets that matter.
3. **Semantics confidently wrong.** Mitigation: proposals versus confirmed, visible in the UI, and the demo shows one object going through confirmation rather than a hundred unexplained labels.
4. **WebGL on the demo laptop.** Tested at 19:45, two fallbacks.
5. **One night.** G1 is a working mission without obstructions, so a bad night still ships on-brief.

## 11. Not building

Robot simulation, predictive maintenance, automatic pipe connectivity, whole-plant understanding, VR or AR, LiDAR or photogrammetry capture, a login, a cloud service, an LLM on the answer path.

## 12. Checklist at 19:30

1. Read the full brief in the app. Check it against section 0 and name anything scored that we do not cover.
2. Get the dataset answer: what Valmet provides, in what format, when. If nothing, start the venue capture immediately.
3. Confirm the 120 second sequence out loud, once, with the room.
4. Assign the four seats by name.
5. Freeze contracts: cloud buffer, asset record, route request and response, obstruction event.
6. WebGL test on the demo laptop. Fallback chosen at 19:45.
