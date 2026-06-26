#!/usr/bin/env python3
import argparse
import csv
import json
from pathlib import Path
from shutil import copy2

import cv2


def load_prediction(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def collect_confidences(pred):
    return [
        det["confidence"]
        for frame in pred.get("frames", [])
        for det in frame.get("detections", [])
    ]


def row_for_prediction(label: str, pred):
    summary = pred.get("summary", {})

    return {
        "domain": label,
        "dataset_name": pred.get("dataset_name", ""),
        "dataset_path": pred.get("dataset_path", ""),
        "model": pred.get("model", ""),
        "frames": summary.get("frames", 0),
        "total_detections": summary.get("total_detections", 0),
        "detections_per_frame": summary.get("detections_per_frame", 0.0),
        "average_confidence": summary.get("average_confidence", 0.0),
        "average_latency_ms": summary.get("average_latency_ms", 0.0),
        "low_confidence_fraction": summary.get("low_confidence_fraction", 0.0),
        "small_detection_fraction": summary.get("small_detection_fraction", 0.0),
        "class_counts": json.dumps(summary.get("class_counts", {}), sort_keys=True),
    }


def write_summary_csv(rows, output_dir: Path):
    path = output_dir / "summary.csv"

    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    return path


def write_summary_json(rows, output_dir: Path):
    path = output_dir / "summary.json"
    path.write_text(json.dumps({"rows": rows}, indent=2) + "\n", encoding="utf-8")
    return path


def write_confidence_plot(pred_a, pred_b, label_a: str, label_b: str, output_dir: Path):
    try:
        import matplotlib.pyplot as plt
    except ModuleNotFoundError:
        print("matplotlib is not installed; skipping confidence_distribution.png")
        return None

    conf_a = collect_confidences(pred_a)
    conf_b = collect_confidences(pred_b)

    path = output_dir / "confidence_distribution.png"

    plt.figure()
    plt.hist(conf_a, bins=20, alpha=0.6, label=label_a)
    plt.hist(conf_b, bins=20, alpha=0.6, label=label_b)
    plt.xlabel("Detection confidence")
    plt.ylabel("Count")
    plt.title("Confidence distribution by source")
    plt.legend()
    plt.tight_layout()
    plt.savefig(path)
    plt.close()

    return path


def draw_label(image, text: str, x: int, y: int) -> None:
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = 0.55
    thickness = 1

    (tw, th), baseline = cv2.getTextSize(text, font, scale, thickness)
    x = max(0, int(x))
    y = max(th + 4, int(y))

    cv2.rectangle(
        image,
        (x, y - th - baseline - 4),
        (x + tw + 6, y + baseline),
        (40, 40, 40),
        thickness=-1,
    )
    cv2.putText(
        image,
        text,
        (x + 3, y - 3),
        font,
        scale,
        (255, 255, 255),
        thickness,
        cv2.LINE_AA,
    )


def annotate_frame(frame, *, title: str, output_path: Path):
    frame_path = Path(frame.get("frame_path", ""))

    if not frame_path.exists() or not frame_path.is_file():
        return False

    image = cv2.imread(str(frame_path))

    if image is None:
        return False

    draw_label(image, title, 8, 24)

    for det in frame.get("detections", []):
        x1, y1, x2, y2 = [int(round(v)) for v in det.get("bbox_xyxy", [0, 0, 0, 0])]
        cv2.rectangle(image, (x1, y1), (x2, y2), (80, 220, 80), 2)
        draw_label(
            image,
            f"{det.get('class_name', '')} {float(det.get('confidence', 0.0)):.2f}",
            x1,
            y1 - 6,
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(output_path), image)

    return True


def export_qualitative_examples(pred, *, label: str, output_dir: Path, max_examples: int):
    frames = sorted(
        pred.get("frames", []),
        key=lambda item: len(item.get("detections", [])),
        reverse=True,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    count = 0

    for frame in frames:
        if count >= max_examples:
            break

        if not frame.get("detections"):
            continue

        example_path = Path(frame.get("example_path", ""))

        if example_path.exists() and example_path.is_file():
            copy2(example_path, output_dir / f"{label}_example_{count + 1:03d}.png")
            count += 1
            continue

        ok = annotate_frame(
            frame,
            title=f"{label} detections={len(frame.get('detections', []))}",
            output_path=output_dir / f"{label}_example_{count + 1:03d}.png",
        )

        if ok:
            count += 1

    return count


def compare(args):
    output_dir = Path(args.output)
    output_dir.mkdir(parents=True, exist_ok=True)

    pred_a = load_prediction(Path(args.pred_a))
    pred_b = load_prediction(Path(args.pred_b))

    label_a = args.label_a
    label_b = args.label_b

    rows = [
        row_for_prediction(label_a, pred_a),
        row_for_prediction(label_b, pred_b),
    ]

    summary_csv = write_summary_csv(rows, output_dir)
    summary_json = write_summary_json(rows, output_dir)
    plot_path = write_confidence_plot(pred_a, pred_b, label_a, label_b, output_dir)

    examples_dir = output_dir / "qualitative_examples"

    count_a = export_qualitative_examples(
        pred_a,
        label=label_a,
        output_dir=examples_dir,
        max_examples=args.max_examples_per_domain,
    )
    count_b = export_qualitative_examples(
        pred_b,
        label=label_b,
        output_dir=examples_dir,
        max_examples=args.max_examples_per_domain,
    )

    print(f"wrote {summary_csv}")
    print(f"wrote {summary_json}")

    if plot_path:
        print(f"wrote {plot_path}")

    print(f"qualitative examples: {label_a}={count_a}, {label_b}={count_b}")

    print("\nComparison:")
    for row in rows:
        print(
            f"  {row['domain']}: "
            f"detections/frame={float(row['detections_per_frame']):.3f}, "
            f"avg_conf={float(row['average_confidence']):.3f}, "
            f"small_frac={float(row['small_detection_fraction']):.3f}"
        )


def parse_args():
    parser = argparse.ArgumentParser(
        description="Compare lightweight domain-shift behavior from two batch inference JSON files."
    )

    parser.add_argument("--pred-a", required=True)
    parser.add_argument("--pred-b", required=True)
    parser.add_argument("--label-a", default="domain_a")
    parser.add_argument("--label-b", default="domain_b")
    parser.add_argument("--output", default="reports/domain_shift")
    parser.add_argument("--max-examples-per-domain", type=int, default=5)

    return parser.parse_args()


def main():
    args = parse_args()
    compare(args)


if __name__ == "__main__":
    main()
