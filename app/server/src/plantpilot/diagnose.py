"""Build an evidence-backed diagnosis from the local builder pack."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path


class DiagnosisError(ValueError):
    """The pack does not contain enough information for a diagnosis."""


def _evidence_id(table: str, index: int) -> str:
    return f"{table}:{index + 1:05d}"


def _rows_for(rows: list[dict], asset_id: str) -> list[tuple[int, dict]]:
    return [(index, row) for index, row in enumerate(rows) if row.get("asset_id") == asset_id]


def _numeric_summary(rows: list[dict], field: str) -> dict | None:
    values = []
    for row in rows:
        value = row.get(field)
        if value in ("", None):
            continue
        try:
            values.append(float(value))
        except (TypeError, ValueError):
            continue
    if not values:
        return None
    return {
        "field": field,
        "count": len(values),
        "min": round(min(values), 3),
        "max": round(max(values), 3),
        "mean": round(statistics.fmean(values), 3),
    }


def diagnose(pack: dict, target_tag: str = "P-005", output: Path | None = None) -> dict:
    asset = next((row for row in pack.get("assets", []) if row.get("tag") == target_tag), None)
    if asset is None:
        raise DiagnosisError(f"target asset {target_tag} is not in the pack")
    asset_id = str(asset["asset_id"])
    tables = pack.get("tables", {})
    telemetry = _rows_for(tables.get("telemetry", []), asset_id)
    events = _rows_for(tables.get("alarms_events", []), asset_id)
    quality = _rows_for(tables.get("data_quality", []), asset_id)
    history = _rows_for(tables.get("maintenance_history", []), asset_id)

    documents = {
        str(row.get("doc_id")): row
        for row in tables.get("knowledge_docs", [])
        if row.get("doc_id")
    }
    core_doc_id = str(asset.get("knowledge_doc_id", ""))
    cited_ids = [doc_id for doc_id in (core_doc_id, "DOC-FIELD-SAFETY") if doc_id in documents]
    if len(cited_ids) < 2:
        raise DiagnosisError("target requires a core document and field-safety document")

    telemetry_evidence = [
        {
            "evidence_id": _evidence_id("telemetry", index),
            "source": "telemetry",
            "summary": {
                key: row[key]
                for key in ("timestamp", "process_pressure_bar", "process_flow_pct",
                            "vibration_mm_s", "bearing_temp_c", "motor_current_a")
                if row.get(key) not in ("", None)
            },
        }
        for index, row in telemetry[-5:]
    ]
    event_evidence = [
        {
            "evidence_id": _evidence_id("alarms_events", index),
            "source": "alarms_events",
            "event_type": row.get("event_type"),
            "severity": row.get("severity"),
            "event_code": row.get("event_code"),
            "description": row.get("description"),
        }
        for index, row in events
        if row.get("event_code") == asset.get("issue_code") or row.get("severity") == "high"
    ][:5]
    quality_evidence = [
        {
            "evidence_id": _evidence_id("data_quality", index),
            "source": "data_quality",
            "issue_type": row.get("issue_type"),
            "severity": row.get("severity"),
            "recommended_handling": row.get("recommended_handling"),
        }
        for index, row in quality
    ]

    evidence_ids = [
        item["evidence_id"]
        for item in telemetry_evidence + event_evidence + quality_evidence
    ]
    quality_penalty = min(0.35, 0.05 * len(quality_evidence))
    confidence = round(max(0.1, float(asset.get("model_confidence", 0.0)) - quality_penalty), 3)
    findings = [
        {
            "finding_id": "F-001",
            "type": "condition",
            "statement": f"{asset['condition_state']}: {asset['issue_summary']}",
            "evidence_ids": evidence_ids,
            "confidence": confidence,
        },
        {
            "finding_id": "F-002",
            "type": "health",
            "statement": f"Health score is {asset['health_score']} with {asset['urgency']} urgency.",
            "evidence_ids": evidence_ids[: max(1, len(evidence_ids) // 2)],
            "confidence": confidence,
        },
    ]
    payload = {
        "artifact": "diagnosis",
        "version": 1,
        "target": {
            "asset_id": asset_id,
            "tag": target_tag,
            "class": asset.get("asset_class"),
            "area": asset.get("area_name"),
        },
        "condition": asset.get("condition_state"),
        "health_score": asset.get("health_score"),
        "issue": {
            "code": asset.get("issue_code"),
            "summary": asset.get("issue_summary"),
            "urgency": asset.get("urgency"),
        },
        "findings": findings,
        "telemetry": {
            "rows": len(telemetry),
            "evidence": telemetry_evidence,
            "summaries": [
                summary
                for field in ("process_pressure_bar", "process_flow_pct", "vibration_mm_s",
                              "bearing_temp_c", "motor_current_a")
                if (summary := _numeric_summary([row for _, row in telemetry], field)) is not None
            ],
        },
        "alarms": {
            "rows": len(events),
            "evidence": event_evidence,
        },
        "data_quality": {
            "cases": len(quality_evidence),
            "evidence": quality_evidence,
            "confidence_penalty": round(quality_penalty, 3),
        },
        "maintenance_history": {
            "rows": len(history),
            "latest": history[-1][1] if history else None,
        },
        "citations": [
            {
                "doc_id": doc_id,
                "title": documents[doc_id].get("title"),
                "scope": documents[doc_id].get("scope"),
                "content": documents[doc_id].get("content"),
            }
            for doc_id in cited_ids
        ],
        "next_safe_check": {
            "action": asset.get("recommended_next_check"),
            "document_id": "DOC-FIELD-SAFETY",
            "reason": "Verify locally before maintenance work and request confirmation for data-quality cases.",
        },
        "provenance": {
            "synthetic_data": bool(asset.get("synthetic_record")),
            "offline": True,
            "evidence_ids": evidence_ids,
        },
    }
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build diagnosis.json from pack.json.")
    parser.add_argument("--pack", type=Path, default=Path("data/scene/pack.json"))
    parser.add_argument("--target", default="P-005")
    parser.add_argument("--out", type=Path, default=Path("data/scene/diagnosis.json"))
    args = parser.parse_args(argv)
    try:
        payload = diagnose(json.loads(args.pack.read_text()), args.target, args.out)
    except (OSError, json.JSONDecodeError, DiagnosisError) as exc:
        print(f"diagnosis failed: {exc}", file=sys.stderr)
        return 1
    print(f"target             {payload['target']['tag']} ({payload['target']['asset_id']})")
    print(f"telemetry rows     {payload['telemetry']['rows']}")
    print(f"alarm rows         {payload['alarms']['rows']}")
    print(f"data quality cases {payload['data_quality']['cases']}")
    print(f"documents cited    {len(payload['citations'])}")
    print(f"confidence          {payload['findings'][0]['confidence']}")
    print(f"wrote               {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
