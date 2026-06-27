#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from typing import Dict, List

import matplotlib.pyplot as plt


FAILURE_CATEGORIES = [
    {
        "key": "small_objects",
        "title": "Small objects",
        "symptom": "Small or distant contacts are missed, detected intermittently, or tracked for only a short time.",
        "likely_cause": "Small maritime objects occupy few pixels and can be confused with wakes, foam, horizon clutter, or compression artifacts.",
        "how_detected": "Uncertain-frame mining flags low-confidence and small-area detections; unstable-track mining flags short-lived tracks.",
        "possible_mitigation": "Add curated labels for small vessels, buoys, debris, and ambiguous waterline objects; evaluate small-object recall separately.",
        "limitation": "Candidates still need human-reviewed labels before they can be treated as true positives or false positives.",
    },
    {
        "key": "glare_reflections",
        "title": "Glare, reflections, and wakes",
        "symptom": "Bright glare regions, wakes, or reflections can trigger false positives, suppress real detections, or destabilize confidence.",
        "likely_cause": "Water reflections create high-contrast shapes that can resemble object boundaries, while glare reduces texture on real objects.",
        "how_detected": "Glare approximation scenarios, uncertainty mining, and water-prior disagreement expose these cases.",
        "possible_mitigation": "Add hard negatives for glare/wakes, preserve ignore labels, and require temporal consistency before promoting detections to stable contacts.",
        "limitation": "The current glare scenario is an approximation, not a substitute for real sun angle, water state, and exposure metadata.",
    },
    {
        "key": "horizon_clutter",
        "title": "Horizon and waterline clutter",
        "symptom": "Distant contacts near the horizon or waterline become ambiguous and can be confused with shoreline structures or wave clutter.",
        "likely_cause": "The horizon compresses many visual classes into a narrow band, and camera pitch changes the expected water region.",
        "how_detected": "Water-prior checks, overlay inspection, and uncertain-frame export preserve detector/context disagreements.",
        "possible_mitigation": "Improve waterline/ROI estimation, preserve camera attitude metadata, and label ambiguous horizon objects as unknown or ignore.",
        "limitation": "The current water-prior logic is a debugging aid, not a calibrated scene-understanding model.",
    },
    {
        "key": "tracking_fragmentation",
        "title": "Tracking fragmentation",
        "symptom": "A single physical object may become multiple track IDs, or tracks may disappear and reappear across frames.",
        "likely_cause": "Detection confidence drops, frame drops, blur, occlusion, or association thresholds can break track continuity.",
        "how_detected": "Unstable-track mining flags missed frames, short-lived tracks, and possible ID-switch events.",
        "possible_mitigation": "Tune lifecycle thresholds, keep tentative tracks alive longer under degraded conditions, and use velocity/appearance consistency.",
        "limitation": "Without ground-truth track IDs, this remains diagnostic rather than a formal MOT evaluation.",
    },
    {
        "key": "latency_stale_outputs",
        "title": "Latency and stale outputs",
        "symptom": "The system continues running, but outputs become delayed or less useful for real-time debugging.",
        "likely_cause": "Artificial delay, CPU load, queue buildup, model runtime cost, and visualization overhead can increase tail latency.",
        "how_detected": "Runtime metrics, p50/p95 latency, queue diagnostics, timestamp skew, and delay scenarios expose stale-output behavior.",
        "possible_mitigation": "Use p95 latency as a first-class metric, bound queues, profile detector runtime separately, and reduce visualization load during benchmarks.",
        "limitation": "The current numbers are local-machine measurements; field hardware and sustained thermal behavior still need validation.",
    },
    {
        "key": "annotation_noise",
        "title": "Annotation noise risk",
        "symptom": "Mined samples can include ambiguous objects, reflections, overlays, or low-quality frames that should not become confident labels.",
        "likely_cause": "Mining selects hard cases, not automatically correct labels. Model predictions are suggestions, not ground truth.",
        "how_detected": "Mined outputs preserve confidence, reason, timestamp, source path, and track metadata for review.",
        "possible_mitigation": "Use a labeling policy, keep raw frames separate from overlays, and reject samples where localization or class is unclear.",
        "limitation": "The annotation loop exports review candidates; it does not replace human label QA or dataset versioning.",
    },
]


