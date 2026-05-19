#!/usr/bin/env python3

import argparse
import csv
import sys
from pathlib import Path


def fail(message: str, code: int = 1) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(code)


def extract_frames(
    video_path: Path,
    output_dir: Path,
    stride: int,
    max_frames: int | None,
    prefix: str,
    ext: str,
) -> int:
    try:
        import cv2
    except ImportError:
        fail("OpenCV is not installed. Run: pip install opencv-python")

    if stride < 1:
        fail("--stride must be >= 1")

    if not video_path.exists():
        fail(f"video not found: {video_path}")

    output_dir.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        fail(f"could not open video: {video_path}")

    fps = float(cap.get(cv2.CAP_PROP_FPS))
    saved = 0
    frame_idx = 0

    manifest_path = output_dir / "frames_manifest.csv"

    with manifest_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["frame_index", "timestamp_sec", "path"],
        )
        writer.writeheader()

        while True:
            ok, frame = cap.read()
            if not ok:
                break

            if frame_idx % stride == 0:
                timestamp_sec = frame_idx / fps if fps > 0 else None
                frame_name = f"{prefix}_{frame_idx:06d}.{ext}"
                frame_path = output_dir / frame_name

                success = cv2.imwrite(str(frame_path), frame)
                if not success:
                    cap.release()
                    fail(f"could not write frame: {frame_path}")

                writer.writerow(
                    {
                        "frame_index": frame_idx,
                        "timestamp_sec": timestamp_sec,
                        "path": str(frame_path),
                    }
                )

                saved += 1

                if max_frames is not None and saved >= max_frames:
                    break

            frame_idx += 1

    cap.release()
    return saved


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract frames from a video.")
    parser.add_argument("video", type=Path, help="Path to the video file.")
    parser.add_argument("--output-dir", type=Path, default=Path("data/interim/frames"))
    parser.add_argument("--stride", type=int, default=1)
    parser.add_argument("--max-frames", type=int, default=None)
    parser.add_argument("--prefix", default="frame")
    parser.add_argument("--ext", choices=["jpg", "png"], default="jpg")
    args = parser.parse_args()

    saved = extract_frames(
        video_path=args.video,
        output_dir=args.output_dir,
        stride=args.stride,
        max_frames=args.max_frames,
        prefix=args.prefix,
        ext=args.ext,
    )

    print(f"saved_frames: {saved}")
    print(f"output_dir: {args.output_dir}")
    print(f"manifest: {args.output_dir / 'frames_manifest.csv'}")


if __name__ == "__main__":
    main()
