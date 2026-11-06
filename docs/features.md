# Features, grouped by how much we need them

P0 is the demo. P1 is the difference between a demo and a product. P2 is only if the gates pass early. P3 is out, and stays out.

The score we build against: 30 percent extraction density, 25 percent navigation and proximity display, 20 percent diagnostics and grounding, 15 percent backend, 10 percent demo clarity. A feature that serves none of those is not a feature.

## P0, the demo dies without these

| # | Feature | Why it is P0 | Owner | Gate |
| --- | --- | --- | --- | --- |
| 1 | Robust splat ingest: filter the defective rows, decimate, render points with size and alpha | there is no demo without the room on screen | A | G0 |
| 2 | Scene-agnostic CLI and pipeline: `make pipeline PLY=... PACK=...`, no room constants | the one-room objection dies here, and it is the 15 percent backend score | A, D | G1 |
| 3 | Object extraction: plane removal, clustering, split oversized components, oriented boxes with a class proposal | the 30 percent beat, and the demo's first impression | A | G1 |
| 4 | Metadata mapping: 30 records to 30 objects, method and confidence, P-005 as the faulty target | space plus meaning, the join the challenge asks for | D | G1 |
| 5 | Floor and occupancy grid derived from the splat | navigation needs a walkable surface, not a hand-drawn plan | B | G1 |
| 6 | A* route to the service position, with length and clearance | the 25 percent beat | B | G1 |
| 7 | Viewer: room, boxes, selection, red highlight on the faulty device | the product surface, and the display of every other beat | C | G1 |
| 8 | Avatar travelling the route, at minimum a simple avatar body sliding along the path, with floor arrows | proves the route means something | C | G1 |
| 9 | Proximity display: nearby objects highlighted with tag, class and state | the second half of the 25 percent criterion | C, D | G2 |
| 10 | Grounded diagnosis panel: evidence IDs, documents, a confidence that drops when a data quality case touches the asset, next safe check | the 20 percent beat | D | G2 |
| 11 | Offline run and a provenance line: which scene, which mapping method | a plant demo that needs Wi-Fi is a liability | all | G2 |
| 12 | Reproducible artifacts from a clean clone once the two supplied files are in `data/supplied/` | the 15 percent backend score | D | G2 |

## P1, should have, and the value is large

| # | Feature | Value | Cost | Cut when |
| --- | --- | --- | --- | --- |
| 1 | Isolate view: lift one framed object out of the room with its card | the visual from Valmet's own demo 1, and honest confidence | 2 h | G3 at 16:00 |
| 2 | Second-scene run on the reference plant, scored against ground truth. If it is cut, the scene-agnostic claim is downgraded in the plan, the README and the pitch | proves the agnostic claim with a number | 1.5 h | G3 at 16:00 |
| 3 | Start and waypoint search: pick the free cells with the best clearance | makes the route robust on any scene | 2 h | G2 at 12:30 |
| 4 | Asset card built from the pack's master data | a real product surface, not a tooltip | 1 h | G2 at 12:30 |
| 5 | Walking animation and follow camera | the avatar moves without it; this is the polish | 2 h | G3 at 16:00 |

## P2, only if the gates pass early

| # | Feature | Value | Cost |
| --- | --- | --- | --- |
| 1 | Area rollup from the pack (its five area names and 30 assets) in the About and the slide, not in 3D | plant-level story without invented geometry | 1 h |
| 2 | Top-down minimap with the route | orientation for a judge | 1 h |
| 3 | Keyboard shortcuts for the demo beats | keeps a live demo on the rails | 0.5 h |
| 4 | Screenshot export for the README | saves a manual step on Sunday | 1 h |
| 5 | Point budget setting for a weaker laptop | safety on unknown hardware | 0.5 h |
| 6 | Work-order draft from the diagnosis | shows the next step in the field workflow | 2 h |

## P3, out, and stays out

Android, an emulator, AR, a 3D Gaussian rasteriser, SAM or CLIP, an LLM on the answer path, mesh reconstruction, interactive rerouting, robot dynamics, physics, a login, a cloud service, invented multi-room geometry. One extra supplied-style scene is allowed, as the generality proof, and only after G2.

## The cut ladder

When time is short, this is the order things leave. It matches the roadmap gates, and it never cuts an acceptance check.

1. The follow camera, keeping the avatar moving on a fixed camera.
2. The walking animation, keeping a simple avatar body that slides along the path.
3. Proximity labels down to the nearest two.
4. The isolate view, and the script selects a nearby asset instead.
5. The second-scene run. The agnostic claim is then downgraded everywhere to "designed for compatible 3DGS PLY inputs, tested on one scene".

Never cut: boxes with class proposals, the 30 mapped records, P-005 turning red with its card, the route arrows, the moving avatar, the diagnosis evidence, the offline run, the provenance line. Those are the acceptance checks.

## Which judge line each feature serves

| Judge line | Features that carry it |
| --- | --- |
| Works and answers the brief | P0 1, 3, 4, 5, 6, 7, 9, 10 |
| Technical quality and feasibility | P0 2, 3, 5, 6, 12; P1 2, 3, 5 |
| Understanding of the system | mapping method, evidence IDs, provenance line, the code path from splat to object |
| Responsible data handling | offline run, synthetic metadata labels, no personal data, no cloud |
| Business value | the mission framing, the route, the diagnosis, training and remote support |

## The submission surface, which is not a feature list

The vote card shows the name, the tagline, the first lines of the About text, the demo video playing inline, the optional pitch deck and the first five Built with chips. Voters can vote without watching the video to the end, so the tagline and the first two sentences do as much work as the demo. Judges read the full About text.

Treat these as P0 copy, not decoration: the tagline on Friday night, the first two sentences by Saturday midday, and the Built with order chosen deliberately because only the first five become chips.

## Rules

- A P0 never gets cut. If a P0 is late, the demo changes shape around it, not without it.
- A P1 that misses its gate becomes P2 automatically. No negotiating at 03:00.
- A P2 can never displace a P1 without the lead naming the P1 it replaces.
- New ideas go to P2 or P3 first. A new idea may not enter P0 after G1.
