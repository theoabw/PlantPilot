"""PlantPilot API. One process, one port, no cloud calls."""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path

import numpy as np

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from . import __version__, corpus, nav, ocr, register
from .models import (
    AssetGraphResponse,
    CloudMetaResponse,
    DiagnosisResponse,
    ExplainRequest,
    ExplainResponse,
    HealthResponse,
    PlantResponse,
    RouteRequest,
    RouteResponse,
    ScanResponse,
    SectionResponse,
)

ROOT = Path(__file__).resolve().parents[4]
DATA = Path(os.environ.get("PLANTPILOT_DATA", ROOT / "data"))
FIXTURES = ROOT / "fixtures"
INDEX_DB = DATA / "index.db"
REGISTER_DB = DATA / "register.db"
PLANT_SPEC = FIXTURES / "plant" / "plant.json"
PLANT_CLOUD = DATA / "plant" / "cloud.npz"
ROUTE_FILE = DATA / "scene" / "route.json"
# The scene artifacts the room view reads. They are written by make scene,
# make objects, make map and make splat-asset, never committed. PLANTPILOT_SCENE
# and PLANTPILOT_SPLAT point the room at another capture, for example
# PLANTPILOT_SCENE=data/equipment PLANTPILOT_SPLAT=data/viewer/equipment.ply.
SCENE_DIR = Path(os.environ.get("PLANTPILOT_SCENE", DATA / "scene"))
OBJECTS_FILE = SCENE_DIR / "objects.json"
ASSETS_FILE = SCENE_DIR / "assets.json"
MAPPED_FILE = SCENE_DIR / "mapped.json"
ROUTE_ARTIFACT = SCENE_DIR / "route.json"
DIAGNOSIS_FILE = SCENE_DIR / "diagnosis.json"
SPLAT_ASSET = Path(os.environ.get("PLANTPILOT_SPLAT", DATA / "viewer" / "room.ply"))

app = FastAPI(title="PlantPilot", version=__version__)


def _ensure_register() -> None:
    if not REGISTER_DB.exists():
        csv_path = FIXTURES / "register" / "assets.csv"
        if csv_path.exists():
            register.build(REGISTER_DB, csv_path)


def _actions() -> list[dict]:
    for path in (DATA / "vmr003_actions.csv", FIXTURES / "vmr003_actions.csv"):
        if path.exists():
            with path.open(newline="", encoding="utf-8") as fh:
                return list(csv.DictReader(fh))
    return []


# The demo asset is a NelesAce control valve whose limit switch inspection is the
# action we track. Any other part can be asked for by name; the table is the document's.
DEMO_PART = "Limit switches"


def _next_action(family: str, part: str = DEMO_PART) -> dict | None:
    rows = _actions()
    for row in rows:
        if row.get("family") == family and row.get("part") == part:
            return row
    for row in rows:
        if row.get("family") == family and "1 year" in row.get("interval", ""):
            return row
    return rows[0] if rows else None


_ensure_register()


@app.get("/api/health")
def health() -> HealthResponse:
    return {
        "ok": True,
        "corpus_sections": corpus.count(INDEX_DB),
        "assets": register.count(REGISTER_DB),
        "version": __version__,
    }


@app.get("/api/diagnosis", response_model=DiagnosisResponse)
def diagnosis() -> DiagnosisResponse:
    if not DIAGNOSIS_FILE.exists():
        return {
            "available": False,
            "reason": "no diagnosis generated, run make diagnose",
        }
    try:
        return {"available": True, **json.loads(DIAGNOSIS_FILE.read_text(encoding="utf-8"))}
    except (OSError, json.JSONDecodeError) as exc:
        return {"available": False, "reason": f"failed to read diagnosis.json: {exc}"}


@app.post("/api/scan")
async def scan(
    frame: UploadFile = File(...), symptom: str = Form("cavitation damage")
) -> ScanResponse:
    data = await frame.read()
    result = ocr.analyze(data)
    empty = {"asset": None, "sections": [], "action": None}
    if not result["gate"]["ok"] or not result["plate"]:
        return {**result, **empty}

    fields = result["plate"]["fields"]
    family = result["plate"]["family"]
    dn = fields.get("dn", "")
    pn = fields.get("pn", "")
    asset = register.match_plate(REGISTER_DB, family, dn, pn, fields.get("serial"), fields.get("type"))

    query = " ".join(p for p in [family, "valve", symptom] if p)
    sections = corpus.search(INDEX_DB, query, limit=3)
    return {
        "gate": result["gate"],
        "plate": result["plate"],
        "asset": asset,
        "sections": sections,
        "action": _next_action(family),
    }


@app.get("/api/assets/{tag}")
def asset(tag: str) -> AssetGraphResponse:
    row = register.get(REGISTER_DB, tag)
    if not row:
        return {"asset": None, "neighbours": [], "shared_spares": []}
    return {
        "asset": row,
        "neighbours": register.neighbours(REGISTER_DB, tag),
        "shared_spares": register.shared_spares(REGISTER_DB, tag),
    }


