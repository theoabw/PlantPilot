from pathlib import Path

import pytest

from plantpilot import pack


WORKBOOK = Path("data/supplied/builder_pack.xlsx")


@pytest.mark.skipif(not WORKBOOK.exists(), reason="builder pack not supplied")
def test_builder_pack_writes_the_contract(tmp_path):
    output = tmp_path / "pack.json"
    payload = pack.build_pack(WORKBOOK, output)

    assert output.exists()
    assert payload["artifact"] == "pack"
    assert payload["counts"]["asset_master"] == 30
    assert payload["counts"]["telemetry"] == 4320
    assert payload["counts"]["alarms_events"] == 1000
    assert payload["target"] == {
        "asset_id": "ASSET-017",
        "tag": "P-005",
        "reason": "fixed demo target from Current_State",
    }
    assert len(payload["assets"]) == 30
    assert any(row["tag"] == "P-005" for row in payload["assets"])
    assert payload["tables"]["knowledge_docs"]


def test_missing_builder_pack_fails_explicitly(tmp_path):
    with pytest.raises(pack.PackError, match="no builder pack"):
        pack.build_pack(tmp_path / "missing.xlsx", tmp_path / "pack.json")
