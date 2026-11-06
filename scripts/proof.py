"""Summarise the timed trials into proof/metrics.json.

trials.csv columns: trial_id, arm, asset, target_section, found_section, correct,
duration_s, wrong_asset_warning, notes. arm is "app" or "baseline". One row per
trial, written by the person holding the stopwatch, not by the app.

No trials yet: prints the schema and exits 0, so the target is harmless in CI.
"""

from __future__ import annotations

import csv
import json
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRIALS = ROOT / "proof" / "trials.csv"
OUT = ROOT / "proof" / "metrics.json"
COLUMNS = ["trial_id", "arm", "asset", "target_section", "found_section", "correct",
           "duration_s", "wrong_asset_warning", "notes"]


def summarise(rows: list[dict]) -> dict:
    out: dict = {"n": len(rows), "arms": {}}
    for arm in ("app", "baseline"):
        arm_rows = [r for r in rows if r["arm"] == arm]
        if not arm_rows:
            continue
        durations = sorted(float(r["duration_s"]) for r in arm_rows)
        correct = sum(1 for r in arm_rows if str(r["correct"]).lower() in ("1", "true", "yes"))
        wrong = sum(1 for r in arm_rows if str(r.get("wrong_asset_warning", "")).lower() in ("1", "true", "yes"))
        q1, q3 = statistics.quantiles(durations, n=4)[0], statistics.quantiles(durations, n=4)[2]
        out["arms"][arm] = {
            "n": len(arm_rows),
            "median_s": round(statistics.median(durations), 1),
            "iqr_s": [round(q1, 1), round(q3, 1)],
            "correct_pct": round(100 * correct / len(arm_rows), 1),
            "wrong_asset_warnings": wrong,
        }
    return out


def main() -> None:
    if not TRIALS.exists():
        print(f"no {TRIALS.relative_to(ROOT)} yet")
        print("columns:", ", ".join(COLUMNS))
        return
    with TRIALS.open(newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    metrics = summarise(rows)
    OUT.write_text(json.dumps(metrics, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
