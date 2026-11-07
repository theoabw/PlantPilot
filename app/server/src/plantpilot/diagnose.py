"""Build an evidence-backed diagnosis from the local builder pack.

The artifact stays deterministic and offline: every field is a join over the
pack tables and the synthetic knowledge documents. Findings carry a browsable
`evidence` list (telemetry rows, alarm events, data-quality cases and document
excerpts), the condition finding carries a sparkline sized `trend`, and the
citations carry short verbatim excerpts rather than a full document.

A `reasoning` block sits on top of the same joined rows: computed facts (first
and last reading, net percentage change and window length per channel), five
cited claims, a three way differential whose verdicts come from named thresholds,
and a guardrail that counts the citations. Every number in that prose is
interpolated from the computed facts, never written by hand.

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

# The reasoning block records which builder produced it, so a later version can
# change the prose without silently changing the meaning of an old artifact.
REASONING_GENERATED_BY = "deterministic-v1"

# Artifact name, pack telemetry column and unit per channel, in the order the
# facts block lists them. The order is fixed because the JSON is compared
# byte for byte across runs.
REASONING_METRICS = (
    ("flow", "process_flow_pct", "percent"),
    ("pressure", "process_pressure_bar", "bar"),
    ("vibration", "vibration_mm_s", "mm/s"),
    ("bearing_temp", "bearing_temp_c", "C"),
    ("motor_current", "motor_current_a", "A"),
    ("speed", "speed_rpm", "rpm"),
)

# Differential thresholds, and why they are these numbers. The pack is a 30
# minute profile resampled across the window, so adjacent samples jump by up to
# about 12 percent in flow and one pair of readings proves nothing. The check
# therefore compares the first and the last reading across the whole window.
# A net flow fall of at least 10 percent is the smallest net loss this check will
# call a loss at all. The speed and pressure bars are deliberately tighter: a net
# change under 1 percent across the window leaves a channel flat, and the fouling
# signature the pack files is flow falling at a steady speed and a steady head.
FOULING_FLOW_DROP_PCT = 10.0
FOULING_SPEED_STABLE_PCT = 1.0
FOULING_PRESSURE_STABLE_PCT = 1.0

# A flow sensor that drifts does not load the motor, so only a real rise in motor
# current argues against a sensor-only explanation, and only on a falling flow:
# there is no sensor error to explain when the flow has not fallen at all. The
# current channel moves by about 3 percent between adjacent samples on average in
# this pack, so a net rise below 3 percent is not distinguishable from that
# scatter.
SENSOR_DRIFT_CURRENT_RISE_PCT = 3.0

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


def _reasoning_rows(rows: list[dict]) -> list[dict]:
    """The target's telemetry rows, oldest first.

    The pack ships the rows in order, but the reasoning sorts them so a first and
    last reading never depend on export order. A row without a numeric timestamp
    sorts after the dated rows, in its original order.
    """

    def key(row: dict) -> tuple[int, float]:
        try:
            return (0, float(row.get("timestamp")))
        except (TypeError, ValueError):
            return (1, 0.0)

    return sorted(rows, key=key)


def _field_values(rows: list[dict], field: str) -> list[float]:
    """The numeric readings of one channel, oldest first, blanks dropped."""
    values = []
    for row in rows:
        value = row.get(field)
        if not _is_filled(value):
            continue
        try:
            values.append(float(value))
        except (TypeError, ValueError):
            continue
    return values


def _round_number(value: float, digits: int) -> float:
    """Round for the artifact and fold -0.0 into 0.0, so the JSON stays stable."""
    rounded = round(value, digits)
    return 0.0 if rounded == 0 else rounded


def _percentage_change(first: float | None, last: float | None) -> float | None:
    """Net percent change across the window, or None when it has no meaning.

    A first reading of zero (or no reading at all) has no percentage change, and
    the caller gets None rather than a division error or an invented number.
    """
    if not first or last is None:
        return None
    return _round_number(100.0 * (last - first) / first, 2)


def _build_reasoning_facts(rows: list[dict]) -> dict:
    """First and last reading per channel, the sample count, and the window span.

    `rows` is the target asset's telemetry, the same rows the findings join over.
    The captured percent changes are net changes across the whole window, never
    the change between two neighbouring samples.
    """
    ordered = _reasoning_rows(rows)
    stamps: list[float] = []
    for row in ordered:
        try:
            stamps.append(float(row.get("timestamp")))
        except (TypeError, ValueError):
            continue
    # The pack stores timestamps as Excel serial day numbers, so the span in
    # hours is the difference in days times 24. One dated row has no window.
    window_hours = (
        _round_number((max(stamps) - min(stamps)) * 24.0, 1) if len(stamps) > 1 else 0.0
    )
    facts = {"samples": len(ordered), "window_hours": window_hours}
    for name, field, _unit in REASONING_METRICS:
        values = _field_values(ordered, field)
        first = values[0] if values else None
        last = values[-1] if values else None
        facts[name] = {
            "first": first,
            "last": last,
            "delta_pct": _percentage_change(first, last),
        }
    return facts


def _reasoning_conditions(facts: dict) -> dict[str, bool]:
    """The threshold tests every verdict is derived from, in one place.

    A missing percentage change is never treated as a satisfied condition.
    """
    flow = facts["flow"]["delta_pct"]
    pressure = facts["pressure"]["delta_pct"]
    speed = facts["speed"]["delta_pct"]
    current = facts["motor_current"]["delta_pct"]
    return {
        "flow_falls": flow is not None and flow <= -FOULING_FLOW_DROP_PCT,
        "flow_drops": flow is not None and flow < 0,
        "speed_steady": speed is not None and abs(speed) < FOULING_SPEED_STABLE_PCT,
        "pressure_steady": pressure is not None and abs(pressure) < FOULING_PRESSURE_STABLE_PCT,
        "current_rises": current is not None and current >= SENSOR_DRIFT_CURRENT_RISE_PCT,
    }


def _number(value: float | None, digits: int) -> str:
    """A facts number as prose, at the same rounding the artifact stores."""
    return "n/a" if value is None else f"{value:.{digits}f}"


def _movement(name: str, delta: float | None, unit: str) -> str:
    """A direction word that always matches the sign of the measured change."""
    if delta is None:
        return f"{name} has no usable change"
    if delta < 0:
        return f"{name} fell {_number(abs(delta), 2)} {unit}"
    if delta > 0:
        return f"{name} rose {_number(delta, 2)} {unit}"
    return f"{name} was flat at {_number(delta, 2)} {unit}"


def _change_phrase(delta: float | None, unit: str) -> str:
    """How far the channel moved, with the direction left to the surrounding words."""
    if delta is None:
        return f"no usable {unit} change"
    return f"a change of {_number(abs(delta), 2)} {unit}"


def _join_clauses(clauses: list[str]) -> str:
    """A short English list: one item, or 'a, b and c'."""
    if len(clauses) <= 1:
        return "".join(clauses)
    return ", ".join(clauses[:-1]) + " and " + clauses[-1]


def _refs_at(ids: list[str], *positions: int) -> list[str]:
    """The evidence ids at the given positions, deduplicated, in the given order."""
    picked: list[str] = []
    for position in positions:
        if not -len(ids) <= position < len(ids):
            continue
        ref = ids[position]
        if ref not in picked:
            picked.append(ref)
    return picked


def _unique(*groups: list[str]) -> list[str]:
    """Every ref once, in first seen order."""
    picked: list[str] = []
    for group in groups:
        for ref in group:
            if ref not in picked:
                picked.append(ref)
    return picked


def _reasoning_claims(
    facts: dict,
    conditions: dict[str, bool],
    confidence: float,
    telemetry_ids: list[str],
    quality_ids: list[str],
    next_check: str | None,
) -> list[dict]:
    """The five claims: what the series shows, what it means, and the next check.

    Every number is interpolated from `facts`, and every ref is an evidence id
    the artifact already publishes, so a claim cannot quote or cite anything the
    artifact does not carry. Each claim carries the diagnosis confidence, which
    already includes the data-quality penalty; a hand-tuned per-claim weight
    would be a number the data does not support.
    """
    flow = facts["flow"]
    pressure = facts["pressure"]
    vibration = facts["vibration"]
    bearing = facts["bearing_temp"]
    current = facts["motor_current"]
    speed = facts["speed"]
    trend_refs = _refs_at(telemetry_ids, 0, -1)
    last_refs = _refs_at(telemetry_ids, -1)

    if conditions["flow_falls"] and conditions["speed_steady"]:
        steadiness = "which is a steady speed next to the flow loss"
    elif conditions["flow_falls"]:
        steadiness = "so speed did not hold next to the flow loss"
    else:
        steadiness = "so the series does not show the flow loss this check needs"
    observation = (
        f"Across {facts['samples']} samples over {_number(facts['window_hours'], 1)} hours the "
        f"{_movement('flow', flow['delta_pct'], 'percent')}, from {_number(flow['first'], 3)} "
        f"percent to {_number(flow['last'], 3)} percent, while the "
        f"{_movement('speed', speed['delta_pct'], 'percent')}, from {_number(speed['first'], 3)} "
        f"rpm to {_number(speed['last'], 3)} rpm, {steadiness}."
    )

    if conditions["flow_falls"] and conditions["pressure_steady"]:
        head = (
            "so the flow loss is not a collapse in head: a head collapse would show as "
            "pressure falling with the flow"
        )
    elif conditions["flow_falls"]:
        head = (
            "so the flow loss comes with a head change of its own, and a collapse in head "
            "is not excluded by this series"
        )
    else:
        head = (
            "so the series does not show a flow fall large enough to be called a loss next "
            "to a steady head, and this check cannot separate a head problem from a "
            "flow-side problem"
        )
    pressure_claim = (
        f"Pressure moved from {_number(pressure['first'], 3)} bar to "
        f"{_number(pressure['last'], 3)} bar, {_change_phrase(pressure['delta_pct'], 'percent')}, "
        f"{head}."
    )

    if conditions["current_rises"] and conditions["flow_drops"]:
        load = "so the pump is working harder for less delivered flow"
    elif conditions["current_rises"]:
        load = "so the motor load rose without the flow falling"
    elif conditions["flow_drops"]:
        load = "so the data does not show the load rise that would explain where the lost flow goes"
    else:
        load = "so the data does not show the flow fall and load rise this check pairs"
    current_claim = (
        f"The {_movement('motor current', current['delta_pct'], 'percent')}, from "
        f"{_number(current['first'], 3)} A to {_number(current['last'], 3)} A, while the "
        f"{_movement('flow', flow['delta_pct'], 'percent')} over the same window, {load}."
    )

    temperature_up = bearing["delta_pct"] is not None and bearing["delta_pct"] > 0
    vibration_up = vibration["delta_pct"] is not None and vibration["delta_pct"] > 0
    if temperature_up and not vibration_up:
        rotating = (
            "which argues against a bearing or rotating-assembly fault: that pairing would "
            "raise vibration together with the temperature"
        )
    elif temperature_up and vibration_up:
        rotating = (
            "which is the pairing a bearing or rotating-assembly fault would produce, so this "
            "series does not rule it out"
        )
    else:
        rotating = (
            "so the two channels do not point the same way, and the data does not separate a "
            "bearing fault from the load change"
        )
    rotating_claim = (
        f"The {_movement('bearing temperature', bearing['delta_pct'], 'percent')}, from "
        f"{_number(bearing['first'], 3)} C to {_number(bearing['last'], 3)} C, and the "
        f"{_movement('vibration', vibration['delta_pct'], 'percent')}, from "
        f"{_number(vibration['first'], 3)} mm/s to {_number(vibration['last'], 3)} mm/s, "
        f"{rotating}."
    )

    safety = (
        "local confirmation (site procedures, lockout/tagout, permits and qualified personnel) "
        "before any maintenance work"
    )
    if next_check:
        action = (
            f"The pack's next safe check is to {next_check}, and the field-safety document "
            f"requires {safety}"
        )
    else:
        action = (
            "The pack lists no next safe check for this asset, and the field-safety document "
            f"requires {safety}"
        )
    if quality_ids:
        action_claim = (
            f"{action}. The flagged data-quality cases reduce the reported confidence, so this "
            "stays a next check rather than a work order."
        )
    else:
        action_claim = f"{action}, so this stays a next check rather than a work order."

    return [
        {
            "claim_id": "C-1",
            "kind": "observation",
            "text": observation,
            "refs": trend_refs,
            "confidence": confidence,
        },
        {
            "claim_id": "C-2",
            "kind": "inference",
            "text": pressure_claim,
            "refs": last_refs,
            "confidence": confidence,
        },
        {
            "claim_id": "C-3",
            "kind": "inference",
            "text": current_claim,
            "refs": trend_refs,
            "confidence": confidence,
        },
        {
            "claim_id": "C-4",
            "kind": "inference",
            "text": rotating_claim,
            "refs": last_refs,
            "confidence": confidence,
        },
        {
            "claim_id": "C-5",
            "kind": "action",
            "text": action_claim,
            "refs": _unique(_refs_at(telemetry_ids, -1), quality_ids),
            "confidence": confidence,
        },
    ]


def _reasoning_differential(
    facts: dict, conditions: dict[str, bool], telemetry_ids: list[str]
) -> list[dict]:
    """Three candidate causes, each verdict computed from the facts and thresholds.

    A verdict is only ever `supported` or `less likely` when its condition holds;
    otherwise it is `cannot separate` and the text says what the data does not
    show.
    """
    flow = facts["flow"]
    pressure = facts["pressure"]
    current = facts["motor_current"]
    speed = facts["speed"]
    trend_refs = _refs_at(telemetry_ids, 0, -1)
    last_refs = _refs_at(telemetry_ids, -1)

    flow_change = f"flow changed {_number(flow['delta_pct'], 2)} percent"
    pressure_change = f"pressure changed {_number(pressure['delta_pct'], 2)} percent"
    speed_change = f"speed changed {_number(speed['delta_pct'], 2)} percent"
    current_change = f"motor current changed {_number(current['delta_pct'], 2)} percent"

    if conditions["flow_falls"] and conditions["speed_steady"] and conditions["pressure_steady"]:
        fouling_verdict = "supported"
        fouling_because = (
            f"{flow_change.capitalize()} while {speed_change} and {pressure_change}: a flow "
            "loss at a steady speed and a steady head is the hydraulic restriction signature "
            "this check looks for."
        )
    else:
        fouling_verdict = "cannot separate"
        missing = []
        if not conditions["flow_falls"]:
            missing.append(
                f"a net flow fall of at least {_number(FOULING_FLOW_DROP_PCT, 2)} percent"
            )
        if not conditions["speed_steady"]:
            missing.append(f"a speed within {_number(FOULING_SPEED_STABLE_PCT, 2)} percent")
        if not conditions["pressure_steady"]:
            missing.append(f"a pressure within {_number(FOULING_PRESSURE_STABLE_PCT, 2)} percent")
        fouling_because = (
            f"{flow_change.capitalize()}, {speed_change} and {pressure_change}. The data does "
            f"not show {_join_clauses(missing)}, so fouling cannot be separated from the other "
            "candidates."
        )

    if conditions["pressure_steady"]:
        suction_verdict = "less likely"
        suction_because = (
            f"{pressure_change.capitalize()} while {flow_change}: a restricted suction line or "
            "a partly closed valve would drop the head with the flow, and the head stayed "
            f"inside {_number(FOULING_PRESSURE_STABLE_PCT, 2)} percent, so this is less likely "
            "than a restriction in the hydraulic path."
        )
    else:
        suction_verdict = "cannot separate"
        suction_because = (
            f"{pressure_change.capitalize()} while {flow_change}. The data does not show the "
            "steady head this verdict would rest on, so a suction restriction cannot be "
            "separated from a restriction downstream of the pump."
        )

    if conditions["current_rises"] and conditions["flow_drops"]:
        drift_verdict = "less likely"
        drift_because = (
            f"{current_change.capitalize()} while {flow_change}: a flow sensor that drifts "
            "would not load the motor, so a load rise of at least "
            f"{_number(SENSOR_DRIFT_CURRENT_RISE_PCT, 2)} percent argues against a sensor-only "
            "explanation."
        )
    else:
        drift_verdict = "cannot separate"
        missing = []
        if not conditions["flow_drops"]:
            missing.append("a flow fall for a sensor error to explain")
        if not conditions["current_rises"]:
            missing.append(
                f"a motor current rise of at least "
                f"{_number(SENSOR_DRIFT_CURRENT_RISE_PCT, 2)} percent"
            )
        drift_because = (
            f"{current_change.capitalize()} while {flow_change}. The data does not show "
            f"{_join_clauses(missing)}, so a flow-sensor error cannot be separated from a real "
            "flow loss."
        )

    return [
        {
            "hypothesis": "Hydraulic path fouling",
            "verdict": fouling_verdict,
            "because": fouling_because,
            "refs": trend_refs,
        },
        {
            "hypothesis": "Restricted suction line or a partly closed valve",
            "verdict": suction_verdict,
            "because": suction_because,
            "refs": last_refs,
        },
        {
            "hypothesis": "Flow sensor drift",
            "verdict": drift_verdict,
            "because": drift_because,
            "refs": last_refs,
        },
    ]


def _reasoning_guardrail(claims: list[dict], differential: list[dict]) -> dict:
    """The citation counts a reader checks first, computed from the lists above."""
    cited = sum(1 for claim in claims if claim["refs"])
    refs: list[str] = []
    for entry in claims + differential:
        for ref in entry["refs"]:
            if ref not in refs:
                refs.append(ref)
    return {
        "claims": len(claims),
        "cited": cited,
        "unsupported": len(claims) - cited,
        "refs_resolved": len(refs),
    }


def _build_reasoning(
    rows: list[dict],
    confidence: float,
    next_check: str | None,
    telemetry_items: list[dict],
    quality_items: list[dict],
) -> dict:
    """The reasoning block: computed facts, cited claims, a differential, a count."""
    facts = _build_reasoning_facts(rows)
    conditions = _reasoning_conditions(facts)
    telemetry_ids = [item["evidence_id"] for item in telemetry_items]
    quality_ids = [item["evidence_id"] for item in quality_items]
    claims = _reasoning_claims(
        facts, conditions, confidence, telemetry_ids, quality_ids, next_check
    )
    differential = _reasoning_differential(facts, conditions, telemetry_ids)
    return {
        "generated_by": REASONING_GENERATED_BY,
        "facts": facts,
        "claims": claims,
        "differential": differential,
        "guardrail": _reasoning_guardrail(claims, differential),
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
    reasoning = _build_reasoning(
        [row for _, row in telemetry],
        confidence,
        asset.get("recommended_next_check"),
        telemetry_items,
        quality_items,
    )

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
        "reasoning": reasoning,
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
    reasoning = payload["reasoning"]
    guardrail = reasoning["guardrail"]
    print(f"reasoning          {guardrail['claims']} claims, {guardrail['cited']} cited, "
          f"{guardrail['unsupported']} unsupported, {guardrail['refs_resolved']} refs resolved "
          f"({reasoning['generated_by']})")
    print(f"wrote               {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
