"""Convert the builder workbook into the local pack artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from zipfile import ZipFile
from xml.etree import ElementTree as ET

MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
NS = {"m": MAIN_NS, "r": REL_NS}

TABLE_SHEETS = {
    "Asset_Master": "asset_master",
    "Scene_Anchors": "scene_anchors",
    "Current_State": "current_state",
    "Telemetry_Sample_3d": "telemetry",
    "Alarms_Events": "alarms_events",
    "Maintenance_History": "maintenance_history",
    "Historical_Service_Cases": "historical_service_cases",
    "Knowledge_Docs": "knowledge_docs",
    "RAG_Corpus_Index": "rag_corpus_index",
    "Data_Quality": "data_quality",
}


class PackError(ValueError):
    """The workbook does not contain the expected builder-pack structure."""


def _column_index(reference: str) -> int:
    letters = re.match(r"[A-Z]+", reference)
    if not letters:
        raise PackError(f"invalid spreadsheet cell reference {reference!r}")
    index = 0
    for letter in letters.group():
        index = index * 26 + ord(letter) - ord("A") + 1
    return index - 1


def _shared_strings(zfile: ZipFile) -> list[str]:
    try:
        root = ET.fromstring(zfile.read("xl/sharedStrings.xml"))
    except KeyError:
        return []
    return [
        "".join(node.text or "" for node in item.iter(f"{{{MAIN_NS}}}t"))
        for item in root.findall("m:si", NS)
    ]


def _cell_value(cell: ET.Element, shared: list[str]) -> str | int | float | bool:
    value = cell.find("m:v", NS)
    raw = value.text if value is not None else ""
    cell_type = cell.attrib.get("t")
    if cell_type == "s":
        try:
            return shared[int(raw)]
        except (ValueError, IndexError) as exc:
            raise PackError(f"invalid shared-string index {raw!r}") from exc
    if cell_type == "inlineStr":
        return "".join(node.text or "" for node in cell.iter(f"{{{MAIN_NS}}}t"))
    if cell_type == "b":
        return raw == "1"
    if raw == "":
        return ""
    try:
        number = float(raw)
    except ValueError:
        return raw
    return int(number) if number.is_integer() else number


def _sheet_targets(zfile: ZipFile) -> dict[str, str]:
    workbook = ET.fromstring(zfile.read("xl/workbook.xml"))
    relationships = ET.fromstring(zfile.read("xl/_rels/workbook.xml.rels"))
    targets = {
        rel.attrib["Id"]: rel.attrib["Target"].lstrip("/")
        for rel in relationships.findall(f"{{{PKG_REL_NS}}}Relationship")
    }
    result: dict[str, str] = {}
    sheets = workbook.find("m:sheets", NS)
    if sheets is None:
        raise PackError("workbook has no sheets")
    for sheet in sheets:
        target = targets[sheet.attrib[f"{{{REL_NS}}}id"]]
        result[sheet.attrib["name"]] = target if target.startswith("xl/") else f"xl/{target}"
    return result


def read_sheet(zfile: ZipFile, target: str, shared: list[str]) -> list[dict[str, object]]:
    root = ET.fromstring(zfile.read(target))
    rows: list[list[object]] = []
    for row in root.findall(".//m:sheetData/m:row", NS):
        cells = {}
        for cell in row.findall("m:c", NS):
            cells[_column_index(cell.attrib["r"])] = _cell_value(cell, shared)
        if cells:
            width = max(cells) + 1
            rows.append([cells.get(index, "") for index in range(width)])
    if not rows:
        return []
    headers = [str(value).strip() for value in rows[0]]
    if not any(headers):
        return []
    return [
        {
            header: row[index] if index < len(row) else ""
            for index, header in enumerate(headers)
            if header
        }
        for row in rows[1:]
        if any(value != "" for value in row)
    ]


def _merge_assets(tables: dict[str, list[dict[str, object]]]) -> list[dict[str, object]]:
    merged: dict[str, dict[str, object]] = {}
    for table_name in ("asset_master", "scene_anchors", "current_state"):
        for row in tables[table_name]:
            asset_id = str(row.get("asset_id", ""))
            if asset_id:
                merged.setdefault(asset_id, {}).update(row)
    return sorted(merged.values(), key=lambda row: str(row.get("asset_id", "")))


def build_pack(workbook: Path, output: Path) -> dict[str, object]:
    workbook = Path(workbook)
    if not workbook.exists():
        raise PackError(f"no builder pack at {workbook}")
    with ZipFile(workbook) as zfile:
        targets = _sheet_targets(zfile)
        shared = _shared_strings(zfile)
        missing = sorted(set(TABLE_SHEETS) - set(targets))
        if missing:
            raise PackError(f"missing builder-pack sheets: {', '.join(missing)}")
        tables = {
            output_name: read_sheet(zfile, targets[sheet_name], shared)
            for sheet_name, output_name in TABLE_SHEETS.items()
        }

    assets = _merge_assets(tables)
    target = next((asset for asset in assets if asset.get("tag") == "P-005"), None)
    if target is None:
        raise PackError("builder pack does not contain target asset P-005")
    payload: dict[str, object] = {
        "artifact": "pack",
        "version": 1,
        "source": {
            "file": workbook.name,
            "bytes": workbook.stat().st_size,
            "sha256": hashlib.sha256(workbook.read_bytes()).hexdigest(),
            "sheets": sorted(targets),
        },
        "counts": {name: len(rows) for name, rows in tables.items()},
        "assets": assets,
        "target": {
            "asset_id": target.get("asset_id"),
            "tag": target.get("tag"),
            "reason": "fixed demo target from Current_State",
        },
        "tables": tables,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def format_report(payload: dict[str, object]) -> str:
    counts = payload["counts"]
    target = payload["target"]
    return (
        f"assets             {counts['asset_master']}\n"
        f"telemetry rows     {counts['telemetry']}\n"
        f"events             {counts['alarms_events']}\n"
        f"work orders        {counts['maintenance_history']}\n"
        f"knowledge docs     {counts['knowledge_docs']}\n"
        f"data quality cases {counts['data_quality']}\n"
        f"target             {target['tag']} ({target['asset_id']})\n"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build pack.json from the builder workbook.")
    parser.add_argument("--xlsx", type=Path, required=True)
    parser.add_argument("--out", type=Path, default=Path("data/scene/pack.json"))
    args = parser.parse_args(argv)
    try:
        payload = build_pack(args.xlsx, args.out)
    except (OSError, KeyError, ET.ParseError, PackError) as exc:
        print(f"pack failed: {exc}", file=sys.stderr)
        return 1
    print(format_report(payload), end="")
    print(f"wrote             {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
