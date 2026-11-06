import json

from plantpilot.mapping import map_assets


def _asset(asset_id, tag, asset_class, bbox, condition="healthy", issue="NORMAL"):
    return {
        "asset_id": asset_id,
        "tag": tag,
        "asset_class": asset_class,
        "bbox_x_m": bbox[0],
        "bbox_y_m": bbox[1],
        "bbox_z_m": bbox[2],
        "condition_state": condition,
        "issue_code": issue,
    }


def _object(object_id, object_class, extents, points=100):
    return {"id": object_id, "class": object_class, "extents": list(extents), "points": points}


def _pack(assets, target_asset_id, target_tag):
    return {
        "source": {"file": "builder_pack.xlsx"},
        "target": {"asset_id": target_asset_id, "tag": target_tag},
        "assets": assets,
    }


def _objects(rows):
    return {"source": {"scene": "scene.npz"}, "objects": rows}


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
    assert payload["counts"] == {
        "assets": 2,
        "mapped": 2,
        "unresolved": 0,
        "unmapped_objects": 0,
    }
    assert payload["target_object_id"] == "OBJ-001"
    assert len({mapping["object_id"] for mapping in payload["mappings"]}) == 2
    assert all(mapping["method"] for mapping in payload["mappings"])


def test_size_incompatible_asset_stays_unresolved_and_is_counted(tmp_path):
    pack = _pack(
        [
            _asset("ASSET-P", "P-100", "PROCESS_PUMP", (1.8, 1.0, 1.1), "attention_required", "FOULING"),
            # A class match alone is not enough: this size cannot be the motor.
            _asset("ASSET-M", "M-900", "MOTOR", (40.0, 40.0, 40.0)),
        ],
        "ASSET-P",
        "P-100",
    )
    objects = _objects([
        _object("OBJ-100", "pump", (1.8, 1.0, 1.1)),
        _object("OBJ-101", "motor", (0.5, 0.4, 0.3)),
    ])

    payload = map_assets(pack, objects, tmp_path / "mapped.json")
    by_tag = {mapping["tag"]: mapping for mapping in payload["mappings"]}

    # The oversized workbook asset clears the class prior but not the size
    # gate, so it keeps its workbook fields and borrows no object.
    assert by_tag["M-900"]["status"] == "unresolved"
    assert by_tag["M-900"]["asset_id"] == "ASSET-M"
    assert by_tag["M-900"]["class"] == "MOTOR"
    assert by_tag["M-900"]["object_id"] is None
    assert by_tag["M-900"]["confidence"] is None
    assert by_tag["M-900"]["match_score"] is None
    assert by_tag["M-900"]["reason"]
    assert by_tag["P-100"]["status"] == "proposed"
    assert by_tag["P-100"]["object_id"] == "OBJ-100"
    assert payload["counts"] == {
        "assets": 2,
        "mapped": 1,
        "unresolved": 1,
        "unmapped_objects": 1,
    }


def test_counts_add_up_on_a_normal_run(tmp_path):
    pack = _pack(
        [
            _asset("ASSET-P", "P-100", "PROCESS_PUMP", (1.8, 1.0, 1.1)),
            _asset("ASSET-M", "M-100", "MOTOR", (1.0, 0.8, 1.0), "watch", "MISALIGNMENT"),
            _asset("ASSET-C", "CV-100", "CONTROL_VALVE", (0.6, 0.5, 0.4)),
        ],
        "ASSET-P",
        "P-100",
    )
    objects = _objects([
        _object("OBJ-1", "pump", (1.8, 1.0, 1.1)),
        _object("OBJ-2", "motor", (1.0, 0.8, 1.0)),
        _object("OBJ-3", "valve", (0.6, 0.5, 0.4)),
    ])

    payload = map_assets(pack, objects, tmp_path / "mapped.json")
    mappings = payload["mappings"]
    counts = payload["counts"]

    assert counts["assets"] == 3
    assert counts["mapped"] + counts["unresolved"] == counts["assets"]
    assert counts["mapped"] == len([row for row in mappings if row["status"] == "proposed"])
    assert counts["unresolved"] == len([row for row in mappings if row["status"] == "unresolved"])
    assert counts["unmapped_objects"] == len(payload["unmapped_object_ids"])
    assert counts["mapped"] == 3
    assert counts["unresolved"] == 0
    assert payload["target_object_id"] == "OBJ-1"
    for row in mappings:
        assert row["status"] == "proposed"
        assert row["confidence"] == row["match_score"]
        assert 0.0 <= row["confidence"] <= 1.0
        assert row["reason"] is None


def test_one_object_is_never_proposed_for_two_tags(tmp_path):
    pack = _pack(
        [
            _asset("ASSET-1", "CV-101", "CONTROL_VALVE", (1.0, 0.8, 1.3)),
            _asset("ASSET-2", "CV-102", "CONTROL_VALVE", (1.0, 0.8, 1.3)),
            _asset("ASSET-3", "CV-103", "CONTROL_VALVE", (1.0, 0.8, 1.3)),
        ],
        "ASSET-1",
        "CV-101",
    )
    objects = _objects([
        _object("OBJ-A", "valve", (1.0, 0.8, 1.3), 400),
        _object("OBJ-B", "valve", (1.0, 0.8, 1.3), 300),
        _object("OBJ-C", "valve", (0.95, 0.78, 1.25), 200),
    ])

    payload = map_assets(pack, objects, tmp_path / "mapped.json")
    proposed = [row for row in payload["mappings"] if row["status"] == "proposed"]

    object_ids = [row["object_id"] for row in proposed]
    assert len(object_ids) == len(set(object_ids)) == payload["counts"]["mapped"] == 3
    assert len({row["tag"] for row in proposed}) == 3
    assert not set(object_ids) & set(payload["unmapped_object_ids"])
    assert len({row["asset_id"] for row in payload["mappings"]}) == len(pack["assets"])


def test_target_object_id_is_null_when_target_is_unresolved(tmp_path):
    pack = _pack(
        [
            _asset(
                "ASSET-017",
                "P-005",
                "PROCESS_PUMP",
                (40.0, 40.0, 40.0),
                "attention_required",
                "FOULING",
            ),
        ],
        "ASSET-017",
        "P-005",
    )
    objects = _objects([_object("OBJ-001", "pump", (1.8, 1.0, 1.1))])

    payload = map_assets(pack, objects, tmp_path / "mapped.json")
    target = next(row for row in payload["mappings"] if row["asset_id"] == "ASSET-017")

    assert target["status"] == "unresolved"
    assert payload["target_asset_id"] == "ASSET-017"
    assert payload["target_tag"] == "P-005"
    assert payload["target_object_id"] is None
    assert payload["counts"]["unresolved"] == 1
