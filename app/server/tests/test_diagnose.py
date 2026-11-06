import json
from pathlib import Path

import pytest

from plantpilot import diagnose


PACK = Path("data/scene/pack.json")


@pytest.mark.skipif(not PACK.exists(), reason="builder pack not supplied")
def test_diagnosis_is_grounded_and_confidence_reflects_data_quality(tmp_path):
    output = tmp_path / "diagnosis.json"
    payload = diagnose.diagnose(json.loads(PACK.read_text()), output=output)

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


def test_unknown_diagnosis_target_fails():
    with pytest.raises(diagnose.DiagnosisError, match="not in the pack"):
        diagnose.diagnose({"assets": [], "tables": {}}, "P-999")
