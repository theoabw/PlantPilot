# PlantPilot

Inspection missions in a scanned plant.

Built for the **SinceAI Hackathon 2026**, Valmet challenge: a digital plant that "understands where machines are, what they are, how people or robots could move between them and which equipment needs attention".

This is the working tree at the start of the build. The capture, OCR, corpus and register layers work and are tested; the mission flow (work order, route, blocked aisle, reroute) is being built during the event.

## The problem

A work order names a machine, not a place. A technician has to find P-204 inside a plant, work out how to reach the inspection point, and then explain why the visit is needed. A 3D scan of the plant looks impressive and answers none of that on its own. The description says it plainly: today's captures "lack the meaning needed for intelligent action".

## Solution

PlantPilot turns a capture into four things a mission needs:

- **Meaning**: geometry becomes equipment. Points are classified as floor, wall, pipe, pump, tank or valve, by geometric rules and image labels, and every label is marked as a proposal until a person confirms it.
- **Identity**: a printed tag on the machine is read by OCR and matched to the asset register. A tagged machine is certain; an untagged one is a hypothesis, and the interface says which.
- **Accessibility**: the floor becomes an occupancy grid, obstacles are inflated by the width of the person or cart, and A* computes a route to a reviewed inspection position beside the machine, never to its centre. Block an aisle and the route is recomputed or reported unreachable.
- **Context**: the asset record joins the work order, the manual section with its page anchor, and the service interval, so the answer to "why this visit" is cited rather than asserted.

## Demo path

1. A scan of the area, unlabelled, rotating.
2. Equipment highlights. Select P-204 and see its evidence: the tag, the OCR, the confirmation.
3. Pick the inspection request. The machine lights, a route appears with distance and clearance.
4. Block an aisle with a click. The route disappears and a new one is computed around it.
5. Follow the route to the inspection position, then open the reason and the manual page.
6. A judge picks another destination or blocks another aisle.

## Setup

Requirements: Python 3.12 or newer, [uv](https://docs.astral.sh/uv/), Node 20 or newer, `poppler-utils`, Tesseract 5.

```bash
uv sync                 # Python environment
make models             # monocular depth model, 27 MB, once
make corpus             # the two public Valmet PDFs into data/ and the local index
make register           # the synthetic asset register
make plant              # the synthetic reference plant, points plus ground truth
make scan PHOTO=path/to/room.jpg   # photo to metric point cloud
make demo               # http://127.0.0.1:8000
```

Front end development: `make web` runs Vite on 5173 and proxies `/api` to 8000. `make web-build` writes `app/web/dist`, which `make demo` serves. Tests: `make test`. Submission hygiene: `make check`. Printable tags and a scale card: `make plates`.

No API keys are required. `.env.example` documents the one optional override.

## Technology

All open source, all local, nothing on the network at demo time.

| Layer | Tool | Licence |
| --- | --- | --- |
| Monocular depth | Depth Anything V2 Small, int8 ONNX | Apache-2.0 |
| Image processing | OpenCV (ArUco, guided filter, calibration) | Apache-2.0 |
| Inference | ONNX Runtime | MIT |
| Backend | Python, FastAPI, SQLite FTS5 | MIT, Apache-2.0, public domain |
| Geometry and planning | numpy, scipy, A* on an occupancy grid | BSD |
| Viewer | React, Vite, three.js | MIT |

Data: the Valmet *Flow control manual* (6th edition) and *VMR003* service recommendation, both public PDFs. Pre-existing before the event and declared in the submission: the two document fetches, the scaffold, the table of contents parser probe and the capture module.

## Data and licences

- The Valmet documents are copyright Valmet, all rights reserved. `make corpus` downloads them into `data/`, which is gitignored. The repository ships section ids, titles, pages and quotes of one to two lines only.
- The asset register, tag text and service intervals are synthetic. Every printed tag carries `SYNTHETIC DEMO ASSET`.
- Our code is MIT, see [LICENCE](LICENCE).

## What is real and what is not

| | |
| --- | --- |
| Real | the photographs, the depth model, the guided filter, the ArUco scale, the point cloud, the floor and occupancy grid, the routes, the OCR, the corpus, the page anchors, the timing, the offline run |
| Synthetic | the asset register, tag text, service intervals, the work orders, and the reference plant geometry in `fixtures/plant/plant.json` when it is used. The screen always says which source is loaded |
| Not attempted | LiDAR or photogrammetry capture, physics simulation, robot control, a multi-room twin, predictive maintenance |

## Limitations

- Semantics are proposals until confirmed. The interface shows the difference and the README does not blur it.
- Depth on flat white walls and glass is weak; textual views and tagged assets carry the demo.
- The walkable floor may be reviewed and corrected by hand. If it is, the evaluation reports it as manual preparation.
- The alert behind a work order is simulated and labelled simulated. A scan cannot establish that a bearing is failing.
- Routes are for a person or a cart on one floor, not a robot with dynamics.

## Repository layout

```
app/server/      FastAPI app: corpus, OCR, register, capture
app/web/         React, Vite and three.js viewer
scripts/         corpus, register, plates, photo scan, proof summary
fixtures/        committed and small: register CSV, section sample, action sample
proof/           trials.csv and the metrics the README and the video quote
docs/            the plan, the roadmap and the workflow rules
```

Repository: <https://github.com/theoabw/SinceAI-2026>
