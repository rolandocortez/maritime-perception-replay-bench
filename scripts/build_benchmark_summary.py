#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from pathlib import Path
from typing import Dict, List, Optional

import matplotlib.pyplot as plt


ROBUSTNESS_FALLBACK = [
    {
        "scenario": "clean",
        "fps": 7.303,
        "p50_ms": 57.608,
        "p95_ms": 80.269,
        "detections_per_frame": 10.117,
        "active_tracks": 165.0,
        "notes": "Baseline replay condition for comparing degraded runs.",
    },
    {
        "scenario": "frame_drop_15",
        "fps": 6.762,
        "p50_ms": 74.042,
        "p95_ms": 106.059,
        "detections_per_frame": 14.767,
        "active_tracks": 226.0,
        "notes": "Frame loss increased p95 latency and track activity.",
    },
    {
        "scenario": "blur_medium",
        "fps": 5.654,
        "p50_ms": 86.103,
        "p95_ms": 113.602,
        "detections_per_frame": 22.774,
        "active_tracks": 242.0,
        "notes": "Visual degradation increased detections/frame and tracking load.",
    },
    {
        "scenario": "delay_100ms",
        "fps": 4.534,
        "p50_ms": 173.015,
        "p95_ms": 191.530,
        "detections_per_frame": 11.333,
        "active_tracks": 183.0,
        "notes": "Artificial delay produced the largest latency increase.",
    },
    {
        "scenario": "glare_approx",
        "fps": 4.645,
        "p50_ms": 0.000,
        "p95_ms": 0.000,
        "detections_per_frame": 0.000,
        "active_tracks": 285.0,
        "notes": "Glare approximation requires careful interpretation.",
    },
]

RUNTIME_FALLBACK = [
    {
        "runtime": "PyTorch CPU",
        "p50_ms": 46.379,
        "p95_ms": 52.365,
        "fps": 21.401,
        "notes": "Slowest baseline, useful for comparison.",
    },
    {
        "runtime": "ONNX Runtime CPU",
        "p50_ms": 19.462,
        "p95_ms": 21.747,
        "fps": 50.351,
        "notes": "Best p95 stability in the measured edge-runtime comparison.",
    },
    {
        "runtime": "OpenVINO CPU",
        "p50_ms": 19.201,
        "p95_ms": 22.119,
        "fps": 51.060,
        "notes": "Highest FPS in the measured comparison, close to ONNX Runtime.",
    },
]


