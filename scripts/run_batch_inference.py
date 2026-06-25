#!/usr/bin/env python3
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import time

import cv2


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}
VIDEO_SUFFIXES = {".mp4", ".avi", ".mov", ".mkv", ".webm"}


def iter_image_files(dataset: Path):
    if dataset.is_file() and dataset.suffix.lower() in IMAGE_SUFFIXES:
        yield dataset
        return

    if dataset.is_dir():
        for path in sorted(dataset.rglob("*")):
            if path.suffix.lower() in IMAGE_SUFFIXES:
                yield path


def iter_video_frames(video_path: Path, *, frame_stride: int, max_frames: int):
    cap = cv2.VideoCapture(str(video_path))

    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

    frame_index = 0
    emitted = 0

    while True:
        ok, frame = cap.read()
        if not ok:
            break

        if frame_index % max(1, frame_stride) == 0:
            yield frame_index, frame
            emitted += 1

            if max_frames > 0 and emitted >= max_frames:
                break

        frame_index += 1

    cap.release()


def run_model_on_image(model, image, *, args):
    start = time.perf_counter()

    results = model.predict(
        image,
        conf=args.confidence_threshold,
        iou=args.iou_threshold,
        imgsz=args.imgsz,
        device=args.device,
        verbose=False,
    )

    latency_ms = (time.perf_counter() - start) * 1000.0

    detections = []

    if not results:
        return detections, latency_ms

    result = results[0]
    names = result.names

    if result.boxes is None:
        return detections, latency_ms

    boxes = result.boxes

    for i in range(len(boxes)):
        xyxy = boxes.xyxy[i].detach().cpu().tolist()
        conf = float(boxes.conf[i].detach().cpu().item())
        cls_id = int(boxes.cls[i].detach().cpu().item())
        class_name = str(names.get(cls_id, cls_id))

        x1, y1, x2, y2 = [float(v) for v in xyxy]
        width = max(0.0, x2 - x1)
        height = max(0.0, y2 - y1)

        detections.append(
            {
                "class_id": cls_id,
                "class_name": class_name,
                "confidence": conf,
                "bbox_xyxy": [x1, y1, x2, y2],
                "bbox_center": [x1 + width / 2.0, y1 + height / 2.0],
                "bbox_size": [width, height],
            }
        )

    return detections, latency_ms


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


def save_example(*, image, detections, output_dir: Path, name: str, title: str):
    output_dir.mkdir(parents=True, exist_ok=True)

    out = image.copy()
    draw_label(out, title, 8, 24)

    for det in detections:
        x1, y1, x2, y2 = [int(round(v)) for v in det["bbox_xyxy"]]
        cv2.rectangle(out, (x1, y1), (x2, y2), (80, 220, 80), 2)
        draw_label(out, f"{det['class_name']} {det['confidence']:.2f}", x1, y1 - 6)

    cv2.imwrite(str(output_dir / name), out)


def summarize(frames):
    total_detections = sum(len(frame["detections"]) for frame in frames)
    confidences = [det["confidence"] for frame in frames for det in frame["detections"]]
    class_counts = Counter(det["class_name"] for frame in frames for det in frame["detections"])
    latencies = [frame["latency_ms"] for frame in frames]

    small_flags = []
    low_conf_flags = []

    for frame in frames:
        image_area = float(frame["width"] * frame["height"])

        for det in frame["detections"]:
            width, height = det["bbox_size"]
            area_ratio = (width * height) / image_area if image_area > 0 else 0.0
            small_flags.append(area_ratio < 0.01)
            low_conf_flags.append(det["confidence"] < 0.35)

    n_frames = len(frames)
    n_dets = max(1, total_detections)

    return {
        "frames": n_frames,
        "total_detections": total_detections,
        "detections_per_frame": total_detections / n_frames if n_frames else 0.0,
        "average_confidence": sum(confidences) / len(confidences) if confidences else 0.0,
        "class_counts": dict(class_counts),
        "average_latency_ms": sum(latencies) / len(latencies) if latencies else 0.0,
        "low_confidence_fraction": sum(low_conf_flags) / n_dets,
        "small_detection_fraction": sum(small_flags) / n_dets,
    }


