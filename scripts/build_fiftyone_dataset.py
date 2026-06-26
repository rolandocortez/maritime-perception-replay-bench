#!/usr/bin/env python3
import argparse
import json
from pathlib import Path


def infer_tags(path: Path) -> list[str]:
    name = path.name.lower()
    tags = []

    if "small_objects" in name or "small_object" in name:
        tags.append("small_objects")
    if "horizon_clutter" in name or "horizon" in name:
        tags.append("horizon_clutter")
    if "glare_reflections" in name or "glare" in name or "reflection" in name:
        tags.append("glare_reflections")

    if not tags:
        tags.append("unspecified_failure_slice")

    return tags


def load_events(events_jsonl: Path) -> dict[str, dict]:
    if not events_jsonl.exists():
        return {}

    events = {}

    with events_jsonl.open("r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue

            item = json.loads(line)
            path = Path(item.get("path", ""))
            events[path.name] = item

    return events


def build_dataset(*, examples_dir: Path, dataset_name: str, events_jsonl: Path, launch: bool) -> None:
    try:
        import fiftyone as fo
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "FiftyOne is not installed. Install optional analysis dependencies with:\n"
            "  python -m pip install -r requirements-analysis.txt"
        ) from exc

    image_paths = sorted(
        [
            path
            for path in examples_dir.glob("*")
            if path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
        ]
    )

    if not image_paths:
        raise SystemExit(f"No images found in {examples_dir}")

    if fo.dataset_exists(dataset_name):
        fo.delete_dataset(dataset_name)

    dataset = fo.Dataset(dataset_name)
    dataset.persistent = True

    events = load_events(events_jsonl)
    samples = []

    for path in image_paths:
        sample = fo.Sample(filepath=str(path.resolve()))
        sample.tags = infer_tags(path)

        event = events.get(path.name)
        if event:
            detections = event.get("detections", [])
            scores = [float(det.get("score", 0.0)) for det in detections]
            area_ratios = [float(det.get("area_ratio", 0.0)) for det in detections]
            class_names = sorted(
                {
                    str(det.get("class_name", ""))
                    for det in detections
                    if str(det.get("class_name", "")).strip()
                }
            )

            sample["primary_slice"] = str(event.get("primary_slice", ""))
            sample["candidate_count"] = int(event.get("all_candidate_count", 0))
            sample["sync_delta_ms"] = float(event.get("sync_delta_ms", 0.0))
            sample["avg_confidence"] = sum(scores) / len(scores) if scores else 0.0
            sample["min_area_ratio"] = min(area_ratios) if area_ratios else 0.0
            sample["max_area_ratio"] = max(area_ratios) if area_ratios else 0.0
            sample["class_names"] = ",".join(class_names)

        samples.append(sample)

    dataset.add_samples(samples)

    print(f"Created FiftyOne dataset: {dataset.name}")
    print(f"Samples: {len(dataset)}")
    print("Tags:")
    for tag, count in dataset.count_sample_tags().items():
        print(f"  {tag}: {count}")

    if launch:
        session = fo.launch_app(dataset)
        print("FiftyOne app launched. Press Ctrl+C to stop.")
        session.wait()

def parse_args():
    parser = argparse.ArgumentParser(
        description="Build a FiftyOne dataset from H18 maritime failure slice screenshots."
    )

    parser.add_argument(
        "--examples-dir",
        default="reports/failure_slices/examples",
        help="Directory containing exported failure slice screenshots.",
    )
    parser.add_argument(
        "--events-jsonl",
        default="reports/failure_slices/failure_slices_events.jsonl",
        help="Optional metadata JSONL produced by export_failure_examples.py.",
    )
    parser.add_argument(
        "--dataset-name",
        default="maritime_failure_slices",
        help="FiftyOne dataset name.",
    )
    parser.add_argument(
        "--launch",
        action="store_true",
        help="Launch the FiftyOne browser app after creating the dataset.",
    )

    return parser.parse_args()


def main():
    args = parse_args()

    build_dataset(
        examples_dir=Path(args.examples_dir),
        dataset_name=args.dataset_name,
        events_jsonl=Path(args.events_jsonl),
        launch=bool(args.launch),
    )


if __name__ == "__main__":
    main()
