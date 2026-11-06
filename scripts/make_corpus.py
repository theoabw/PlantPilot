"""Fetch the two public Valmet documents and build the local corpus index.

Downloads into data/valmet, which is gitignored, because both documents are
all rights reserved. The index and the downloaded PDFs never enter the repo.
The repo keeps only section ids, titles, pages and short quotes.
"""

from __future__ import annotations

import csv
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app" / "server" / "src"))

from plantpilot import corpus  # noqa: E402

DATA = ROOT / "data"
VALMET = DATA / "valmet"
MANUAL = VALMET / "flowcontrol_manual.pdf"
VMR003 = VALMET / "vmr003en.pdf"
SAMPLE = ROOT / "fixtures" / "corpus" / "sections_sample.json"
ACTIONS = DATA / "vmr003_actions.csv"

URLS = {
    MANUAL: "https://www.valmet.com/globalassets/sharepoint/imported/flowcontrol_manual.pdf",
    VMR003: "https://www.valmet.com/globalassets/sharepoint/imported/vmr003en.pdf",
}

# Transcribed from VMR003EN (5/2022), the public one page service recommendation.
# Two interval columns, 1 year and 4 years, nine part rows.
VMR_ROWS = [
    ("Potentiometer + R/I modulator", "Calibration", "Change"),
    ("Display card", "Check function", "Check function"),
    ("Limit switches", "Check function", "Check function"),
    ("Flexible coupling", "Change", "Change"),
    ("Coupling set", "Check condition", "Change"),
    ("Belt", "Check condition and tightness", "Change"),
    ("Step motor", "Optional spare part", "Optional spare part"),
    ("Gear and lubrication set", "Check for leakages", "Change lubricant"),
    ("Valve", "Visual checking, clean closing element and seat ring", "Clean, replace spare part set"),
]


def fetch(path: Path) -> None:
    if path.exists() and path.stat().st_size > 10_000:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(URLS[path], headers={"User-Agent": "plantpilot/0.1 (hackathon)"})
    with urllib.request.urlopen(req, timeout=120) as resp, path.open("wb") as fh:
        fh.write(resp.read())
    print(f"fetched {path.name} ({path.stat().st_size} bytes)")


def write_sample() -> int:
    pages = corpus.pdf_text(MANUAL)
    sections = corpus.parse_toc(pages)
    if not sections:
        print("TOC parse produced no sections", file=sys.stderr)
        return 0
    step = max(len(sections) // 20, 1)
    picked = sections[::step][:20]
    rows = []
    for sec in picked:
        body = corpus.section_text(pages, sec)
        rows.append({
            "id": sec.sid,
            "title": sec.title,
            "page": sec.page,
            "quote": corpus.first_quote(body),
        })
    SAMPLE.parent.mkdir(parents=True, exist_ok=True)
    SAMPLE.write_text(json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return len(rows)


def write_actions() -> int:
    DATA.mkdir(parents=True, exist_ok=True)
    with ACTIONS.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["family", "part", "action", "interval", "source"])
        for part, one_year, four_year in VMR_ROWS:
            writer.writerow(["NelesAce", part, one_year, "1 year", "VMR003"])
            writer.writerow(["NelesAce", part, four_year, "4 years", "VMR003"])
    return len(VMR_ROWS) * 2


def main() -> None:
    for path in URLS:
        fetch(path)
    meta = corpus.build_index(MANUAL, DATA / "index.db")
    print(f"indexed {meta['indexed']} sections from {meta['pages']} pages")
    print(f"sample sections: {write_sample()}")
    print(f"action rows: {write_actions()}")
    for sec in corpus.parse_toc(corpus.pdf_text(MANUAL))[:6]:
        print(f"  {sec.sid:<8} p{sec.page:<4} {sec.title}")


if __name__ == "__main__":
    main()
