"""Generate the synthetic asset register as a CMMS-shaped CSV.

Deterministic: no randomness, no clock. The demo asset and its neighbours are
written first so the graph always has an overdue node to show.
"""

from __future__ import annotations

import csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "fixtures" / "register" / "assets.csv"

COLUMNS = ["tag", "line", "family", "type", "dn", "pn", "body", "serial",
           "install_date", "last_service", "criticality", "spare_group", "overdue"]

LINES = [
    ("Line 1 stock preparation", "L1"),
    ("Line 2 board machine", "K"),
    ("Line 3 drying", "D"),
    ("Line 4 finishing", "F"),
]
FAMILIES = [("NelesAce", "MAP"), ("Neles", "NEL"), ("Jamesbury", "JBS"), ("Flowrox", "FLX")]
SIZES = ["DN 50", "DN 80", "DN 100", "DN 150", "DN 200", "DN 250", "DN 300"]
CLASSES = ["PN 16", "PN 25", "PN 40"]
BODIES = ["A216 WCB", "A351 CF8M", "A105", "A494 CW-12MW"]


def main() -> None:
    rows: list[dict] = []
    # The demo asset and two neighbours on the same line, one of them overdue.
    rows.append({"tag": "K-102", "line": LINES[1][0], "family": "NelesAce", "type": "MAP-150-4",
                 "dn": "DN 150", "pn": "PN 40", "body": "A216 WCB", "serial": "SN 24-118377",
                 "install_date": "2014-05-12", "last_service": "2025-11-14",
                 "criticality": "high", "spare_group": "SP-07", "overdue": 0})
    rows.append({"tag": "K-101", "line": LINES[1][0], "family": "Neles", "type": "NEL-200-3",
                 "dn": "DN 200", "pn": "PN 25", "body": "A351 CF8M", "serial": "SN 21-044190",
                 "install_date": "2011-09-01", "last_service": "2024-08-02",
                 "criticality": "medium", "spare_group": "SP-07", "overdue": 1})
    rows.append({"tag": "K-103", "line": LINES[1][0], "family": "Jamesbury", "type": "JBS-080-2",
                 "dn": "DN 80", "pn": "PN 16", "body": "A105", "serial": "SN 19-771204",
                 "install_date": "2019-03-18", "last_service": "2026-01-20",
                 "criticality": "low", "spare_group": "SP-12", "overdue": 0})
    for line_name, prefix in LINES:
        for i in range(1, 13):
            family, code = FAMILIES[i % len(FAMILIES)]
            size = SIZES[(i + len(line_name)) % len(SIZES)]
            tag = f"{prefix}-{100 + i}"
            if any(r["tag"] == tag for r in rows):
                continue
            rows.append({
                "tag": tag, "line": line_name, "family": family,
                "type": f"{code}-{size.split()[1]}-{(i % 4) + 2}",
                "dn": size, "pn": CLASSES[i % len(CLASSES)], "body": BODIES[i % len(BODIES)],
                "serial": f"SN {10 + i}-{100000 + i * 137 + len(line_name)}",
                "install_date": f"20{10 + i % 12}-0{(i % 9) + 1}-1{i % 9}",
                "last_service": f"202{5 - i % 3}-0{(i % 9) + 1}-2{i % 8}",
                "criticality": ["low", "medium", "high"][i % 3],
                "spare_group": f"SP-{(i % 6) + 1:02d}",
                "overdue": 1 if i in (4, 7, 11) else 0,
            })
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {OUT.relative_to(ROOT)} with {len(rows)} assets")


if __name__ == "__main__":
    main()