def run_dataset(args):
    from ultralytics import YOLO

    dataset_path = Path(args.dataset)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    examples_dir = Path(args.examples_dir) if args.examples_dir else None

    model = YOLO(args.model)

    frames = []
    saved_examples = 0

    if dataset_path.is_file() and dataset_path.suffix.lower() in VIDEO_SUFFIXES:
        source_kind = "video"

        for frame_index, image in iter_video_frames(
            dataset_path,
            frame_stride=args.frame_stride,
            max_frames=args.max_frames,
        ):
            detections, latency_ms = run_model_on_image(model, image, args=args)
            height, width = image.shape[:2]

            example_path = ""

            if examples_dir and detections and saved_examples < args.max_examples:
                example_name = f"{args.dataset_name}_frame_{frame_index:06d}.png"
                save_example(
                    image=image,
                    detections=detections,
                    output_dir=examples_dir,
                    name=example_name,
                    title=f"{args.dataset_name} frame={frame_index}",
                )
                example_path = str(examples_dir / example_name)
                saved_examples += 1

            frames.append(
                {
                    "frame_index": frame_index,
                    "frame_path": str(dataset_path),
                    "source_kind": source_kind,
                    "width": width,
                    "height": height,
                    "latency_ms": latency_ms,
                    "detections": detections,
                    "example_path": example_path,
                }
            )

    else:
        source_kind = "image_directory"
        image_paths = list(iter_image_files(dataset_path))

        if args.max_frames > 0:
            image_paths = image_paths[: args.max_frames]

        if not image_paths:
            raise SystemExit(f"No images found in {dataset_path}")

        for frame_index, image_path in enumerate(image_paths):
            image = cv2.imread(str(image_path))

            if image is None:
                continue

            detections, latency_ms = run_model_on_image(model, image, args=args)
            height, width = image.shape[:2]

            example_path = ""

            if examples_dir and detections and saved_examples < args.max_examples:
                example_name = f"{args.dataset_name}_frame_{frame_index:06d}.png"
                save_example(
                    image=image,
                    detections=detections,
                    output_dir=examples_dir,
                    name=example_name,
                    title=f"{args.dataset_name} frame={frame_index}",
                )
                example_path = str(examples_dir / example_name)
                saved_examples += 1

            frames.append(
                {
                    "frame_index": frame_index,
                    "frame_path": str(image_path),
                    "source_kind": source_kind,
                    "width": width,
                    "height": height,
                    "latency_ms": latency_ms,
                    "detections": detections,
                    "example_path": example_path,
                }
            )

    payload = {
        "version": "0.1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "dataset_name": args.dataset_name,
        "dataset_path": str(dataset_path),
        "model": args.model,
        "device": args.device,
        "confidence_threshold": args.confidence_threshold,
        "iou_threshold": args.iou_threshold,
        "imgsz": args.imgsz,
        "frames": frames,
        "summary": summarize(frames),
    }

    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    print(f"wrote {output_path}")
    print(json.dumps(payload["summary"], indent=2))


def parse_args():
    parser = argparse.ArgumentParser(
        description="Run batch YOLO inference for lightweight maritime domain-shift comparison."
    )

    parser.add_argument("--dataset", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--dataset-name", default="dataset")
    parser.add_argument("--model", default="yolo11n.pt")
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--confidence-threshold", type=float, default=0.25)
    parser.add_argument("--iou-threshold", type=float, default=0.45)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--frame-stride", type=int, default=15)
    parser.add_argument("--max-frames", type=int, default=60)
    parser.add_argument("--examples-dir", default="")
    parser.add_argument("--max-examples", type=int, default=5)

    return parser.parse_args()


def main():
    args = parse_args()
    run_dataset(args)


if __name__ == "__main__":
    main()
