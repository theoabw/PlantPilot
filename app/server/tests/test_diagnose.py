import json
from pathlib import Path

import pytest

from plantpilot import diagnose


PACK = Path("data/scene/pack.json")
SKIP_NO_PACK = pytest.mark.skipif(not PACK.exists(), reason="builder pack not supplied")
ALLOWED_KINDS = {"telemetry", "alarm", "data_quality", "document"}
TELEMETRY_FIELDS = (
    "process_pressure_bar",
    "process_flow_pct",
    "vibration_mm_s",
    "bearing_temp_c",
    "motor_current_a",
    "speed_rpm",
)


def _pack() -> dict:
    return json.loads(PACK.read_text())


def _payload() -> dict:
    return diagnose.diagnose(_pack())


@SKIP_NO_PACK
def test_diagnosis_is_grounded_and_confidence_reflects_data_quality(tmp_path):
    output = tmp_path / "diagnosis.json"
    payload = diagnose.diagnose(_pack(), output=output)

    assert output.exists()
    assert payload["artifact"] == "diagnosis"
    assert payload["target"]["tag"] == "P-005"
    assert payload["telemetry"]["rows"] == 144
    assert payload["alarms"]["rows"] == 34
    assert payload["data_quality"]["cases"] == 9
    assert len(payload["citations"]) >= 2
    assert payload["next_safe_check"]["document_id"] == "DOC-FIELD-SAFETY"
    assert payload["findings"][0]["confidence"] < 0.91
    valid_ids = set(payload["provenance"]["evidence_ids"])
    assert valid_ids
    for finding in payload["findings"]:
        assert set(finding["evidence_ids"]) <= valid_ids


@SKIP_NO_PACK
def test_every_finding_carries_concrete_pack_evidence():
    payload = _payload()
    kinds = set()
    for finding in payload["findings"]:
        items = finding["evidence"]
        assert items, f"{finding['finding_id']} has no evidence"
        for item in items:
            assert item["kind"] in ALLOWED_KINDS
            assert isinstance(item["label"], str) and item["label"].strip()
            assert item["ref"]
            assert item.get("value") is not None or item.get("detail")
            kinds.add(item["kind"])
    assert kinds == ALLOWED_KINDS


@SKIP_NO_PACK
def test_telemetry_evidence_values_match_pack_rows_exactly():
    pack = _pack()
    rows = pack["tables"]["telemetry"]
    payload = _payload()
    items = [item for finding in payload["findings"] for item in finding["evidence"] if item["kind"] == "telemetry"]
    assert items
    for item in items:
        table_index = int(item["ref"].removeprefix("TELEMETRY-")) - 1
        row = rows[table_index]
        expected = {key: row[key] for key in item["value"]}
        assert item["value"] == expected, item["ref"]
        assert row["asset_id"] == payload["target"]["asset_id"]


@SKIP_NO_PACK
def test_trend_is_a_usable_series_or_explains_the_omission():
    pack = _pack()
    payload = _payload()
    asset_id = payload["target"]["asset_id"]
    trend = payload["trend"]
    rows = [row for row in pack["tables"]["telemetry"] if row.get("asset_id") == asset_id]
    if trend.get("available"):
        points = trend["points"]
        assert 5 <= len(points) <= 20, "the sparkline window must be small"
        assert len(points) <= 20
        assert all(isinstance(point["value"], (int, float)) for point in points)
        assert all(point["timestamp"] for point in points)
        assert [point["timestamp"] for point in points] == sorted(point["timestamp"] for point in points)
        field = trend["metric"]
        assert field in TELEMETRY_FIELDS
        assert trend["why"].strip()
        series = [float(row[field]) for row in rows if row.get(field) not in ("", None)]
        assert [point["value"] for point in points] == series[-len(points):]
        summary = trend["summary"]
        assert summary["first"] == points[0]["value"]
        assert summary["last"] == points[-1]["value"]
    else:
        assert trend.get("reason"), "an omitted trend must say why"


@SKIP_NO_PACK
def test_every_citation_has_a_short_verbatim_excerpt():
    pack = _pack()
    payload = _payload()
    documents = {doc["doc_id"]: doc for doc in pack["tables"]["knowledge_docs"]}
    assert payload["citations"]
    for citation in payload["citations"]:
        assert citation["doc_id"] in documents
        assert citation["title"]
        assert "content" not in citation, "the full document must not be copied into the artifact"
        excerpt = citation["excerpt"]
        assert excerpt and citation["excerpt_words"] >= 1
        assert citation["excerpt_words"] <= 25
        assert len(excerpt.split()) <= 25
        quote = excerpt[:-4] if excerpt.endswith(" ...") else excerpt
        assert quote in documents[citation["doc_id"]]["content"], "the excerpt must be a verbatim quote"
        assert "section" in citation and "page" in citation


@SKIP_NO_PACK
def test_data_quality_cases_are_referenced_and_explained():
    pack = _pack()
    payload = _payload()
    asset_id = payload["target"]["asset_id"]
    rows = [row for row in pack["tables"]["data_quality"] if row.get("asset_id") == asset_id]
    section = payload["data_quality"]
    items = section["evidence"]
    assert items
    assert len(items) == section["cases"] == len(rows)
    assert {item["ref"] for item in items} == {row["issue_id"] for row in rows}
    for item in items:
        assert item["kind"] == "data_quality"
        assert item["value"] in {"timestamp_jitter", "duplicate_event", "sensor_quality_drop", "missing_value"}
        assert item["detail"] and item["severity"]
    assert section["confidence_effect"].strip()
    assert "confidence" in section["confidence_effect"]
    finding_refs = {item["ref"] for finding in payload["findings"] for item in finding["evidence"]}
    assert {item["ref"] for item in items} <= finding_refs


@SKIP_NO_PACK
def test_artifact_is_byte_identical_across_runs(tmp_path):
    first = tmp_path / "first.json"
    second = tmp_path / "second.json"
    payload_first = diagnose.diagnose(_pack(), output=first)
    payload_second = diagnose.diagnose(_pack(), output=second)
    assert payload_first == payload_second
    assert first.read_bytes() == second.read_bytes()


def test_unknown_diagnosis_target_fails():
    with pytest.raises(diagnose.DiagnosisError, match="not in the pack"):
        diagnose.diagnose({"assets": [], "tables": {}}, "P-999")
