"""Reasoning block tests: computed facts, cited claims and derived verdicts.

The synthetic packs are built inline, so the fouling and pressure-collapse cases
run without the supplied data and can never skip. The equipment-pack case
recomputes the facts from the pack itself and skips when the pack is absent.
"""

import json
import re
from pathlib import Path

import pytest

from plantpilot import diagnose


PACK = Path("data/equipment/pack.json")
SKIP_NO_PACK = pytest.mark.skipif(not PACK.exists(), reason="equipment pack not supplied")

SAMPLE_COUNT = 8
SAMPLE_STEP_DAYS = 0.5 / 24.0
NUMBER = re.compile(r"-?\d+(?:\.\d+)?")

COLUMNS = {
    "flow": "process_flow_pct",
    "pressure": "process_pressure_bar",
    "vibration": "vibration_mm_s",
    "bearing_temp": "bearing_temp_c",
    "motor_current": "motor_current_a",
    "speed": "speed_rpm",
}

# Flow down hard, head flat, current up: the fouling shape the pack files for
# P-005.
FOULING_SERIES = {
    "flow": (70.0, 58.0),
    "pressure": (4.5, 4.49),
    "vibration": (2.3, 2.1),
    "bearing_temp": (55.0, 55.4),
    "motor_current": (40.0, 43.0),
    "speed": (1480.0, 1479.0),
}

# Flow and head fall together: the opposite of the fouling shape, and the case
# where a suction restriction cannot be called less likely.
COLLAPSE_SERIES = {
    "flow": (70.0, 55.0),
    "pressure": (4.5, 3.0),
    "vibration": (2.2, 2.25),
    "bearing_temp": (55.0, 55.2),
    "motor_current": (40.0, 42.5),
    "speed": (1480.0, 1479.5),
}

# A flow fall too small for the fouling bar but still a fall, with the current
# rising: the sensor-drift hypothesis is judged on any fall, not on the 10 percent
# fouling bar.
MILD_SERIES = {
    "flow": (70.0, 66.5),
    "pressure": (4.5, 4.49),
    "vibration": (2.2, 2.1),
    "bearing_temp": (55.0, 55.1),
    "motor_current": (40.0, 42.0),
    "speed": (1480.0, 1479.5),
}


def _ramp(start: float, end: float, count: int = SAMPLE_COUNT) -> list[float]:
    """A straight deterministic ramp, rounded the way the pack rounds readings."""
    if count == 1:
        return [round(start, 3)]
    step = (end - start) / (count - 1)
    return [round(start + step * index, 3) for index in range(count)]


def _synthetic_pack(series: dict[str, tuple[float, float]]) -> dict:
    """A minimal complete pack: one pump, six channels, one alarm, one case."""
    channels = {name: _ramp(*pair) for name, pair in series.items()}
    rows = []
    for index in range(SAMPLE_COUNT):
        row = {
            "timestamp": 46000 + index * SAMPLE_STEP_DAYS,
            "asset_id": "ASSET-001",
            "tag": "P-005",
        }
        for name, column in COLUMNS.items():
            row[column] = channels[name][index] if name in channels else ""
        rows.append(row)
    documents = [
        {
            "doc_id": "DOC-PROCESS_PUMP-CORE",
            "title": "Process pump condition context",
            "scope": "PROCESS_PUMP",
            "section": None,
            "page": None,
            "content": "Use vibration, bearing temperature, pressure, flow and motor load together.",
            "synthetic_record": True,
        },
        {
            "doc_id": "DOC-FIELD-SAFETY",
            "title": "Field-service safety guardrail",
            "scope": "ALL",
            "section": None,
            "page": None,
            "content": "Recommend verification and escalation rather than autonomous physical action.",
            "synthetic_record": True,
        },
    ]
    return {
        "artifact": "pack",
        "version": 1,
        "assets": [
            {
                "asset_id": "ASSET-001",
                "tag": "P-005",
                "asset_class": "PROCESS_PUMP",
                "area_name": "Utility Island",
                "condition_state": "attention_required",
                "issue_code": "FOULING",
                "issue_summary": "Efficiency loss / fouling-like signature",
                "urgency": "high",
                "health_score": 44,
                "model_confidence": 0.8,
                "recommended_next_check": "inspect hydraulic path",
                "knowledge_doc_id": "DOC-PROCESS_PUMP-CORE",
                "synthetic_record": True,
            }
        ],
        "tables": {
            "telemetry": rows,
            "alarms_events": [
                {
                    "event_id": "EVT-00001",
                    "asset_id": "ASSET-001",
                    "event_code": "FOULING",
                    "event_type": "CONDITION_CHANGE",
                    "severity": "high",
                    "status": "open",
                    "description": "Flow loss signature detected",
                    "timestamp": 46000.5,
                }
            ],
            "data_quality": [
                {
                    "issue_id": "DQ-0001",
                    "asset_id": "ASSET-001",
                    "issue_type": "sensor_quality_drop",
                    "severity": "medium",
                    "source_sheet": "Telemetry",
                    "recommended_handling": "flag_for_review",
                }
            ],
            "maintenance_history": [],
            "knowledge_docs": documents,
        },
    }