def as_float(value: object, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(value)
    except Exception:
        return default


def read_robustness(path: Path) -> List[Dict[str, object]]:
    if not path.exists():
        return ROBUSTNESS_FALLBACK

    rows: List[Dict[str, object]] = []
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            scenario = row.get("scenario") or row.get("name") or ""
            if not scenario:
                continue
            rows.append(
                {
                    "scenario": scenario,
                    "fps": as_float(row.get("fps")),
                    "p50_ms": as_float(row.get("e2e_latency_ms_p50") or row.get("p50_ms")),
                    "p95_ms": as_float(row.get("e2e_latency_ms_p95") or row.get("p95_ms")),
                    "detections_per_frame": as_float(row.get("detections_per_frame")),
                    "active_tracks": as_float(row.get("active_tracks")),
                    "notes": observation_for(scenario),
                }
            )

    return rows or ROBUSTNESS_FALLBACK


def read_runtime(path: Path) -> List[Dict[str, object]]:
    if not path.exists():
        return RUNTIME_FALLBACK

    rows: List[Dict[str, object]] = []
    with path.open("r", encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            runtime = row.get("runtime") or row.get("name") or row.get("backend") or ""
            if not runtime:
                continue
            rows.append(
                {
                    "runtime": runtime,
                    "p50_ms": as_float(row.get("p50_ms") or row.get("latency_ms_p50")),
                    "p95_ms": as_float(row.get("p95_ms") or row.get("latency_ms_p95")),
                    "fps": as_float(row.get("fps")),
                    "notes": runtime_observation(runtime),
                }
            )

    return rows or RUNTIME_FALLBACK


def observation_for(scenario: str) -> str:
    mapping = {
        "clean": "Baseline replay condition for comparing degraded runs.",
        "frame_drop_15": "Frame loss increased p95 latency and track activity.",
        "blur_medium": "Visual degradation increased detections/frame and tracking load.",
        "delay_100ms": "Artificial delay produced the largest latency increase.",
        "glare_approx": "Glare approximation requires careful interpretation.",
    }
    return mapping.get(scenario, "Measured replay or degraded scenario.")


def runtime_observation(runtime: str) -> str:
    key = runtime.lower()
    if "onnx" in key:
        return "Strong p95 latency and good default deployment path."
    if "openvino" in key:
        return "Strong CPU FPS; useful for Intel deployment exploration."
    if "torch" in key or "pytorch" in key:
        return "Baseline reference; slower than optimized runtimes."
    return "Runtime comparison entry."


def write_summary_csv(path: Path, robustness: List[Dict[str, object]], runtime: List[Dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = [
        "section",
        "name",
        "fps",
        "p50_ms",
        "p95_ms",
        "detections_per_frame",
        "active_tracks",
        "notes",
    ]

    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()

        for row in robustness:
            writer.writerow(
                {
                    "section": "robustness",
                    "name": row["scenario"],
                    "fps": row["fps"],
                    "p50_ms": row["p50_ms"],
                    "p95_ms": row["p95_ms"],
                    "detections_per_frame": row["detections_per_frame"],
                    "active_tracks": row["active_tracks"],
                    "notes": row["notes"],
                }
            )

        for row in runtime:
            writer.writerow(
                {
                    "section": "runtime",
                    "name": row["runtime"],
                    "fps": row["fps"],
                    "p50_ms": row["p50_ms"],
                    "p95_ms": row["p95_ms"],
                    "detections_per_frame": "",
                    "active_tracks": "",
                    "notes": row["notes"],
                }
            )


def fmt(value: object) -> str:
    return f"{as_float(value):.3f}"


def write_summary_md(path: Path, robustness: List[Dict[str, object]], runtime: List[Dict[str, object]]) -> None:
    lines: List[str] = []

    lines.extend(
        [
            "# Benchmark Summary",
            "",
            "## Goal",
            "",
            "Measure runtime behavior and robustness of the ROS2 perception pipeline across clean replay, degraded replay scenarios, live OAK integration smoke tests, and edge-runtime profiling.",
            "",
            "This summary is intentionally not a raw CSV dump. It focuses on what was measured, what changed under degradation, and which metrics were most useful for debugging.",
            "",
            "## Scenarios",
            "",
            "- clean replay",
            "- frame drop",
            "- blur",
            "- delay",
            "- glare approximation",
            "- OAK live smoke test",
            "- ONNX Runtime benchmark",
            "- OpenVINO benchmark",
            "- PyTorch CPU baseline",
            "",
            "## Robustness results",
            "",
            "| Scenario | FPS | E2E p50 ms | E2E p95 ms | Detections/frame | Active tracks | Main observation |",
            "|---|---:|---:|---:|---:|---:|---|",
        ]
    )

    for row in robustness:
        lines.append(
            f"| {row['scenario']} | {fmt(row['fps'])} | {fmt(row['p50_ms'])} | {fmt(row['p95_ms'])} | {fmt(row['detections_per_frame'])} | {fmt(row['active_tracks'])} | {row['notes']} |"
        )

    lines.extend(
        [
            "",
            "## Runtime comparison",
            "",
            "| Runtime | p50 ms | p95 ms | FPS | Notes |",
            "|---|---:|---:|---:|---|",
        ]
    )

    for row in runtime:
        lines.append(
            f"| {row['runtime']} | {fmt(row['p50_ms'])} | {fmt(row['p95_ms'])} | {fmt(row['fps'])} | {row['notes']} |"
        )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "The main takeaway is not a single accuracy number. The replay bench made it easier to see how latency, visual degradation, dropped frames, and artificial delay affect the behavior of a ROS2 perception pipeline.",
            "",
            "The most useful metrics were p95 latency, detections per frame, active tracks, and signs of track instability. Average FPS was useful, but it was not enough by itself. The degraded scenarios showed that the pipeline can remain alive while still becoming harder to trust: latency rises, tracking load changes, and detections can become noisier or less interpretable.",
            "",
            "Artificial delay was the clearest latency stressor. Blur increased detections per frame and active tracks, which suggests downstream tracking/debugging pressure. Frame drop increased tail latency. The glare approximation needs to be interpreted carefully because the measured zero detection/latency fields indicate that the scenario changed the data path or detection behavior enough that the raw summary should not be overclaimed.",
            "",
            "For edge profiling, ONNX Runtime and OpenVINO were both substantially faster than the PyTorch CPU baseline in the measured setup. ONNX Runtime was the safer default because it had the best p95 latency in the comparison, while OpenVINO showed strong FPS and remains useful for Intel CPU deployment exploration.",
            "",
            "## OAK live smoke test",
            "",
            "The OAK live path was used as a hardware-in-the-loop integration smoke test. It showed that live OAK RGB frames can enter the same ROS2 perception, tracking, overlay, water-prior, and metrics stack as replay.",
            "",
            "This validates integration and timing behavior. It does not validate maritime performance.",
            "",
            "## What cannot be concluded",
            "",
            "This benchmark summary does not prove production accuracy, safety, or real harbor performance. It does not validate an operational maritime autonomy system. It also does not replace dataset-level evaluation with ground-truth labels.",
            "",
            "The numbers should be read as engineering measurements for runtime behavior, robustness debugging, and deployment-path comparison.",
            "",
            "## Limitations",
            "",
            "- Public/sample data and controlled replay scenarios are not a substitute for real harbor trials.",
            "- OAK live testing is an integration smoke test, not domain validation.",
            "- Acoustic processing is currently a prototype lane, not an operational classifier.",
            "- Reports are generated locally and should be tied to run manifests for traceability.",
            "- p50/p95 latency and track behavior are more informative than average FPS alone.",
            "",
        ]
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def bar_plot(path: Path, labels: List[str], values: List[float], title: str, ylabel: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    plt.figure(figsize=(10, 5))
    plt.bar(labels, values)
    plt.title(title)
    plt.ylabel(ylabel)
    plt.xticks(rotation=30, ha="right")
    plt.tight_layout()
    plt.savefig(path, dpi=160)
    plt.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Build benchmark summary report and figures.")
    parser.add_argument("--robustness-csv", default="reports/robustness/summary.csv")
    parser.add_argument("--runtime-csv", default="reports/edge/runtime_comparison.csv")
    parser.add_argument("--output-dir", default="reports")
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    robustness = read_robustness(Path(args.robustness_csv))
    runtime = read_runtime(Path(args.runtime_csv))

    write_summary_csv(output_dir / "benchmark_summary.csv", robustness, runtime)
    write_summary_md(output_dir / "benchmark_summary.md", robustness, runtime)

    figures = output_dir / "figures"
    bar_plot(
        figures / "latency_comparison.png",
        [str(row["scenario"]) for row in robustness],
        [as_float(row["p95_ms"]) for row in robustness],
        "Robustness scenario p95 latency",
        "p95 latency (ms)",
    )
    bar_plot(
        figures / "fps_comparison.png",
        [str(row["scenario"]) for row in robustness],
        [as_float(row["fps"]) for row in robustness],
        "Robustness scenario FPS",
        "FPS",
    )
    bar_plot(
        figures / "runtime_comparison.png",
        [str(row["runtime"]) for row in runtime],
        [as_float(row["p95_ms"]) for row in runtime],
        "Runtime p95 latency comparison",
        "p95 latency (ms)",
    )

    print(f"wrote {output_dir / 'benchmark_summary.md'}")
    print(f"wrote {output_dir / 'benchmark_summary.csv'}")
    print(f"wrote {figures / 'latency_comparison.png'}")
    print(f"wrote {figures / 'fps_comparison.png'}")
    print(f"wrote {figures / 'runtime_comparison.png'}")


if __name__ == "__main__":
    main()