def write_visual(path: Path, title: str, lines: List[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    plt.figure(figsize=(9, 5))
    plt.axis("off")
    text = title + "\n\n" + "\n".join(f"• {line}" for line in lines)
    plt.text(0.04, 0.96, text, va="top", ha="left", wrap=True, fontsize=11)
    plt.tight_layout()
    plt.savefig(path, dpi=160)
    plt.close()


def copy_example_images(category_dir: Path, candidate_roots: List[Path], max_images: int = 3) -> int:
    category_dir.mkdir(parents=True, exist_ok=True)
    copied = 0

    for root in candidate_roots:
        if not root.exists():
            continue
        for image in sorted(root.rglob("*.jpg")) + sorted(root.rglob("*.png")):
            if copied >= max_images:
                return copied
            dst = category_dir / f"example_{copied + 1:02d}{image.suffix.lower()}"
            shutil.copy2(image, dst)
            copied += 1

    return copied


def write_report(path: Path, visual_rel_paths: Dict[str, List[str]]) -> None:
    lines: List[str] = [
        "# Failure Analysis",
        "",
        "## Why failure analysis matters",
        "",
        "Aggregate metrics can show that a pipeline is slower or less stable, but they do not explain why. Field robotics problems often appear as interactions between perception, tracking, timing, sensor state, environment, and data quality.",
        "",
        "This analysis separates failure categories by symptom, likely cause, how the issue was detected, possible mitigation, and the limitation of the current analysis. The goal is not to blame the detector for everything; it is to understand where the system needs better data, better timing, better tracking logic, or better instrumentation.",
        "",
    ]

    for idx, item in enumerate(FAILURE_CATEGORIES, start=1):
        lines.extend(
            [
                f"## Failure category {idx}: {item['title']}",
                "",
                "### Symptom",
                "",
                item["symptom"],
                "",
                "### Likely cause",
                "",
                item["likely_cause"],
                "",
                "### How detected",
                "",
                item["how_detected"],
                "",
                "### Possible mitigation",
                "",
                item["possible_mitigation"],
                "",
                "### Limitation of current analysis",
                "",
                item["limitation"],
                "",
            ]
        )

        examples = visual_rel_paths.get(item["key"], [])
        if examples:
            lines.extend(["### Local visual examples", ""])
            for rel in examples:
                lines.append(f"- `{rel}`")
            lines.append("")

    lines.extend(
        [
            "## What I would collect in a real harbor test",
            "",
            "- Synchronized raw video.",
            "- Camera metadata: exposure, gain, focus, resolution, FPS.",
            "- Weather and lighting conditions.",
            "- Approximate sun angle and glare notes.",
            "- Operator notes and event timestamps.",
            "- False alarm timestamps.",
            "- Hard negatives: wakes, reflections, birds, docks, shoreline clutter.",
            "- Sensor health logs.",
            "- ROS2 bag or MCAP files with image, detection, track, metrics, and diagnostics topics.",
            "- Run manifests linking code, config, model, runtime, machine, and artifacts.",
            "",
            "## What I would improve next",
            "",
            "- Add a curated small-object validation split.",
            "- Add human-reviewed hard negatives for glare, wakes, and horizon clutter.",
            "- Add track-level evaluation once track ground truth exists.",
            "- Add long-run live OAK stability tests.",
            "- Add better horizon/waterline context.",
            "- Add sustained runtime and thermal measurements.",
            "- Connect failure categories to dataset update decisions.",
            "- Preserve every benchmark and field run through manifests and artifact bundles.",
            "",
            "## Summary",
            "",
            "The most interesting failures were not just missed detections. Small objects, glare, waterline clutter, dropped frames, blur, delay, and annotation noise risk affected the system differently. The failure analysis helps separate perception errors, tracking instability, and systems/timing issues.",
            "",
        ]
    )

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build local failure analysis report and visual example folders.")
    parser.add_argument("--output-dir", default="reports")
    parser.add_argument(
        "--candidate-root",
        action="append",
        default=[
            "reports/annotation/export_examples",
            "reports/annotation/uncertain_frames",
            "reports/annotation/unstable_tracks",
        ],
        help="Candidate image roots to copy examples from. Can be repeated.",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    cases_dir = output_dir / "failure_cases"
    candidate_roots = [Path(p) for p in args.candidate_root]

    visual_rel_paths: Dict[str, List[str]] = {}

    for item in FAILURE_CATEGORIES:
        category_dir = cases_dir / item["key"]
        copied = copy_example_images(category_dir, candidate_roots, max_images=2)

        summary_png = category_dir / "failure_summary.png"
        write_visual(
            summary_png,
            item["title"],
            [
                f"Symptom: {item['symptom']}",
                f"Detected by: {item['how_detected']}",
                f"Mitigation: {item['possible_mitigation']}",
            ],
        )

        paths = [str(summary_png.relative_to(output_dir))]
        for image in sorted(category_dir.glob("example_*")):
            paths.append(str(image.relative_to(output_dir)))

        if copied == 0:
            note = category_dir / "README.txt"
            note.write_text(
                "No mined image examples were available locally when this report was generated. "
                "The summary PNG is an illustrative local placeholder. Regenerate after mining/exporting examples.\n",
                encoding="utf-8",
            )
            paths.append(str(note.relative_to(output_dir)))

        visual_rel_paths[item["key"]] = paths

    write_report(output_dir / "failure_analysis.md", visual_rel_paths)

    print(f"wrote {output_dir / 'failure_analysis.md'}")
    print(f"wrote {cases_dir}")


if __name__ == "__main__":
    main()
