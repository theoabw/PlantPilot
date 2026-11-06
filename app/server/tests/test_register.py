from pathlib import Path

from fieldplate import register

ROOT = Path(__file__).resolve().parents[3]
CSV = ROOT / "fixtures" / "register" / "assets.csv"


def test_build_and_lookup(tmp_path):
    db = tmp_path / "register.db"
    assert register.build(db, CSV) == 48
    asset = register.get(db, "K-102")
    assert asset["family"] == "NelesAce" and asset["dn"] == "DN 150"
    assert asset["last_service"] == "2025-11-14"


def test_match_plate_by_serial_then_by_shape(tmp_path):
    db = tmp_path / "register.db"
    register.build(db, CSV)
    by_serial = register.match_plate(db, "NelesAce", "DN 150", "PN 40", "SN 24-118377")
    assert by_serial["tag"] == "K-102"
    by_type = register.match_plate(db, "NelesAce", "DN 150", "PN 40", None, "MAP-150-4")
    assert by_type["tag"] == "K-102"
    by_shape = register.match_plate(db, "NelesAce", "DN 150", "PN 40", None)
    assert by_shape["dn"] == "DN 150" and by_shape["family"] == "NelesAce"


def test_neighbours_and_shared_spares(tmp_path):
    db = tmp_path / "register.db"
    register.build(db, CSV)
    neighbours = register.neighbours(db, "K-102")
    assert neighbours and any(n["overdue"] for n in neighbours)
    assert "K-101" in register.shared_spares(db, "K-102")
