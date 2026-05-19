#!/usr/bin/env python3

import argparse
import json
import sys
from pathlib import Path


def fail(message: str, code: int = 1) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(code)


def decode_fourcc(value: float) -> str:
    try:
        value = int(value)
        chars = [chr((value >> 8 * i) & 0xFF) for i in range(4)]
        codec = "".join(chars).strip()
        return codec if codec else "unknown"
    except Exception:
        return "unknown"


def inspect_video(video_path: Path) -> dict:
    try:
        import cv2
    except ImportError:
        fail("OpenCV is not installed. Run: pip install opencv-python")

    if not video_path.exists():
        fail(f"video not found: {video_path}")

    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        fail(f"could not open video: {video_path}")

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    fps = float(cap.get(cv2.CAP_PROP_FPS))
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    fourcc = decode_fourcc(cap.get(cv2.CAP_PROP_FOURCC))

    duration_sec = None
    if fps > 0 and frame_count > 0:
        duration_sec = frame_count / fps

    cap.release()

    return {
        "path": str(video_path),
        "width": width,
        "height": height,
        "fps": fps,
        "frame_count": frame_count,
        "duration_sec": duration_sec,
        "codec": fourcc,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect a video file.")
    parser.add_argument("video", type=Path, help="Path to the video file.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    args = parser.parse_args()

    info = inspect_video(args.video)

    if args.json:
        print(json.dumps(info, indent=2))
        return

    print(f"path: {info['path']}")
    print(f"width: {info['width']}")
    print(f"height: {info['height']}")
    print(f"fps: {info['fps']}")
    print(f"frame_count: {info['frame_count']}")
    print(f"duration_sec: {info['duration_sec']}")
    print(f"codec: {info['codec']}")


if __name__ == "__main__":
    main()