def _payload(series: dict[str, tuple[float, float]]) -> dict:
    return diagnose.diagnose(_synthetic_pack(series))


def _verdicts(payload: dict) -> dict[str, str]:
    return {
        entry["hypothesis"]: entry["verdict"]
        for entry in payload["reasoning"]["differential"]
    }


def _claim(payload: dict, claim_id: str) -> dict:
    return next(
        claim for claim in payload["reasoning"]["claims"] if claim["claim_id"] == claim_id
    )


def _reasoning_texts(payload: dict) -> list[str]:
    reasoning = payload["reasoning"]
    return [claim["text"] for claim in reasoning["claims"]] + [
        entry["because"] for entry in reasoning["differential"]
    ]


def _facts_values(facts: dict) -> list:
    values: list = [facts["samples"], facts["window_hours"]]
    for name in COLUMNS:
        values.extend(facts[name].values())
    return values


def _number_tokens(values) -> set[str]:
    """Every way a value can be written in prose, at zero to three decimals."""
    tokens: set[str] = set()
    for value in values:
        if value is None:
            continue
        if isinstance(value, int):
            tokens.add(str(value))
            continue
        for digits in range(0, 4):
            tokens.add(f"{value:.{digits}f}")
            tokens.add(f"{abs(value):.{digits}f}")
    return tokens


def _assert_citations_resolve(payload: dict) -> None:
    reasoning = payload["reasoning"]
    valid = set(payload["provenance"]["evidence_ids"])
    claims = reasoning["claims"]
    differential = reasoning["differential"]
    assert len(claims) == 5
    assert len(differential) == 3
    for entry in claims + differential:
        assert entry["refs"], entry
        assert set(entry["refs"]) <= valid, entry
    guardrail = reasoning["guardrail"]
    assert guardrail["claims"] == len(claims)
    assert guardrail["cited"] == sum(1 for claim in claims if claim["refs"])
    assert guardrail["unsupported"] == sum(1 for claim in claims if not claim["refs"])
    assert guardrail["cited"] + guardrail["unsupported"] == guardrail["claims"]
    distinct = {ref for entry in claims + differential for ref in entry["refs"]}
    assert guardrail["refs_resolved"] == len(distinct)


def test_fouling_series_supports_fouling_and_clears_the_other_two():
    payload = _payload(FOULING_SERIES)
    reasoning = payload["reasoning"]

    assert reasoning["generated_by"] == "deterministic-v1"
    assert list(reasoning) == ["generated_by", "facts", "claims", "differential", "guardrail"]
    assert list(reasoning["facts"]) == ["samples", "window_hours", *COLUMNS]

    claims = reasoning["claims"]
    assert [claim["claim_id"] for claim in claims] == ["C-1", "C-2", "C-3", "C-4", "C-5"]
    assert [claim["kind"] for claim in claims] == [
        "observation",
        "inference",
        "inference",
        "inference",
        "action",
    ]
    for claim in claims:
        assert claim["text"].strip()
        assert 0 < claim["confidence"] <= 1

    assert _verdicts(payload) == {
        "Hydraulic path fouling": "supported",
        "Restricted suction line or a partly closed valve": "less likely",
        "Flow sensor drift": "less likely",
    }
    for verdict in _verdicts(payload).values():
        assert verdict in {"supported", "less likely", "cannot separate"}

    facts = reasoning["facts"]
    assert facts["samples"] == SAMPLE_COUNT
    assert facts["window_hours"] == pytest.approx(3.5, abs=0.05)
    assert facts["flow"]["delta_pct"] < 0
    assert abs(facts["pressure"]["delta_pct"]) < diagnose.FOULING_PRESSURE_STABLE_PCT

    valid = set(payload["provenance"]["evidence_ids"])
    assert valid
    for claim in claims:
        assert set(claim["refs"]) <= valid, claim["claim_id"]
    assert any(claim["refs"] for claim in claims)


def test_pressure_collapse_does_not_clear_the_suction_hypothesis():
    payload = _payload(COLLAPSE_SERIES)
    verdicts = _verdicts(payload)

    assert verdicts["Restricted suction line or a partly closed valve"] == "cannot separate"
    assert verdicts["Hydraulic path fouling"] == "cannot separate"

    suction = next(
        entry
        for entry in payload["reasoning"]["differential"]
        if entry["hypothesis"] == "Restricted suction line or a partly closed valve"
    )
    assert "cannot be separated" in suction["because"]

    # No prose may claim a held head when the pressure collapses with the flow.
    for text in _reasoning_texts(payload):
        assert "is not a collapse in head" not in text
        assert "the head did not move" not in text

    pressure_claim = _claim(payload, "C-2")
    assert "not excluded" in pressure_claim["text"]
    assert "33.33" in pressure_claim["text"]
    assert payload["reasoning"]["facts"]["pressure"]["delta_pct"] == pytest.approx(
        -33.33, abs=0.01
    )


