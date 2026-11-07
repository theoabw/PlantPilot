"""PlantPilot API. One process, one port, no cloud calls."""

from __future__ import annotations

import json
import re
import os
import threading
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from pydantic import BaseModel
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import __version__, nav

ROOT = Path(__file__).resolve().parents[4]
DATA = Path(os.environ.get("PLANTPILOT_DATA", ROOT / "data"))
# The scene artifacts the room view reads. They are written by make scene,
# make objects, make map and make splat-asset, never committed. PLANTPILOT_SCENE
# and PLANTPILOT_SPLAT point the room at another capture, for example
# PLANTPILOT_SCENE=data/equipment PLANTPILOT_SPLAT=data/viewer/equipment.ply.
SCENE_DIR = Path(os.environ.get("PLANTPILOT_SCENE", DATA / "scene"))
OBJECTS_FILE = SCENE_DIR / "objects.json"
ASSETS_FILE = SCENE_DIR / "assets.json"
ANCHORS_FILE = SCENE_DIR / "anchors.json"
MAPPED_FILE = SCENE_DIR / "mapped.json"
ROUTE_ARTIFACT = SCENE_DIR / "route.json"
DIAGNOSIS_FILE = SCENE_DIR / "diagnosis.json"
SPLAT_ASSET = Path(os.environ.get("PLANTPILOT_SPLAT", DATA / "viewer" / "room.ply"))
FILTER_DIR = Path(os.environ.get("PLANTPILOT_FILTERS", DATA / "viewer" / "filters" / SCENE_DIR.name))
MESH_DIR = Path(os.environ.get("PLANTPILOT_MESHES", DATA / "objects" / "meshes" / SCENE_DIR.name))
OBJECT_SPLAT_DIR = Path(os.environ.get("PLANTPILOT_OBJECT_SPLATS", DATA / "objects" / "splats" / SCENE_DIR.name))
FILTER_NAMES = ("height", "normals", "edges_base", "semantics", "anchors_overlay")

# The body heights the viewer's robots plan at: the compact AMR, the cargo AMR, and
# the humanoid standing and crouched. A robot's layers take seconds to build the
# first time, and a replan holds the robot still until its answer arrives.
ROBOT_BODY_HEIGHTS_M = (0.55, 0.9, 1.35, 0.95)


def warm_route_layers() -> None:
    """Build each robot height's occupancy layers, so no replan waits for them."""
    scene = SCENE_DIR / "scene.npz"
    if not (scene.exists() and OBJECTS_FILE.exists() and MAPPED_FILE.exists()):
        return
    for height in ROBOT_BODY_HEIGHTS_M:
        nav.build_route(
            scene_path=scene,
            objects_path=OBJECTS_FILE,
            mapped_path=MAPPED_FILE,
            agent_height_m=height,
        )


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # In the background, so the room view opens while the layers build. A failure
    # surfaces in the log and leaves the routes building on demand, as they would.
    threading.Thread(target=warm_route_layers, name="warm-route-layers", daemon=True).start()
    yield


app = FastAPI(title="PlantPilot", version=__version__, lifespan=lifespan)


@app.get("/api/diagnosis")
def diagnosis() -> dict:
    if not DIAGNOSIS_FILE.exists():
        return {
            "available": False,
            "reason": "no diagnosis generated, run make diagnose",
        }
    try:
        return {"available": True, **json.loads(DIAGNOSIS_FILE.read_text(encoding="utf-8"))}
    except (OSError, json.JSONDecodeError) as exc:
        return {"available": False, "reason": f"failed to read diagnosis.json: {exc}"}


