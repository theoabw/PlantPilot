"""Write a printable A4 sheet of synthetic nameplates into data/plates/.

The plates are printed on matte stock and stuck on real objects in the room.
Every plate says SYNTHETIC DEMO ASSET, so no video frame can be read as a real
mill or a real serial number.
"""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "plates"

DPI = 300
A4 = (int(8.27 * DPI), int(11.69 * DPI))
PLATE = (708, 472)
MARGIN = 60

def font_path(linux_name: str, macos_name: str) -> str:
    candidates = (
        Path("/usr/share/fonts/truetype/dejavu") / linux_name,
        Path("/System/Library/Fonts/Supplemental") / macos_name,
    )
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    raise RuntimeError(f"Font not found: {linux_name}")


BOLD = font_path("DejaVuSansMono-Bold.ttf", "Courier New Bold.ttf")
PLAIN = font_path("DejaVuSans.ttf", "Arial.ttf")

PLATES = [
    ("NelesAce", "MAP-150-4", "DN 150", "PN 40", "A216 WCB", "SN 24-118377"),
    ("NelesAce", "MAP-200-2", "DN 200", "PN 25", "A351 CF8M", "SN 23-004821"),
    ("Neles", "NEL-100-3", "DN 100", "PN 16", "A105", "SN 22-771904"),
    ("Jamesbury", "JBS-080-2", "DN 80", "PN 16", "A105", "SN 21-118200"),
    ("Flowrox", "FLX-300-5", "DN 300", "PN 40", "A494 CW-12MW", "SN 20-550117"),
    ("Neles", "NEL-250-4", "DN 250", "PN 25", "A216 WCB", "SN 19-303455"),
    ("NelesAce", "MAP-050-1", "DN 50", "PN 40", "A351 CF8M", "SN 24-900231"),
    ("Jamesbury", "JBS-150-3", "DN 150", "PN 40", "A216 WCB", "SN 18-220019"),
    ("Neles", "NEL-080-2", "DN 80", "PN 25", "A351 CF8M", "SN 23-441028"),
    ("NelesAce", "MAP-300-3", "DN 300", "PN 25", "A216 WCB", "SN 22-660913"),
    ("Flowrox", "FLX-150-4", "DN 150", "PN 16", "A494 CW-12MW", "SN 21-778140"),
    ("Jamesbury", "JBS-200-5", "DN 200", "PN 40", "A351 CF8M", "SN 20-119372"),
    ("Neles", "NEL-150-1", "DN 150", "PN 40", "A105", "SN 24-220507"),
    ("NelesAce", "MAP-100-2", "DN 100", "PN 25", "A216 WCB", "SN 23-990481"),
    ("Jamesbury", "JBS-050-3", "DN 50", "PN 16", "A351 CF8M", "SN 22-330256"),
    ("Flowrox", "FLX-250-2", "DN 250", "PN 25", "A105", "SN 19-884603"),
]


def marker_image(marker_id: int, px: int) -> Image.Image:
    """A 4x4 ArUco marker, used for the metre scale on a photo."""
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_4X4_50)
    grid = cv2.aruco.generateImageMarker(dictionary, marker_id, px)
    return Image.fromarray(grid).convert("RGB")


def draw_plate(brand: str, code: str, dn: str, pn: str, body: str, serial: str, damaged: bool = False, marker_id: int = 0) -> Image.Image:
    img = Image.new("RGB", PLATE, (238, 238, 232))
    d = ImageDraw.Draw(img)
    # 40 px bold at 300 dpi is about 3.4 mm cap height, in the range of a real plate.
    f_brand = ImageFont.truetype(BOLD, 46)
    f_small = ImageFont.truetype(PLAIN, 22)
    f_field = ImageFont.truetype(BOLD, 40)
    d.rectangle([8, 8, PLATE[0] - 8, PLATE[1] - 8], outline=(40, 40, 40), width=3)
    d.text((28, 22), brand.upper(), font=f_brand, fill=(20, 20, 20))
    rows = [("TYPE", code), ("SIZE", dn), ("CLASS", pn), ("BODY", body), ("SER", serial)]
    y = 96
    for key, value in rows:
        baseline = y + 34
        d.text((28, baseline), key, font=f_small, fill=(95, 95, 95), anchor="ls")
        shown = value.replace("1", "l") if damaged and key == "SER" else value
        d.text((130, baseline), shown, font=f_field, fill=(20, 20, 20), anchor="ls")
        y += 66
    d.text((28, PLATE[1] - 34), "SYNTHETIC DEMO ASSET", font=f_small, fill=(150, 60, 40))
    if marker_id is not None:
        mark = marker_image(marker_id, 104)
        img.paste(mark, (PLATE[0] - 104 - 20, PLATE[1] - 104 - 40))
        d.rectangle([PLATE[0] - 104 - 22, PLATE[1] - 104 - 42,
                     PLATE[0] - 16, PLATE[1] - 36], outline=(40, 40, 40), width=2)
    return img


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    per_page = 9  # 3 by 3 keeps 60 by 40 mm plates inside an A4 page at 300 dpi
    pages: list[Image.Image] = []
    for start in range(0, len(PLATES), per_page):
        sheet = Image.new("RGB", A4, (255, 255, 255))
        for offset, plate in enumerate(PLATES[start : start + per_page]):
            damaged = (start + offset) % 8 == 5
            tile = draw_plate(*plate, damaged=damaged, marker_id=(start + offset) % 50)
            col, row = offset % 3, offset // 3
            x = MARGIN + col * (PLATE[0] + 20)
            y = MARGIN + row * (PLATE[1] + 40)
            sheet.paste(tile, (x, y))
        pages.append(sheet)
    scale_page = Image.new("RGB", A4, (255, 255, 255))
    d = ImageDraw.Draw(scale_page)
    f_big = ImageFont.truetype(BOLD, 44)
    f_small = ImageFont.truetype(PLAIN, 30)
    d.text((MARGIN, MARGIN), "SCALE CARD 150 mm", font=f_big, fill=(20, 20, 20))
    big_px = int(150 / 25.4 * DPI)
    big = marker_image(48, big_px)
    scale_page.paste(big, (MARGIN, MARGIN + 80))
    d.text((MARGIN, MARGIN + 110 + big_px), "SCALE CARD 100 mm", font=f_big, fill=(20, 20, 20))
    small_px = int(100 / 25.4 * DPI)
    small = marker_image(49, small_px)
    scale_page.paste(small, (MARGIN, MARGIN + 190 + big_px))
    d.text((MARGIN + small_px + 60, MARGIN + 250 + big_px), "print at 100 percent,", font=f_small, fill=(60, 60, 60))
    d.text((MARGIN + small_px + 60, MARGIN + 300 + big_px), "measure one edge with a ruler,", font=f_small, fill=(60, 60, 60))
    d.text((MARGIN + small_px + 60, MARGIN + 350 + big_px), "and pass the real length to scan.py", font=f_small, fill=(60, 60, 60))
    pages.append(scale_page)

    pdf = OUT / "plates-a4.pdf"
    pages[0].save(pdf, "PDF", resolution=DPI, save_all=True, append_images=pages[1:])
    print(f"wrote {pdf.relative_to(ROOT)}: {len(PLATES)} plates plus a scale card on {len(pages)} pages at {DPI} dpi")
    print("print on matte stock at 100 percent, no fit to page, then cut along the borders")


if __name__ == "__main__":
    main()