def test_mild_flow_fall_still_clears_the_sensor_drift_hypothesis():
    payload = _payload(MILD_SERIES)
    verdicts = _verdicts(payload)

    # A 5 percent fall is below the fouling bar but it is still a fall, so the
    # current rise still argues against a sensor-only explanation.
    assert verdicts["Flow sensor drift"] == "less likely"
    assert verdicts["Hydraulic path fouling"] == "cannot separate"
    assert verdicts["Restricted suction line or a partly closed valve"] == "less likely"
    facts = payload["reasoning"]["facts"]
    assert facts["flow"]["delta_pct"] == pytest.approx(-5.0, abs=0.01)
    assert facts["motor_current"]["delta_pct"] == pytest.approx(5.0, abs=0.01)


@SKIP_NO_PACK
def test_facts_match_an_independent_recompute_from_the_equipment_pack():
    pack = json.loads(PACK.read_text())
    facts = diagnose.diagnose(pack)["reasoning"]["facts"]
    asset = next(row for row in pack["assets"] if row.get("tag") == "P-005")
    rows = sorted(
        (row for row in pack["tables"]["telemetry"] if row.get("asset_id") == asset["asset_id"]),
        key=lambda row: float(row["timestamp"]),
    )

    assert facts["samples"] == len(rows) == 144
    span = (float(rows[-1]["timestamp"]) - float(rows[0]["timestamp"])) * 24.0
    assert facts["window_hours"] == round(span, 1) == 71.5

    for name, column in COLUMNS.items():
        values = [float(row[column]) for row in rows if row.get(column) not in ("", None)]
        first, last = values[0], values[-1]
        assert round(facts[name]["first"], 2) == round(first, 2), name
        assert round(facts[name]["last"], 2) == round(last, 2), name
        expected = round(100.0 * (last - first) / first, 2)
        assert facts[name]["delta_pct"] == pytest.approx(expected, abs=0.005), name

    assert facts == {
        "samples": 144,
        "window_hours": 71.5,
        "flow": {"first": 75.394, "last": 64.557, "delta_pct": -14.37},
        "pressure": {"first": 4.508, "last": 4.509, "delta_pct": 0.02},
        "vibration": {"first": 2.223, "last": 2.082, "delta_pct": -6.34},
        "bearing_temp": {"first": 55.734, "last": 56.398, "delta_pct": 1.19},
        "motor_current": {"first": 42.806, "last": 45.559, "delta_pct": 6.43},
        "speed": {"first": 1484.891, "last": 1480.139, "delta_pct": -0.32},
    }


def test_refs_resolve_and_the_guardrail_counters_agree():
    _assert_citations_resolve(_payload(FOULING_SERIES))


@SKIP_NO_PACK
def test_equipment_pack_verdicts_follow_the_computed_facts():
    payload = diagnose.diagnose(json.loads(PACK.read_text()))
    _assert_citations_resolve(payload)
    assert _verdicts(payload) == {
        "Hydraulic path fouling": "supported",
        "Restricted suction line or a partly closed valve": "less likely",
        "Flow sensor drift": "less likely",
    }
    confidence = payload["findings"][0]["confidence"]
    for claim in payload["reasoning"]["claims"]:
        assert claim["confidence"] == confidence


def test_claim_numbers_come_only_from_the_computed_facts():
    for series in (FOULING_SERIES, COLLAPSE_SERIES, MILD_SERIES):
        payload = _payload(series)
        allowed = _number_tokens(_facts_values(payload["reasoning"]["facts"]))
        for claim in payload["reasoning"]["claims"]:
            for token in NUMBER.findall(claim["text"]):
                assert token in allowed, (claim["claim_id"], token, claim["text"])


def test_differential_numbers_come_from_facts_or_the_named_thresholds():
    thresholds = (
        diagnose.FOULING_FLOW_DROP_PCT,
        diagnose.FOULING_SPEED_STABLE_PCT,
        diagnose.FOULING_PRESSURE_STABLE_PCT,
        diagnose.SENSOR_DRIFT_CURRENT_RISE_PCT,
    )
    for series in (FOULING_SERIES, COLLAPSE_SERIES, MILD_SERIES):
        payload = _payload(series)
        allowed = _number_tokens(_facts_values(payload["reasoning"]["facts"]))
        allowed |= _number_tokens(thresholds)
        for entry in payload["reasoning"]["differential"]:
            for token in NUMBER.findall(entry["because"]):
                assert token in allowed, (entry["hypothesis"], token, entry["because"])


def test_reasoning_is_byte_identical_across_runs(tmp_path):
    pack = _synthetic_pack(FOULING_SERIES)
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    diagnose.diagnose(pack, output=first)
    diagnose.diagnose(pack, output=second)
    assert first.read_bytes() == second.read_bytes()
    assert (
        json.loads(first.read_text())["reasoning"]
        == json.loads(second.read_text())["reasoning"]
    )
