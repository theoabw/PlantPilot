"""Fieldplate API. One process, one port, no cloud calls."""

from __future__ import annotations

import csv
import os
from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.staticfiles import StaticFiles

from . import __version__, corpus, ocr, register

ROOT = Path(__file__).resolve().parents[4]
DATA = Path(os.environ.get("FIELDPLATE_DATA", ROOT / "data"))
FIXTURES = ROOT / "fixtures"
INDEX_DB = DATA / "index.db"
REGISTER_DB = DATA / "register.db"

app = FastAPI(title="Fieldplate", version=__version__)


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
def health() -> dict:
    return {
        "ok": True,
        "corpus_sections": corpus.count(INDEX_DB),
        "assets": register.count(REGISTER_DB),
        "version": __version__,
    }


@app.post("/api/scan")
async def scan(frame: UploadFile = File(...), symptom: str = Form("cavitation damage")) -> dict:
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
def asset(tag: str) -> dict:
    row = register.get(REGISTER_DB, tag)
    if not row:
        return {"asset": None, "neighbours": [], "shared_spares": []}
    return {
        "asset": row,
        "neighbours": register.neighbours(REGISTER_DB, tag),
        "shared_spares": register.shared_spares(REGISTER_DB, tag),
    }


@app.get("/api/section/{sid}")
def section(sid: str) -> dict:
    return {"section": corpus.section(INDEX_DB, sid)}


_web = ROOT / "app" / "web" / "dist"
if _web.exists():
    app.mount("/", StaticFiles(directory=str(_web), html=True), name="web")
