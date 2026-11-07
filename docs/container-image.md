# Container image

> One image serves the built room view and every API route. What it holds, what
> it expects mounted beside it, and how to run it. Where this page and the
> Dockerfile disagree, the Dockerfile is correct.

```bash
docker build -t plantpilot .
docker run --rm -p 8000:8000 -v "$PWD/data:/app/data:ro" plantpilot
```

Then open <http://127.0.0.1:8000>. The image carries a `HEALTHCHECK` that asks
for the built room view, so `docker ps` reports whether the process is serving.

Two probes answer different questions. The room view is up when `/` answers
200, and the mount is right when `/api/scene/objects` answers 200 as well.

## What the image holds

Two stages. The first runs the same `npm ci` and `npm run build` that CI runs,
and produces `app/web/dist`. The second installs the locked Python dependencies
with `uv sync --locked --no-dev` and copies `fixtures/`, so one uvicorn process
serves both the room view and the API.

Tesseract and poppler are installed in the runtime stage because the scan and
corpus paths shell out to them. CI installs the same pair, so the container
behaves like the environment the tests run in.

The scene artifacts are not in the image. They are supplied and generated data
(see [scene-artifacts.md](scene-artifacts.md)), they are large, and they change
without the code changing. The image mounts them at `/app/data` instead.

## What the mount must hold

Paths below are relative to the mounted `data/`, with the default capture. Every
row is optional at startup: a missing file turns off what reads it, and the room
view says what it could not load.

| Path | Written by | Needed for |
| --- | --- | --- |
| `equipment/scene.npz` | `make scene` | route planning, including the replan the viewer asks for when a drive starts |
| `equipment/objects.json` | `make objects` | room view, route, mapping |
| `equipment/mapped.json` | `make map` | room view, route, diagnosis |
| `equipment/assets.json` | `make assets` | the equipment instances the viewer lists |
| `equipment/anchors.json` | `make anchors` | the reviewed anchor layer |
| `equipment/route.json` | `make route` | the initial route |
| `equipment/diagnosis.json` | `make diagnose` | the arrival card |
| `viewer/equipment.ply` | `make splat-asset` | the capture the browser draws |
| `viewer/filters/equipment/` | `make filter-assets` | the information channels |
| `objects/splats/equipment/` | `make object-splats` | the object atlas |
| `objects/meshes/equipment/` | `make object-meshes` | the object silhouettes |

Most rows are optional: a 404 leaves that layer out, and the page says what it
could not load. `scene.npz` is the row that bites. Without it the room view
still draws and the mission card still appears, but pressing Send robot leaves
the robot standing still: the viewer replans from the robot's position on every
drive, and the planner answers 404 when the scene is missing.

## Pointing it at another capture

The image defaults to the complete capture the organisers re-uploaded. Set both
variables to serve the capture named in the brief instead, using the layout the
Makefile writes for it:

```bash
docker run --rm -p 8000:8000 -v "$PWD/data:/app/data:ro" \
  -e PLANTPILOT_SCENE=data/scene \
  -e PLANTPILOT_SPLAT=data/viewer/boiler.ply \
  plantpilot
```

`PLANTPILOT_FILTERS`, `PLANTPILOT_MESHES` and `PLANTPILOT_OBJECT_SPLATS` follow
the scene directory name by default, so a capture laid out like the Makefile's
needs only those two variables.

## Serving it on a public name

That configuration is not in this repository. The image publishes no host port,
so a reverse proxy on the serving host reaches it over a shared Docker network
and owns the name, the certificate and the access rules.
