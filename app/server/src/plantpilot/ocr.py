"""Capture gate, plate OCR and field resolution.

The gate is measured on the words tesseract actually found, so the number on
screen during the demo is the number the system used to refuse or accept. One
tesseract pass serves both the gate and the field parser.
"""

from __future__ import annotations

import io
import re
import shutil
import statistics
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageFilter, ImageStat

MIN_CHAR_PX = 20.0
MIN_BLUR = 6.0
MAX_SIDE = 1600

FAMILIES = {
    "MAP": "NelesAce",
    "NELESACE": "NelesAce",
    "NEL": "Neles",
    "NELES": "Neles",
    "JBS": "Jamesbury",
    "JAMES": "Jamesbury",
    "JAMESBURY": "Jamesbury",
    "EASY": "Neles Easyflow",
    "FLX": "Flowrox",
    "FLOWROX": "Flowrox",
}

# Values are matched by their own shape, not by the label in front of them:
# printed labels are small and OCR reads them badly, while codes have a strong form.
RE_TYPE = re.compile(r"\b([A-Z]{2,6})-(\d{2,4})-(\d{1,2})\b")
RE_DN = re.compile(r"\bDN\s*[:\-]?\s*(\d{2,4})\b", re.IGNORECASE)
RE_PN = re.compile(r"\bPN\s*[:\-]?\s*(\d{2,3})\b", re.IGNORECASE)
RE_SERIAL = re.compile(r"\bSN[\s:\-]*([A-Z0-9][A-Z0-9\-]{2,})", re.IGNORECASE)
RE_BODY = re.compile(r"\bA(216|351|105|494|182|743)\s?([A-Z0-9\-]{2,8})\b")


def load_image(data: bytes) -> Image.Image:
    img = Image.open(io.BytesIO(data))
    img = img.convert("RGB")
    if max(img.size) > MAX_SIDE:
        ratio = MAX_SIDE / max(img.size)
        img = img.resize((int(img.width * ratio), int(img.height * ratio)))
    return img


def blur_score(img: Image.Image) -> float:
    """Variance of an edge image: low means soft, out of focus or too far away."""
    edges = img.convert("L").filter(ImageFilter.FIND_EDGES)
    return float(ImageStat.Stat(edges).var[0])


def read_plate_text(img: Image.Image) -> tuple[list[str], list[int]]:
    """One tesseract pass. Returns the rebuilt lines and the per-word heights in px."""
    if not shutil.which("tesseract"):
        return [], []
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "frame.png"
        img.save(path)
        try:
            out = subprocess.run(
                ["tesseract", str(path), "stdout", "--psm", "3", "tsv"],
                capture_output=True, check=True, timeout=60,
            ).stdout.decode("utf-8", "replace")
        except (OSError, subprocess.SubprocessError):
            return [], []
    lines: dict[tuple[int, int, int], list[tuple[int, str]]] = {}
    heights: list[int] = []
    for row in out.splitlines()[1:]:
        cols = row.split("\t")
        if len(cols) < 12 or cols[0] != "5" or not cols[11].strip():
            continue
        key = (int(cols[2]), int(cols[3]), int(cols[4]))
        lines.setdefault(key, []).append((int(cols[6]), cols[11].strip()))
        heights.append(int(float(cols[9] or 0)))
    rebuilt = [" ".join(w for _, w in sorted(lines[k])) for k in sorted(lines)]
    return rebuilt, heights


def decide_gate(heights: list[int], blur: float) -> dict:
    # The 75th percentile ignores the small disclaimer line and measures the plate text.
    char_px = float(statistics.quantiles(heights, n=4)[2]) if len(heights) >= 4 else (
        float(max(heights)) if heights else 0.0)
    if not heights:
        return {"ok": False, "character_px": 0.0, "blur": blur,
                "message": "no text found, fill the frame with the plate"}
    if char_px < MIN_CHAR_PX:
        return {"ok": False, "character_px": char_px, "blur": blur,
                "message": f"characters {char_px:.0f} px, need {MIN_CHAR_PX:.0f}, move closer"}
    if blur < MIN_BLUR:
        return {"ok": False, "character_px": char_px, "blur": blur,
                "message": "frame is soft, hold still and refocus"}
    return {"ok": True, "character_px": char_px, "blur": blur, "message": "ok"}


def parse_fields(lines: list[str]) -> dict:
    text = " ".join(lines)
    fields: dict[str, str] = {}
    m = RE_TYPE.search(text)
    if m:
        fields["type"] = f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = RE_DN.search(text)
    if m:
        fields["dn"] = f"DN {m.group(1)}"
    m = RE_PN.search(text)
    if m:
        fields["pn"] = f"PN {m.group(1)}"
    m = RE_SERIAL.search(text)
    if m:
        fields["serial"] = f"SN {m.group(1)}"
    m = RE_BODY.search(text)
    if m:
        fields["body"] = f"A{m.group(1)} {m.group(2)}".strip()
    return fields


def family_of(fields: dict) -> str:
    code = (fields.get("type") or "").upper()
    for prefix, family in sorted(FAMILIES.items(), key=lambda kv: -len(kv[0])):
        if code.startswith(prefix):
            return family
    return "unknown"


def analyze(data: bytes) -> dict:
    img = load_image(data)
    lines, heights = read_plate_text(img)
    g = decide_gate(heights, blur_score(img))
    if not g["ok"]:
        return {"gate": g, "plate": None}
    fields = parse_fields(lines)
    return {
        "gate": g,
        "plate": {"fields": fields, "confidence": {k: 0.95 for k in fields}, "family": family_of(fields)},
    }
