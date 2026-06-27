#!/usr/bin/env python3
import argparse
import csv
import json
from pathlib import Path

import yaml


DEFAULT_SCENARIOS = [
    "clean",
    "frame_drop_15",
    "blur_medium",
    "delay_100ms",
    "glare_approx",
]


def metric(summary, name, field, default=0.0):
    return float(summary.get("metrics", {}).get(name, {}).get(field, default))


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_config(path):
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def row_for_scenario(name, scenario_cfg):
    output_dir = Path(scenario_cfg["output_dir"])
    summary_path = output_dir / "summary.json"

    if not summary_path.exists():
        return {
            "scenario": scenario_cfg.get("display_name", name),
            "fps_mean": "",
            "e2e_latency_p50_ms": "",
            "e2e_latency_p95_ms": "",
            "active_tracks_mean": "",
            "dropped_frames_latest": "",
            "qualitative_failure": scenario_cfg.get("qualitative_failure", "Missing benchmark output."),
            "status": f"missing {summary_path}",
        }

    summary = load_json(summary_path)

    return {
        "scenario": scenario_cfg.get("display_name", name),
        "fps_mean": round(metric(summary, "input_fps", "mean"), 3),
        "e2e_latency_p50_ms": round(metric(summary, "end_to_end_latency_ms_p50", "mean"), 3),
        "e2e_latency_p95_ms": round(metric(summary, "end_to_end_latency_ms_p95", "mean"), 3),
        "active_tracks_mean": round(metric(summary, "active_tracks", "mean"), 3),
        "dropped_frames_latest": round(metric(summary, "dropped_frames_estimate", "latest"), 3),
        "qualitative_failure": scenario_cfg.get("qualitative_failure", ""),
        "status": "ok",
    }


def write_summary_csv(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)

    fields = [
        "scenario",
        "fps_mean",
        "e2e_latency_p50_ms",
        "e2e_latency_p95_ms",
        "active_tracks_mean",
        "dropped_frames_latest",
        "qualitative_failure",
        "status",
    ]

    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def format_value(value):
    return "" if value == "" else str(value)


def write_markdown(path, *, rows, config):
    report = config["robustness_report"]
    q = report["interpretation_questions"]

    lines = [
        f"# {report['title']}",
        "",
        "## Scope",
        "",
    ]

    for item in report["scope"]:
        lines.append(f"- {item}")

    lines.extend([
        "",
        "## Summary table",
        "",
        "| Scenario | FPS mean | E2E latency p50 ms | E2E latency p95 ms | Active tracks mean | Dropped frames latest | Qualitative failure |",
        "|---|---:|---:|---:|---:|---:|---|",
    ])

    for row in rows:
        lines.append(
            "| {scenario} | {fps_mean} | {e2e_latency_p50_ms} | {e2e_latency_p95_ms} | "
            "{active_tracks_mean} | {dropped_frames_latest} | {qualitative_failure} |".format(
                scenario=row["scenario"],
                fps_mean=format_value(row["fps_mean"]),
                e2e_latency_p50_ms=format_value(row["e2e_latency_p50_ms"]),
                e2e_latency_p95_ms=format_value(row["e2e_latency_p95_ms"]),
                active_tracks_mean=format_value(row["active_tracks_mean"]),
                dropped_frames_latest=format_value(row["dropped_frames_latest"]),
                qualitative_failure=row["qualitative_failure"],
            )
        )

    lines.extend([
        "",
        "## Interpretation",
        "",
        f"**What breaks the detector first?** {q['detector_breaks_first']}",
        "",
        f"**What breaks the tracker first?** {q['tracker_breaks_first']}",
        "",
        f"**What happens to p95 latency?** {q['p95_latency']}",
        "",
        f"**When do unstable tracks appear?** {q['unstable_tracks']}",
        "",
        f"**What would I do in a real field test?** {q['real_field_test']}",
        "",
        f"**What additional data would I collect?** {q['additional_data']}",
        "",
        "## Limitations",
        "",
    ])

    for item in report["limitations"]:
        lines.append(f"- {item}")

    lines.extend([
        "",
        "## Screenshot checklist",
        "",
        "- clean: overlay, metrics, timing",
        "- frame_drop_15: overlay, fault status, timing",
        "- blur_medium: overlay before/after degradation",
        "- delay_100ms: timing diagnostics with elevated p95",
        "- glare_approx: overlay with glare approximation",
        "",
        "Generated metrics and screenshots are local artifacts and should not be committed.",
        "",
    ])

    path.write_text("\n".join(lines), encoding="utf-8")


def ensure_screenshot_dirs(config):
    for payload in config["robustness_report"]["scenarios"].values():
        (Path(payload["output_dir"]) / "screenshots").mkdir(parents=True, exist_ok=True)


def main():
    parser = argparse.ArgumentParser(description="Build clean-vs-degraded robustness report from benchmark summaries.")
    parser.add_argument("--config", default="configs/robustness_report.yaml")
    parser.add_argument("--output-dir", default="reports/robustness")
    args = parser.parse_args()

    config = load_config(args.config)
    scenarios = config["robustness_report"]["scenarios"]

    ensure_screenshot_dirs(config)

    rows = [row_for_scenario(name, scenarios[name]) for name in DEFAULT_SCENARIOS]

    output_dir = Path(args.output_dir)
    write_summary_csv(output_dir / "summary.csv", rows)
    write_markdown(output_dir / "clean_vs_degraded.md", rows=rows, config=config)

    print(f"wrote {output_dir / 'summary.csv'}")
    print(f"wrote {output_dir / 'clean_vs_degraded.md'}")


if __name__ == "__main__":
    main()
