#!/usr/bin/env python3
import argparse
import csv
import json
from pathlib import Path
from statistics import mean


def percentile(values, percentile_value):
    if not values:
        return 0.0

    ordered = sorted(values)
    p = max(0.0, min(100.0, float(percentile_value)))
    k = (len(ordered) - 1) * (p / 100.0)
    lower = int(k)
    upper = min(lower + 1, len(ordered) - 1)
    weight = k - lower

    return float(ordered[lower] * (1.0 - weight) + ordered[upper] * weight)


def summarize_csv(metrics_csv):
    metrics_csv = Path(metrics_csv)

    grouped = {}

    with metrics_csv.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)

        for row in reader:
            name = row["name"]
            value = float(row["value"])
            unit = row.get("unit", "")
            grouped.setdefault(name, {"unit": unit, "values": []})
            grouped[name]["values"].append(value)

    summary = {
        "source_csv": str(metrics_csv),
        "metric_count": len(grouped),
        "metrics": {},
    }

    for name, payload in sorted(grouped.items()):
        values = payload["values"]

        summary["metrics"][name] = {
            "unit": payload["unit"],
            "samples": len(values),
            "latest": float(values[-1]) if values else 0.0,
            "mean": float(mean(values)) if values else 0.0,
            "min": float(min(values)) if values else 0.0,
            "max": float(max(values)) if values else 0.0,
            "p50": percentile(values, 50.0),
            "p95": percentile(values, 95.0),
        }

    return summary


def main():
    parser = argparse.ArgumentParser(description="Summarize runtime metric CSV output.")
    parser.add_argument("--metrics-csv", required=True, help="Path to metrics.csv")
    parser.add_argument("--output", required=True, help="Path to summary.json")
    args = parser.parse_args()

    summary = summarize_csv(args.metrics_csv)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")

    print(f"wrote {output}")


if __name__ == "__main__":
    main()
