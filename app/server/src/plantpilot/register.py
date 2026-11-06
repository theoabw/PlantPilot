"""Asset register: a CMMS-shaped table in SQLite, built from a committed CSV.

The rows are synthetic. The schema is shaped like a real register so one real row
can replace one synthetic row in a single command.
"""

from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

COLUMNS = [
    "tag", "line", "family", "type", "dn", "pn", "body", "serial",
    "install_date", "last_service", "criticality", "spare_group", "overdue",
]

SCHEMA = """
CREATE TABLE IF NOT EXISTS assets (
  tag TEXT PRIMARY KEY, line TEXT, family TEXT, type TEXT, dn TEXT, pn TEXT,
  body TEXT, serial TEXT, install_date TEXT, last_service TEXT,
  criticality TEXT, spare_group TEXT, overdue INTEGER
)
"""


def build(db: Path, csv_path: Path) -> int:
    db.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db)
    con.execute(SCHEMA)
    con.execute("DELETE FROM assets")
    with csv_path.open(newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            con.execute(
                f"INSERT INTO assets ({', '.join(COLUMNS)}) VALUES ({', '.join('?' * len(COLUMNS))})",
                [row.get(c, "") for c in COLUMNS[:-1]] + [1 if row.get("overdue") in ("1", "true", "yes") else 0],
            )
    con.commit()
    n = con.execute("SELECT count(*) FROM assets").fetchone()[0]
    con.close()
    return n


def _row_to_asset(row: sqlite3.Row | tuple) -> dict:
    keys = ["tag", "line", "family", "type", "dn", "pn", "body", "serial",
            "install_date", "last_service", "criticality", "spare_group"]
    out = {k: row[i] for i, k in enumerate(keys)}
    out["overdue"] = bool(row[len(keys)])
    return out


def _connect(db: Path) -> sqlite3.Connection | None:
    if not db.exists():
        return None
    con = sqlite3.connect(db)
    con.row_factory = sqlite3.Row
    try:
        con.execute("SELECT 1 FROM assets LIMIT 1")
    except sqlite3.Error:
        con.close()
        return None
    return con


def get(db: Path, tag: str) -> dict | None:
    con = _connect(db)
    if con is None:
        return None
    try:
        row = con.execute(
            "SELECT tag, line, family, type, dn, pn, body, serial, install_date, "
            "last_service, criticality, spare_group, overdue FROM assets WHERE tag = ?",
            (tag.upper(),),
        ).fetchone()
    finally:
        con.close()
    return _row_to_asset(row) if row else None


SELECT = (
    "SELECT tag, line, family, type, dn, pn, body, serial, install_date, "
    "last_service, criticality, spare_group, overdue FROM assets "
)


def match_plate(
    db: Path,
    family: str,
    dn: str,
    pn: str,
    serial: str | None = None,
    type_code: str | None = None,
) -> dict | None:
    """Find the asset a plate describes. Serial wins, then the exact type code, then the shape."""
    con = _connect(db)
    if con is None:
        return None
    try:
        if serial:
            row = con.execute(SELECT + "WHERE serial = ?", (serial,)).fetchone()
            if row:
                return _row_to_asset(row)
        if type_code:
            row = con.execute(SELECT + "WHERE type = ?", (type_code,)).fetchone()
            if row:
                return _row_to_asset(row)
        row = con.execute(
            SELECT + "WHERE family = ? AND dn = ? AND pn = ? ORDER BY tag LIMIT 1",
            (family, dn, pn),
        ).fetchone()
    finally:
        con.close()
    return _row_to_asset(row) if row else None


def neighbours(db: Path, tag: str, limit: int = 3) -> list[dict]:
    asset = get(db, tag)
    if not asset:
        return []
    con = _connect(db)
    if con is None:
        return []
    try:
        rows = con.execute(
            "SELECT tag, line, overdue FROM assets WHERE line = ? AND tag != ? ORDER BY tag LIMIT ?",
            (asset["line"], asset["tag"], limit),
        ).fetchall()
    finally:
        con.close()
    return [{"tag": r["tag"], "label": r["line"], "overdue": bool(r["overdue"])} for r in rows]


def shared_spares(db: Path, tag: str, limit: int = 3) -> list[str]:
    asset = get(db, tag)
    if not asset or not asset.get("spare_group"):
        return []
    con = _connect(db)
    if con is None:
        return []
    try:
        rows = con.execute(
            "SELECT tag FROM assets WHERE spare_group = ? AND tag != ? ORDER BY tag LIMIT ?",
            (asset["spare_group"], asset["tag"], limit),
        ).fetchall()
    finally:
        con.close()
    return [r["tag"] for r in rows]


def count(db: Path) -> int:
    con = _connect(db)
    if con is None:
        return 0
    try:
        return con.execute("SELECT count(*) FROM assets").fetchone()[0]
    finally:
        con.close()