@app.get("/api/section/{sid}")
def section(sid: str) -> SectionResponse:
    return {"section": corpus.section(INDEX_DB, sid)}


def _plant_spec() -> dict:
    return json.loads(PLANT_SPEC.read_text())


def _start_point(spec: dict) -> list[float]:
    door = spec["door"]
    return [round((door["x0"] + door["x1"]) / 2.0, 3), round(door["z"] + 0.8, 3)]


@app.get("/api/plant", response_model_exclude_unset=True)
def plant() -> PlantResponse:
    spec = _plant_spec()
    return {
        "name": spec["name"],
        "note": spec["note"],
        "source": "synthetic reference plant",
        "area": spec["area"],
        "door": spec["door"],
        "start": _start_point(spec),
        "assets": spec["assets"],
        "aisles": spec["aisles"],
        "blockers": spec["blockers"],
    }


@app.get("/api/cloud/meta", response_model_exclude_unset=True)
def cloud_meta() -> CloudMetaResponse:
    if not PLANT_CLOUD.exists():
        return {"available": False, "count": 0, "source": "synthetic reference plant"}
    data = np.load(PLANT_CLOUD)
    return {
        "available": True,
        "count": int(len(data["points"])),
        "layout": "float32 xyz triples, then uint8 rgb triples",
        "source": "synthetic reference plant",
    }


@app.get(
    "/api/cloud",
    response_class=Response,
    responses={
        200: {"content": {"application/octet-stream": {}}},
        404: {"description": "No cloud has been generated", "content": {"text/plain": {}}},
    },
)
def cloud() -> Response:
    if not PLANT_CLOUD.exists():
        return Response(status_code=404, content=b"no cloud generated, run make plant")
    data = np.load(PLANT_CLOUD)
    points = np.ascontiguousarray(data["points"], dtype=np.float32)
    colours = np.ascontiguousarray(data["colors"], dtype=np.uint8)
    return Response(content=points.tobytes() + colours.tobytes(), media_type="application/octet-stream")


def _plant_asset(asset_id: str) -> dict | None:
    for asset in _plant_spec()["assets"]:
        if asset["id"] == asset_id:
            return asset
    return None


def _due(asset: dict) -> dict:
    from datetime import date, timedelta

    years = 4 if "4" in asset.get("interval", "") else 1
    last = date.fromisoformat(asset["last_service"])
    due = last + timedelta(days=365 * years)
    today = date(2026, 11, 6)
    return {
        "interval": asset.get("interval", ""),
        "last_service": asset.get("last_service", ""),
        "due": due.isoformat(),
        "due_in_days": (due - today).days,
        "symptom": asset.get("symptom", "inspection"),
    }


@app.post("/api/explain", response_model_exclude_unset=True)
def explain(payload: ExplainRequest) -> ExplainResponse:
    """The work order plus the cited reason: a section, a page and the next action."""
    asset_id = payload.asset_id or payload.to
    asset = _plant_asset(str(asset_id)) if asset_id else None
    if not asset:
        return {"asset": None, "reason": f"unknown asset {asset_id}", "sections": [], "action": None}
    order = _due(asset)
    symptom = payload.symptom or order["symptom"]
    query = " ".join(p for p in [symptom, asset.get("kind", ""), "valve", "maintenance"] if p)
    sections = corpus.search(INDEX_DB, query, limit=2)
    action = _next_action(ocr.family_of({"type": asset.get("type", "")}) if asset.get("type") else "NelesAce")
    return {"asset": asset, "request": {**order, "symptom": symptom}, "sections": sections, "action": action}


@app.get("/api/route", response_model_exclude_unset=True)
def get_route() -> RouteResponse:
    if ROUTE_FILE.exists():
        try:
            return json.loads(ROUTE_FILE.read_text())
        except Exception as e:
            return {"reachable": False, "reason": f"failed to read route.json: {e}", "path": []}
    return {"reachable": False, "reason": "no route generated, run make route", "path": []}


@app.post("/api/route", response_model_exclude_unset=True)
def route(payload: RouteRequest) -> RouteResponse:
    spec = _plant_spec()
    start = payload.start or _start_point(spec)
    by_id = {a["id"]: a for a in spec["assets"]}
    goal = payload.goal
    target_id = payload.to
    if goal is None and target_id:
        asset = by_id.get(target_id)
        if not asset:
            return {"reachable": False, "reason": f"unknown asset {target_id}", "path": []}
        goal = asset["waypoint"]
    if goal is None:
        return {"reachable": False, "reason": "give a goal point or an asset id", "path": []}
    agent = payload.agent_radius_m
    if agent is None:
        agent = nav.DEFAULT_AGENT_RADIUS_M
    result = nav.plan(spec, start, goal, payload.blockers or [], agent)
    result["start"] = [round(float(v), 3) for v in start]
    result["goal"] = [round(float(v), 3) for v in goal]
    result["agent_radius_m"] = agent
    return result


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
