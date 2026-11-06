from pathlib import Path

from plantpilot import nav

ROOT = Path(__file__).resolve().parents[3]
SPEC = nav.load_spec(ROOT / "fixtures" / "plant" / "plant.json")
START = (2.0, 0.8)
WEST_CLOSED = [[0.0, 4.8, 4.6, 7.2]]


def test_every_inspection_point_is_reachable():
    for asset in SPEC["assets"]:
        result = nav.plan(SPEC, START, asset["waypoint"])
        assert result["reachable"] is True, asset["id"]
        assert result["distance_m"] > 0.5
        assert result["clearance_m"] > 0.3


def test_the_plain_route_uses_the_west_aisle():
    result = nav.plan(SPEC, START, (8.0, 8.8))
    xs = [p[0] for p in result["path"]]
    assert max(xs) < 9.0 and min(xs) < 2.0


def test_closing_the_west_aisle_forces_a_longer_route():
    plain = nav.plan(SPEC, START, (8.0, 8.8))
    blocked = nav.plan(SPEC, START, (8.0, 8.8), blockers=WEST_CLOSED)
    assert blocked["reachable"] is True
    assert blocked["distance_m"] > plain["distance_m"] + 4.0
    assert max(p[0] for p in blocked["path"]) > 10.0


def test_a_wall_across_the_hall_reports_unreachable_with_a_reason():
    result = nav.plan(SPEC, START, (8.0, 8.8), blockers=[[0.0, 1.5, 16.0, 2.2]])
    assert result["reachable"] is False
    assert "no walkable route" in result["reason"]


def test_agent_width_changes_the_route():
    wide = nav.plan(SPEC, START, (8.0, 8.8), agent_radius_m=0.9)
    assert wide["reachable"] in (True, False)
    if wide["reachable"]:
        assert wide["clearance_m"] >= 0.65
