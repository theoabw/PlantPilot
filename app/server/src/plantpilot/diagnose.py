"""Build an evidence-backed diagnosis from the local builder pack.

The artifact stays deterministic and offline: every field is a join over the
pack tables and the synthetic knowledge documents. Findings carry a browsable
`evidence` list (telemetry rows, alarm events, data-quality cases and document
excerpts), the condition finding carries a sparkline sized `trend`, and the
citations carry short verbatim excerpts rather than a full document.

The Valmet documents are never copied into this artifact. The knowledge rows
here are synthetic context notes, and only a short excerpt is carried.
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path


class DiagnosisError(ValueError):
    """The pack does not contain enough information for a diagnosis."""


# Numeric telemetry columns carried into evidence and trend values. A column
# that is empty for the target asset is simply left out of the item.
TELEMETRY_FIELDS = (
    "process_pressure_bar",
    "process_flow_pct",
    "vibration_mm_s",
    "bearing_temp_c",
    "motor_current_a",
    "speed_rpm",
)

# The primary condition metric per issue code. FOULING is a flow-loss signature,
# so delivered flow is the metric a person would watch; the other channels are
# corroboration. Unknown issues fall back to the first usable numeric series.
ISSUE_METRICS = {
    "FOULING": {
        "field": "process_flow_pct",
        "unit": "percent",
        "why": (
            "FOULING is an efficiency loss for a pump: at a steady speed the delivered flow falls as "
            "the hydraulic path fouls, so process_flow_pct is the primary condition metric. Pressure, "
            "vibration, bearing temperature and motor current are the corroborating checks."
        ),
    },
    "CAVITATION_RISK": {
        "field": "vibration_mm_s",
        "unit": "mm/s",
        "why": (
            "CAVITATION_RISK shows up first as pump vibration and noise, so vibration_mm_s is the "
            "primary condition metric. Flow, pressure and motor current corroborate it."
        ),
    },
    "OVERHEATING": {
        "field": "bearing_temp_c",
        "unit": "C",
        "why": (
            "OVERHEATING is a thermal signature, so bearing_temp_c is the primary condition metric. "
            "Vibration and motor current corroborate the load side."
        ),
    },
    "POSITION_DEVIATION": {
        "field": "position_actual_pct",
        "unit": "percent",
        "why": (
            "POSITION_DEVIATION is about the valve position following its setpoint, so "
            "position_actual_pct is the primary condition metric."
        ),
    },
    "STICTION": {
        "field": "stiction_index",
        "unit": "index",
        "why": (
            "STICTION is a friction signature in the valve travel, so stiction_index is the primary "
            "condition metric; supply pressure and position error corroborate it."
        ),
    },
}

TELEMETRY_LABELS = {
    "process_pressure_bar": ("pressure", "bar"),
    "process_flow_pct": ("flow", "percent"),
    "vibration_mm_s": ("vibration", "mm/s"),
    "bearing_temp_c": ("bearing temperature", "C"),
    "motor_current_a": ("motor current", "A"),
    "speed_rpm": ("speed", "rpm"),
}

TREND_WINDOW = 16
TREND_MIN_POINTS = 5

_EXCEL_EPOCH = datetime(1899, 12, 30, tzinfo=timezone.utc)
_SEVERITY_ORDER = ("high", "medium", "low")


def _evidence_id(table: str, index: int) -> str:
    return f"{table}:{index + 1:05d}"


def _rows_for(rows: list[dict], asset_id: str) -> list[tuple[int, dict]]:
    return [(index, row) for index, row in enumerate(rows) if row.get("asset_id") == asset_id]


def _is_filled(value) -> bool:
    return value not in ("", None)


def _numeric_summary(rows: list[dict], field: str) -> dict | None:
    values = []
    for row in rows:
        value = row.get(field)
        if not _is_filled(value):
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


def _iso_timestamp(serial) -> str | None:
    """Excel serial day number to a UTC ISO 8601 string, deterministic at one second."""
    try:
        value = float(serial)
    except (TypeError, ValueError):
        return None
    return (_EXCEL_EPOCH + timedelta(days=value)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _one_line(text: str, limit: int = 180) -> str:
    collapsed = " ".join(str(text or "").split())
    return collapsed if len(collapsed) <= limit else collapsed[: limit - 4].rstrip() + " ..."


def _telemetry_value(row: dict) -> dict:
    value = {}
    if _is_filled(row.get("timestamp")):
        value["timestamp"] = row["timestamp"]
    for field in TELEMETRY_FIELDS:
        if _is_filled(row.get(field)):
            value[field] = row[field]
    return value


def _telemetry_label(row: dict) -> str:
    parts = []
    stamp = _iso_timestamp(row.get("timestamp"))
    if stamp:
        parts.append(stamp)
    if _is_filled(row.get("process_flow_pct")):
        parts.append(f"flow {float(row['process_flow_pct']):.3f} percent")
    if _is_filled(row.get("process_pressure_bar")):
        parts.append(f"pressure {float(row['process_pressure_bar']):.3f} bar")
    if _is_filled(row.get("vibration_mm_s")):
        parts.append(f"vibration {float(row['vibration_mm_s']):.3f} mm/s")
    return ", ".join(parts) or "telemetry row"


def _telemetry_item(index: int, row: dict) -> dict:
    value = _telemetry_value(row)
    parts = []
    for field, (name, unit) in TELEMETRY_LABELS.items():
        if field in value:
            parts.append(f"{name} {value[field]} {unit}")
    stamp = _iso_timestamp(row.get("timestamp")) or "unknown time"
    detail = f"Telemetry row {index + 1} ({stamp}): " + ", ".join(parts)
    return {
        "evidence_id": _evidence_id("telemetry", index),
        "ref": f"TELEMETRY-{index + 1:05d}",
        "kind": "telemetry",
        "label": _telemetry_label(row),
        "value": value,
        "detail": detail or "no numeric channels in this row",
        "source": "telemetry",
        "summary": {
            key: row[key]
            for key in ("timestamp",) + TELEMETRY_FIELDS
            if _is_filled(row.get(key))
        },
    }


def _alarm_item(index: int, row: dict) -> dict:
    event_id = str(row.get("event_id") or "")
    suffix = event_id[4:] if event_id.startswith("EVT-") else f"{index + 1:05d}"
    stamp = _iso_timestamp(row.get("timestamp")) or str(row.get("timestamp"))
    return {
        "evidence_id": _evidence_id("alarms_events", index),
        "ref": f"ALARM-{suffix}",
        "kind": "alarm",
        "label": _one_line(
            f"{stamp} {row.get('event_type')} {row.get('severity')}: {row.get('description')}"
        ),
        "value": row.get("event_code"),
        "detail": (
            f"{event_id} {row.get('status')} from {row.get('source')}; "
            f"code {row.get('event_code')}, severity {row.get('severity')}"
        ),
        "source": "alarms_events",
        "event_type": row.get("event_type"),
        "severity": row.get("severity"),
        "event_code": row.get("event_code"),
        "event_id": event_id,
        "description": row.get("description"),
    }


def _quality_item(index: int, row: dict) -> dict:
    issue_id = str(row.get("issue_id") or f"DQ-{index + 1:04d}")
    return {
        "evidence_id": _evidence_id("data_quality", index),
        "ref": issue_id,
        "kind": "data_quality",
        "label": _one_line(
            f"{row.get('issue_type')} ({row.get('severity')}) on {row.get('source_sheet')}: "
            f"{row.get('recommended_handling')}"
        ),
        "value": row.get("issue_type"),
        "detail": (
            f"{issue_id} flags {row.get('issue_type')} at {row.get('severity')} severity on the "
            f"{row.get('source_sheet')} sheet; recommended handling: {row.get('recommended_handling')}"
        ),
        "source": "data_quality",
        "issue_type": row.get("issue_type"),
        "severity": row.get("severity"),
        "source_sheet": row.get("source_sheet"),
        "recommended_handling": row.get("recommended_handling"),
    }


def _short_excerpt(content: str, max_words: int = 25) -> tuple[str, int]:
    """The first sentence, or at most max_words words, as a verbatim quote."""
    text = " ".join(str(content or "").split())
    if not text:
        return "", 0
    words = text.split(" ")
    selected: list[str] = []
    for word in words[:max_words]:
        selected.append(word)
        if word.endswith((".", "!", "?")):
            break
    excerpt = " ".join(selected)
    if len(selected) < len(words) and not selected[-1].endswith((".", "!", "?")):
        excerpt += " ..."
    return excerpt, len(selected)


def _citation(doc: dict) -> dict:
    excerpt, words = _short_excerpt(doc.get("content"), max_words=25)
    citation = {
        "doc_id": doc.get("doc_id"),
        "title": doc.get("title"),
        "scope": doc.get("scope"),
        "section": doc.get("section"),
        "page": doc.get("page"),
        "excerpt": excerpt,
        "excerpt_words": words,
        "synthetic_record": bool(doc.get("synthetic_record")),
    }
    return citation


def _document_item(citation: dict) -> dict:
    return {
        "evidence_id": f"documents:{citation['doc_id']}",
        "ref": citation["doc_id"],
        "kind": "document",
        "label": _one_line(f"{citation['title']}: {citation['excerpt']}"),
        "value": citation["excerpt"],
        "detail": {
            "scope": citation["scope"],
            "section": citation["section"],
            "page": citation["page"],
            "excerpt_words": citation["excerpt_words"],
        },
        "source": "knowledge_docs",
    }


def _trend_points(rows: list[dict], field: str, window: int | None = None) -> list[dict]:
    points = []
    for row in rows:
        value = row.get(field)
        if not _is_filled(value):
            continue
        try:
            number = float(value)
        except (TypeError, ValueError):
            continue
        points.append(
            {
                "timestamp": _iso_timestamp(row.get("timestamp")),
                "timestamp_serial": row.get("timestamp"),
                "value": number,
            }
        )
    return points if window is None else points[-window:]


def _slope(values: list[float]) -> float:
    count = len(values)
    if count < 2:
        return 0.0
    mean_x = statistics.fmean(range(count))
    mean_y = statistics.fmean(values)
    denominator = sum((index - mean_x) ** 2 for index in range(count))
    numerator = sum((index - mean_x) * (value - mean_y) for index, value in enumerate(values))
    return numerator / denominator if denominator else 0.0


def _build_trend(rows: list[dict], asset_id: str, issue_code: str) -> dict:
    """The primary condition series for the issue, last TREND_WINDOW points."""
    issue = str(issue_code or "").upper()
    choice = ISSUE_METRICS.get(issue)
    candidates = []
    if choice is not None:
        candidates.append(choice["field"])
    for field in TELEMETRY_FIELDS:
        if field not in candidates:
            candidates.append(field)

    for field in candidates:
        series = _trend_points(rows, field)
        if len(series) < TREND_MIN_POINTS:
            continue
        points = series[-TREND_WINDOW:]
        values = [point["value"] for point in points]
        first, last = values[0], values[-1]
        change = round(last - first, 3)
        change_percent = round(change / abs(first) * 100.0, 2) if first else None
        why = (
            choice["why"]
            if choice is not None and field == choice["field"]
            else f"{field} has {len(points)} usable values and is used as the nearest usable series."
        )
        why = (
            f"{why} The field has {len(series)} usable samples; the last {len(points)} are shown, "
            f"from {points[0]['timestamp']} to {points[-1]['timestamp']}."
        )
        return {
            "available": True,
            "metric": field,
            "unit": choice["unit"] if choice is not None and field == choice["field"] else None,
            "issue_code": issue or None,
            "window": len(points),
            "why": why,
            "points": points,
            "summary": {
                "first": first,
                "last": last,
                "change": change,
                "change_percent": change_percent,
                "min": min(values),
                "max": max(values),
                "slope_per_sample": round(_slope(values), 6),
            },
        }

    reason = (
        f"no telemetry series for {asset_id} has at least {TREND_MIN_POINTS} numeric values; "
        "the sparkline is omitted rather than drawn from a partial join"
    )
    return {
        "available": False,
        "metric": choice["field"] if choice is not None else None,
        "unit": choice["unit"] if choice is not None else None,
        "issue_code": issue or None,
        "window": 0,
        "why": choice["why"] if choice is not None else "no issue-specific metric is defined",
        "reason": reason,
        "points": [],
        "summary": None,
    }


def _confidence_effect(quality: list[tuple[int, dict]], prior: float, final: float) -> str:
    if not quality:
        return f"no data-quality cases touch this asset; confidence stays at {prior:.2f}"
    severities = Counter(str(row.get("severity")) for _, row in quality)
    issues = Counter(str(row.get("issue_type")) for _, row in quality)
    severity_text = ", ".join(
        f"{severities[name]} {name}"
        for name in _SEVERITY_ORDER
        if severities.get(name)
    )
    issue_text = ", ".join(
        f"{name} {count}" for name, count in sorted(issues.items(), key=lambda item: (-item[1], item[0]))
    )
    return (
        f"{len(quality)} data-quality cases ({severity_text}; {issue_text}) reduce the reported "
        f"confidence from {prior:.2f} to {final:.2f}. Treat the diagnosis as directional until the "
        "flagged timestamps, duplicate events and sensor-quality drops are confirmed."
    )


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

    # Browsable evidence: each item names the pack row it came from, so the UI
    # can show a reference id next to the value.
    telemetry_items = [_telemetry_item(index, row) for index, row in telemetry[-5:]]
    event_pool = [
        (index, row)
        for index, row in events
        if row.get("event_code") == asset.get("issue_code") or row.get("severity") == "high"
    ]
    event_items = [_alarm_item(index, row) for index, row in event_pool[:5]]
    quality_items = [_quality_item(index, row) for index, row in quality]

    citations = [_citation(documents[doc_id]) for doc_id in cited_ids]
    document_items = [_document_item(citation) for citation in citations]

    evidence_ids = [item["evidence_id"] for item in telemetry_items + event_items + quality_items]
    quality_penalty = min(0.35, 0.05 * len(quality_items))
    prior_confidence = round(float(asset.get("model_confidence", 0.0)), 3)
    confidence = round(max(0.1, prior_confidence - quality_penalty), 3)
    trend = _build_trend([row for _, row in telemetry], asset_id, str(asset.get("issue_code", "")))
    effect = _confidence_effect(quality, prior_confidence, confidence)

    condition_evidence = telemetry_items + event_items + [document_items[0]]
    health_evidence = (
        quality_items
        + document_items[1:]
        + [item for item in event_items if item["severity"] == "high"][:3]
    )
    findings = [
        {
            "finding_id": "F-001",
            "type": "condition",
            "statement": f"{asset['condition_state']}: {asset['issue_summary']}",
            "evidence_ids": evidence_ids,
            "confidence": confidence,
            "evidence": condition_evidence,
        },
        {
            "finding_id": "F-002",
            "type": "health",
            "statement": f"Health score is {asset['health_score']} with {asset['urgency']} urgency.",
            "evidence_ids": evidence_ids[: max(1, len(evidence_ids) // 2)],
            "confidence": confidence,
            "evidence": health_evidence,
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
        "trend": trend,
        "telemetry": {
            "rows": len(telemetry),
            "evidence": telemetry_items,
            "summaries": [
                summary
                for field in TELEMETRY_FIELDS
                if (summary := _numeric_summary([row for _, row in telemetry], field)) is not None
            ],
        },
        "alarms": {
            "rows": len(events),
            "evidence": event_items,
        },
        "data_quality": {
            "cases": len(quality_items),
            "evidence": quality_items,
            "confidence_penalty": round(quality_penalty, 3),
            "confidence_effect": effect,
            "severity_counts": {
                name: int(Counter(str(row.get("severity")) for _, row in quality).get(name, 0))
                for name in _SEVERITY_ORDER
            },
        },
        "maintenance_history": {
            "rows": len(history),
            "latest": history[-1][1] if history else None,
        },
        "citations": citations,
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
    trend = payload["trend"]
    if trend["available"]:
        print(f"trend               {trend['metric']} {len(trend['points'])} points "
              f"({trend['summary']['first']:.3f} to {trend['summary']['last']:.3f} {trend['unit']})")
    else:
        print(f"trend               unavailable: {trend['reason']}")
    print(f"evidence items      {sum(len(finding['evidence']) for finding in payload['findings'])}")
    print(f"wrote               {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
