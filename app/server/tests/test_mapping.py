import json

from plantpilot.mapping import map_assets


def test_mapping_is_distinct_and_marks_the_faulty_target(tmp_path):
    pack = {
        "source": {"file": "builder_pack.xlsx"},
        "target": {"asset_id": "ASSET-017", "tag": "P-005"},
        "assets": [
            {
                "asset_id": "ASSET-017",
                "tag": "P-005",
                "asset_class": "PROCESS_PUMP",
                "bbox_x_m": 1.8,
                "bbox_y_m": 1.0,
                "bbox_z_m": 1.1,
                "condition_state": "attention_required",
                "issue_code": "FOULING",
            },
            {
                "asset_id": "ASSET-018",
                "tag": "M-006",
                "asset_class": "MOTOR",
                "bbox_x_m": 1.0,
                "bbox_y_m": 0.8,
                "bbox_z_m": 1.0,
                "condition_state": "healthy",
                "issue_code": "NORMAL",
            },
        ],
    }
    objects = {
        "source": {"scene": "scene.npz"},
        "objects": [
            {"id": "OBJ-001", "class": "pump", "extents": [1.8, 1.0, 1.1], "points": 100},
            {"id": "OBJ-002", "class": "motor", "extents": [1.0, 0.8, 1.0], "points": 90},
        ],
    }

    output = tmp_path / "mapped.json"
    payload = map_assets(pack, objects, output)

    assert json.loads(output.read_text()) == payload
    assert payload["counts"] == {"assets": 2, "mapped": 2, "unmapped_objects": 0}
    assert payload["target_object_id"] == "OBJ-001"
    assert len({mapping["object_id"] for mapping in payload["mappings"]}) == 2
    assert all(mapping["method"] for mapping in payload["mappings"])
