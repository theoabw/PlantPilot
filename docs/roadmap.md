# Proposal: static scene pipeline and Three.js client

Status: the no-HTTP variant was not built. This page is a considered
alternative for a post-event refactor, kept so the reasoning is not lost. The
demonstration path shipped: the FastAPI service plus the Spark room view
described in `README.md`, with the pipeline stages in
`app/server/src/plantpilot/` and the commands in `Makefile`.

If built, this proposal would replace the FastAPI-based plan with an offline
scene pipeline plus a Three.js client that loads generated scene geometry and
semantic data directly, with no HTTP service on the demo path.

| Piece | State | Verified by |
| --- | --- | --- |
| Supplied scene | `Industrial Boiler Room.ply`, 1.5 M declared, 502,483 sane rows, up axis `-y`, dense core about 9 by 4 by 2.5 in file units (assumed metres until the door-height check) | measured with numpy on Friday evening; projections checked |
| Supplied pack | 30 assets, 4,320 telemetry rows (the 3-day sample sheet), 1,000 events, 300 work orders, 38 documents, 120 data quality cases | converted to text and read Friday 19:50 |
| Faulty target | P-005 (ASSET-017), pump, fouling, health 44, high urgency | `Current_State` |
| Reusable code | `Grid`, `astar`, inflation, clearance in `nav.py`; FastAPI shape in `main.py`; viewer shell in `app/web/` | read Friday 19:55 |
| Seat A extraction | `make scene` ingests the delivered file and `make objects` frames 122 objects: 1,506,136 declared, 502,483 sane, largest object 1.5 percent, extraction 3.71 s | measured Saturday; artifact shape in [scene-artifacts.md](scene-artifacts.md) |
| Second scene | a measured second-scene run on the reference plant: 141,575 points, effective voxel 0.058 m from a measured 0.042 m spacing, 62 objects framed, 10 of 10 assets framed against ground truth, PASS | measured Friday 21:10; the plan's generality claim was supported by a check, not only designed |
| Off demo path | printed plates, OCR identity, register, photo capture, public PDF corpus, the reference plant fixture | the new rubric names none of them; those stages were later deleted from the repository |
| Stale docs | `README.md`, `docs/video-script.md` and `docs/submission-copy.md` described the synthetic-plant product | the README and the video script were rewritten against the splat demo; `docs/submission-copy.md` still carries the pre-pivot story and is the next rewrite |