# The scene artifacts are written by the pipeline, so the API documents their
# shape without modelling every field of every version.
_ARTIFACT_SCHEMA = {
    "type": "object",
    "properties": {
        "artifact": {"type": "string"},
        "version": {"type": "integer"},
        "source": {"type": "object"},
        "floor": {"type": "object"},
        "counts": {"type": "object"},
        "objects": {"type": "array", "items": {"type": "object"}},
        "mappings": {"type": "array", "items": {"type": "object"}},
        "path": {"type": "array", "items": {"type": "array", "items": {"type": "number"}}},
        "reachable": {"type": "boolean"},
    },
}
_ARTIFACT_RESPONSES = {200: {"content": {"application/json": {"schema": _ARTIFACT_SCHEMA}}}}


@app.get("/api/scene/objects", responses=_ARTIFACT_RESPONSES)
def scene_objects() -> dict:
    """The framed objects of the supplied capture, as make objects writes them."""
    if not OBJECTS_FILE.exists():
        raise HTTPException(status_code=404, detail="no objects artifact, run make objects")
    return json.loads(OBJECTS_FILE.read_text())


@app.get("/api/scene/anchors", responses=_ARTIFACT_RESPONSES)
def scene_anchors() -> dict:
    """The reviewed anchor layer of the capture, from make anchors."""
    if not ANCHORS_FILE.exists():
        raise HTTPException(status_code=404, detail="no anchors artifact, run make anchors")
    return json.loads(ANCHORS_FILE.read_text())


@app.get("/api/scene/assets", responses=_ARTIFACT_RESPONSES)
def scene_assets() -> dict:
    """The coherent equipment assets of the capture, from make assets."""
    if not ASSETS_FILE.exists():
        raise HTTPException(status_code=404, detail="no assets artifact, run make assets")
    return json.loads(ASSETS_FILE.read_text())


@app.get("/api/scene/mapped", responses=_ARTIFACT_RESPONSES)
def scene_mapped() -> dict:
    """The builder assets mapped onto the extracted objects, from make map."""
    if not MAPPED_FILE.exists():
        raise HTTPException(status_code=404, detail="no mapping artifact, run make map")
    return json.loads(MAPPED_FILE.read_text())


@app.get("/api/scene/route", responses=_ARTIFACT_RESPONSES)
def scene_route() -> dict:
    """The navigation route for the supplied scene, from make route."""
    if not ROUTE_ARTIFACT.exists():
        raise HTTPException(status_code=404, detail="no route artifact, run make route")
    return json.loads(ROUTE_ARTIFACT.read_text())


@app.get("/api/scene/filters", responses=_ARTIFACT_RESPONSES)
def scene_filters() -> dict:
    """The baked information channels of the capture, from make filter-assets."""
    path = FILTER_DIR / "filters.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="no filter assets, run make filter-assets")
    return json.loads(path.read_text())


@app.get("/api/scene/object-splats", responses=_ARTIFACT_RESPONSES)
def scene_object_splats() -> dict:
    """The per-object splat assets of the reviewed anchors."""
    path = OBJECT_SPLAT_DIR / "manifest.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="no object splats, run make object-splats")
    return json.loads(path.read_text())


@app.get(
    "/api/object-splat/{anchor_id}",
    responses={200: {"content": {"application/octet-stream": {"schema": {"type": "string", "format": "binary"}}}}},
)
def object_splat(anchor_id: str) -> FileResponse:
    """One reviewed object's own gaussians as a core-property PLY."""
    if not re.fullmatch(r"AN-[0-9a-f]{8}", anchor_id):
        raise HTTPException(status_code=404, detail="unknown object splat")
    path = OBJECT_SPLAT_DIR / f"{anchor_id}.ply"
    if not path.exists():
        raise HTTPException(status_code=404, detail="no object splat, run make object-splats")
    return FileResponse(path, media_type="application/octet-stream", headers={"Cache-Control": "no-cache"})


class RerouteRequest(BaseModel):
    """Transient obstacles for a live replan, in scene plane coordinates."""

    blockers: list[list[float]] = []
    start: list[float] | None = None
    agent_radius_m: float = 0.20
    agent_height_m: float = 0.55
    standing_height_m: float | None = None
    target: list[float] | None = None


