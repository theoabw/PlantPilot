"""Corpus: parse the manual's table of contents, split pages into sections, index them.

The manual is a public Valmet PDF kept in data/ (gitignored, all rights reserved).
We index section text locally and ship only section ids, titles, pages and short
quotes, never the extracted body text.
"""

from __future__ import annotations

import json
import re
import sqlite3
import subprocess
from dataclasses import dataclass, asdict
from pathlib import Path

TOC_SECTION = re.compile(
    r"^\s*(?P<sid>\d+(?:\.\d+)*)\s+(?P<title>\S.*?)\s*\.{2,}\s*(?P<page>\d+)\s*$"
)
TOC_SPACED = re.compile(r"^\s*(?P<sid>\d+(?:\.\d+)*)\s{2,}(?P<title>\S.*?)\s{2,}(?P<page>\d+)\s*$")
PAGE_HEADER_LEAD = re.compile(r"^\s*\d{1,3}\s+(?:[A-Za-z][\w-]*\s*){1,5}$")
PAGE_HEADER_TAIL = re.compile(r"^(?:[A-Za-z][\w-]*\s*){1,5}\d{1,3}\s*$")
JUNK_RUN = re.compile(r"[-=_~.·∙]{4,}|⋅|√|\b(?:where|and)\s*$")
EQUATION_CHARS = set("=+×/÷^_(){}[]Σσµ·∙−⋅√")
MIN_TEXT_CHARS = 3
MAX_SYMBOL_RATIO = 0.12


@dataclass
class Section:
    sid: str
    title: str
    page: int
    end_page: int

    def as_dict(self) -> dict:
        return asdict(self)


def pdf_text(pdf: Path) -> list[str]:
    """One string per page, via poppler's pdftotext. Returns [] if the tool or file is missing."""
    if not pdf.exists():
        return []
    try:
        out = subprocess.run(
            ["pdftotext", "-layout", str(pdf), "-"],
            capture_output=True,
            check=True,
            timeout=120,
        ).stdout.decode("utf-8", "replace")
    except (OSError, subprocess.SubprocessError):
        return []
    pages = out.split("\f")
    if pages and not pages[-1].strip():
        pages.pop()
    return pages


def parse_toc(pages: list[str]) -> list[Section]:
    """Read the printed table of contents and return sections sorted by page."""
    entries: list[Section] = []
    for page in pages[:12]:
        for line in page.splitlines():
            m = TOC_SECTION.match(line) or TOC_SPACED.match(line)
            if not m:
                continue
            title = m.group("title").strip(" .")
            if len(title) < 3:
                continue
            entries.append(Section(m.group("sid"), title, int(m.group("page")), 0))
    # Keep the first occurrence of each id and sort by printed page.
    seen: set[str] = set()
    unique: list[Section] = []
    for s in sorted(entries, key=lambda s: (s.page, s.sid)):
        if s.sid in seen:
            continue
        seen.add(s.sid)
        unique.append(s)
    for i, s in enumerate(unique):
        s.end_page = (unique[i + 1].page - 1) if i + 1 < len(unique) else 10**4
    return unique


def is_junk_line(line: str) -> bool:
    words = line.split()
    if len(line) < MIN_TEXT_CHARS:
        return True
    if len(words) <= 5 and (PAGE_HEADER_LEAD.match(line) or PAGE_HEADER_TAIL.match(line)):
        return True
    if JUNK_RUN.search(line):
        return True
    symbols = sum(1 for ch in line if not ch.isalnum() and not ch.isspace())
    return symbols / max(len(line), 1) > MAX_SYMBOL_RATIO


def clean_text(text: str) -> str:
    """Drop running headers, bare page numbers, equations and figure furniture."""
    return "\n".join(line.strip() for line in text.splitlines() if not is_junk_line(line.strip()))


def section_text(pages: list[str], sec: Section) -> str:
    chunk = pages[sec.page - 1 : sec.end_page]
    return clean_text("\n".join(chunk))


def build_index(pdf: Path, db: Path) -> dict:
    """Build or replace the FTS index. Returns counts."""
    pages = pdf_text(pdf)
    sections = parse_toc(pages)
    db.parent.mkdir(parents=True, exist_ok=True)
    if db.exists():
        db.unlink()
    con = sqlite3.connect(db)
    con.execute(
        "CREATE VIRTUAL TABLE sections USING fts5("
        "sid UNINDEXED, title, page UNINDEXED, quote, body)"
    )
    for sec in sections:
        body = section_text(pages, sec)
        quote = first_quote(body)
        con.execute(
            "INSERT INTO sections (sid, title, page, quote, body) VALUES (?, ?, ?, ?, ?)",
            (sec.sid, sec.title, sec.page, quote, body),
        )
    con.commit()
    ran = con.execute("SELECT count(*) FROM sections").fetchone()[0]
    con.close()
    meta = {"pdf": pdf.name, "pages": len(pages), "sections": len(sections), "indexed": ran}
    (db.parent / "index.json").write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    return meta


def first_quote(body: str, limit: int = 220) -> str:
    """The first sentence that reads as prose, for a card. Never the full body."""
    flat = " ".join(body.split())
    if not flat:
        return ""
    sentences = re.split(r"(?<=[.!?])\s+", flat)
    for sentence in sentences:
        candidate = sentence.strip()
        symbols = sum(1 for ch in candidate if not ch.isalnum() and not ch.isspace())
        if len(candidate) < 50 or len(candidate.split()) < 8:
            continue
        if symbols / max(len(candidate), 1) > MAX_SYMBOL_RATIO:
            continue
        return candidate[:limit].strip()
    return flat[:limit].strip()


def search(db: Path, query: str, limit: int = 3) -> list[dict]:
    """BM25 over section text. Returns [] when the index or the query is missing."""
    if not db.exists():
        return []
    terms = [t for t in re.findall(r"[A-Za-zÄÖÅäöå0-9]{3,}", query)]
    if not terms:
        return []
    fts = " OR ".join(terms)
    con = sqlite3.connect(db)
    try:
        rows = con.execute(
            "SELECT sid, title, page, quote, bm25(sections) AS rank "
            "FROM sections WHERE sections MATCH ? ORDER BY rank LIMIT ?",
            (fts, limit),
        ).fetchall()
    except sqlite3.Error:
        return []
    finally:
        con.close()
    return [
        {"id": r[0], "title": r[1], "page": r[2], "quote": r[3], "anchor": f"#page={r[2]}"}
        for r in rows
    ]


def section(db: Path, sid: str) -> dict | None:
    if not db.exists():
        return None
    con = sqlite3.connect(db)
    try:
        row = con.execute(
            "SELECT sid, title, page, quote FROM sections WHERE sid = ?", (sid,)
        ).fetchone()
    finally:
        con.close()
    if not row:
        return None
    return {"id": row[0], "title": row[1], "page": row[2], "quote": row[3], "anchor": f"#page={row[2]}"}


def count(db: Path) -> int:
    if not db.exists():
        return 0
    con = sqlite3.connect(db)
    try:
        return con.execute("SELECT count(*) FROM sections").fetchone()[0]
    except sqlite3.Error:
        return 0
    finally:
        con.close()
