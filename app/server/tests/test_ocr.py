import io
import shutil

import pytest
from PIL import Image, ImageDraw, ImageFont

from fieldplate import ocr

HAS_TESSERACT = shutil.which("tesseract") is not None


def plate_png(scale: int = 2) -> bytes:
    img = Image.new("RGB", (700 * scale, 470 * scale), (238, 238, 232))
    draw = ImageDraw.Draw(img)
    bold = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf", 17 * scale)
    plain = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 13 * scale)
    rows = [("TYPE", "MAP-150-4"), ("SIZE", "DN 150"), ("CLASS", "PN 40"),
            ("BODY", "A216 WCB"), ("SER", "SN 24-118377")]
    y = 40 * scale
    for key, value in rows:
        draw.text((30 * scale, y), key, font=plain, fill=(90, 90, 90))
        draw.text((130 * scale, y), value, font=bold, fill=(20, 20, 20))
        y += 70 * scale
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@pytest.mark.skipif(not HAS_TESSERACT, reason="tesseract not installed")
def test_gate_accepts_a_readable_plate_and_fields_parse():
    result = ocr.analyze(plate_png(2))
    assert result["gate"]["ok"] is True
    fields = result["plate"]["fields"]
    assert fields["dn"] == "DN 150"
    assert fields["pn"] == "PN 40"
    assert fields["serial"] == "SN 24-118377"
    assert result["plate"]["family"] == "NelesAce"


@pytest.mark.skipif(not HAS_TESSERACT, reason="tesseract not installed")
def test_gate_refuses_a_frame_that_is_too_small():
    tiny = plate_png(1).replace(b"", b"")
    small = Image.open(io.BytesIO(tiny)).resize((300, 200))
    buf = io.BytesIO()
    small.save(buf, format="PNG")
    result = ocr.analyze(buf.getvalue())
    assert result["gate"]["ok"] is False
    assert "move closer" in result["gate"]["message"] or "no text" in result["gate"]["message"]
    assert result["plate"] is None


def test_family_mapping():
    assert ocr.family_of({"type": "MAP-150-4"}) == "NelesAce"
    assert ocr.family_of({"type": "JBS-080-2"}) == "Jamesbury"
    assert ocr.family_of({"type": "ZZZ-1"}) == "unknown"