@app.post("/api/scene/reroute", responses=_ARTIFACT_RESPONSES)
def scene_reroute(payload: RerouteRequest) -> dict:
    """Replan the route around transient obstacles from the robot's position."""
    if not (SCENE_DIR / "scene.npz").exists() or not OBJECTS_FILE.exists() or not MAPPED_FILE.exists():
        raise HTTPException(status_code=404, detail="reroute needs scene, objects and mapping; run make pipeline")
    blockers = [[float(value) for value in rect] for rect in payload.blockers if len(rect) == 4]
    start = None
    if payload.start and len(payload.start) >= 2:
        start = (float(payload.start[0]), float(payload.start[1]))
    try:
        return nav.build_route(
            scene_path=SCENE_DIR / "scene.npz",
            objects_path=OBJECTS_FILE,
            mapped_path=MAPPED_FILE,
            output_path=None,
            blockers=blockers,
            start_override=start,
            agent_radius_m=float(payload.agent_radius_m),
            agent_height_m=float(payload.agent_height_m),
            standing_height_m=(
                float(payload.standing_height_m) if payload.standing_height_m is not None else None
            ),
            goal_override=(
                (float(payload.target[0]), float(payload.target[1]))
                if payload.target and len(payload.target) >= 2
                else None
            ),
        )
    except nav.RouteInputError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.get("/api/scene/meshes", responses=_ARTIFACT_RESPONSES)
def scene_meshes() -> dict:
    """The per-object meshes of the reviewed anchors, from make object-meshes."""
    path = MESH_DIR / "manifest.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="no object meshes, run make object-meshes")
    return json.loads(path.read_text())


@app.get(
    "/api/mesh/{anchor_id}",
    responses={200: {"content": {"application/octet-stream": {"schema": {"type": "string", "format": "binary"}}}}},
)
def object_mesh(anchor_id: str) -> FileResponse:
    """One object mesh as a binary PLY with vertex colours."""
    if not re.fullmatch(r"AN-[0-9a-f]{8}", anchor_id):
        raise HTTPException(status_code=404, detail="unknown object mesh")
    path = MESH_DIR / f"{anchor_id}.ply"
    if not path.exists():
        raise HTTPException(status_code=404, detail="no object mesh, run make object-meshes")
    return FileResponse(path, media_type="application/octet-stream", headers={"Cache-Control": "no-cache"})


@app.get("/api/filter/contours", responses=_ARTIFACT_RESPONSES)
def filter_contours() -> dict:
    """The thin contour overlay of the capture, from make filter-assets."""
    path = FILTER_DIR / "contours.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="no contour asset, run make filter-assets")
    return json.loads(path.read_text())


@app.get(
    "/api/filter/{name}",
    responses={200: {"content": {"application/octet-stream": {"schema": {"type": "string", "format": "binary"}}}}},
)
def filter_asset(name: str) -> FileResponse:
    """One baked information channel as a gaussian PLY for the viewer."""
    if name not in FILTER_NAMES:
        raise HTTPException(status_code=404, detail=f"unknown filter {name}")
    path = FILTER_DIR / f"{name}.ply"
    if not path.exists():
        raise HTTPException(status_code=404, detail="no filter asset, run make filter-assets")
    return FileResponse(path, media_type="application/octet-stream", headers={"Cache-Control": "no-cache"})


@app.get(
    "/api/splat",
    responses={200: {"content": {"application/octet-stream": {"schema": {"type": "string", "format": "binary"}}}}},
)
def splat_asset() -> FileResponse:
    """The sanitised capture as a gaussian splat PLY for the browser renderer."""
    if not SPLAT_ASSET.exists():
        raise HTTPException(status_code=404, detail="no splat asset, run make splat-asset")
    return FileResponse(
        SPLAT_ASSET,
        media_type="application/octet-stream",
        filename="room.ply",
        headers={"Cache-Control": "no-cache"},
    )


_web = ROOT / "app" / "web" / "dist"
if _web.exists():
    app.mount("/", StaticFiles(directory=str(_web), html=True), name="web")
