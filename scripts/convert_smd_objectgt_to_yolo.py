#!/usr/bin/env python3
"""Convert Singapore Maritime Dataset ObjectGT .mat annotations to YOLO format.

Run from repo root, after extracting the Kaggle SMD zip locally.
Generated images/labels stay under data/training/ and should not be committed.
"""
from __future__ import annotations

import argparse
import csv
import random
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from scipy.io import loadmat


@dataclass(frozen=True)
class Pair:
    stem: str
    video: Path
    mat: Path
    split: str


def as_array(x):
    if x is None:
        return np.empty((0,))
    return np.asarray(x)


def as_text(x) -> str:
    if isinstance(x, np.ndarray):
        if x.size == 0:
            return ""
        if x.dtype.kind in {"U", "S", "O"}:
            return " ".join(as_text(v) for v in x.flat).strip()
    return str(x).strip()


def field(obj, name: str):
    if hasattr(obj, name):
        return getattr(obj, name)
    if isinstance(obj, dict):
        return obj.get(name)
    return None


def normalize_boxes(bb) -> np.ndarray:
    arr = as_array(bb).astype(np.float32, copy=False) if bb is not None else np.empty((0, 4), np.float32)
    if arr.size == 0:
        return np.empty((0, 4), np.float32)
    if arr.ndim == 1 and arr.size == 4:
        arr = arr.reshape(1, 4)
    elif arr.ndim != 2:
        arr = arr.reshape(-1, 4)
    if arr.shape[1] != 4:
        return np.empty((0, 4), np.float32)
    return arr


def object_types(frame_obj) -> list[str]:
    raw = field(frame_obj, "ObjectType")
    if raw is None:
        return []
    arr = np.asarray(raw, dtype=object)
    return [as_text(v) for v in arr.flat]


def frame_boxes(frame_obj, object_filter: str | None) -> list[tuple[float, float, float, float]]:
    boxes = normalize_boxes(field(frame_obj, "BB"))
    labels = object_types(frame_obj)
    out = []
    for i, b in enumerate(boxes):
        if not np.isfinite(b).all():
            continue
        if object_filter:
            label = labels[i] if i < len(labels) else ""
            if object_filter.lower() not in label.lower():
                continue
        x, y, w, h = [float(v) for v in b]
        if w > 1 and h > 1:
            out.append((x, y, w, h))
    return out


def yolo_line(box, img_w: int, img_h: int) -> str | None:
    # SMD BB format observed: [x, y, width, height]
    x, y, w, h = box
    x1 = max(0.0, min(float(img_w - 1), x))
    y1 = max(0.0, min(float(img_h - 1), y))
    x2 = max(0.0, min(float(img_w - 1), x + w))
    y2 = max(0.0, min(float(img_h - 1), y + h))
    bw = x2 - x1
    bh = y2 - y1
    if bw <= 1 or bh <= 1:
        return None
    cx = (x1 + x2) / 2.0 / img_w
    cy = (y1 + y2) / 2.0 / img_h
    return f"0 {cx:.6f} {cy:.6f} {bw / img_w:.6f} {bh / img_h:.6f}"


def find_pairs(root: Path, include_tokens: list[str]) -> list[tuple[str, Path, Path]]:
    videos = sorted(root.rglob("*.avi"))
    video_by_stem = {v.stem: v for v in videos}
    pairs = []
    for mat in sorted(root.rglob("*ObjectGT.mat")):
        stem = mat.stem.replace("_ObjectGT", "")
        video = video_by_stem.get(stem)
        if not video:
            continue
        path_text = str(video).replace("\\", "/")
        if include_tokens and not any(t in path_text for t in include_tokens):
            continue
        pairs.append((stem, video, mat))
    return pairs


def split_pairs(raw_pairs, val_fraction: float, seed: int) -> list[Pair]:
    rng = random.Random(seed)
    shuffled = raw_pairs[:]
    rng.shuffle(shuffled)
    val_count = max(1, int(round(len(shuffled) * val_fraction))) if len(shuffled) > 1 else 0
    val_stems = {stem for stem, _, _ in shuffled[:val_count]}
    return [Pair(stem, video, mat, "val" if stem in val_stems else "train") for stem, video, mat in raw_pairs]


def draw_preview(image, lines: list[str]):
    out = image.copy()
    h, w = out.shape[:2]
    for line in lines:
        _, cx, cy, bw, bh = line.split()
        cx, cy, bw, bh = float(cx) * w, float(cy) * h, float(bw) * w, float(bh) * h
        x1, y1 = int(cx - bw / 2), int(cy - bh / 2)
        x2, y2 = int(cx + bw / 2), int(cy + bh / 2)
        cv2.rectangle(out, (x1, y1), (x2, y2), (0, 255, 0), 2)
        cv2.putText(out, "boat", (x1, max(20, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
    return out


def save_preview(items: list[np.ndarray], out_path: Path):
    if not items:
        return
    thumbs = []
    for img in items:
        h, w = img.shape[:2]
        tw = 420
        th = max(1, int(h * tw / max(1, w)))
        thumbs.append(cv2.resize(img, (tw, th)))
    cols = 3
    rows = int(np.ceil(len(thumbs) / cols))
    mh = max(t.shape[0] for t in thumbs)
    canvas = np.full((rows * mh, cols * 420, 3), 255, np.uint8)
    for i, t in enumerate(thumbs):
        r, c = divmod(i, cols)
        canvas[r * mh:r * mh + t.shape[0], c * 420:c * 420 + t.shape[1]] = t
    cv2.imwrite(str(out_path), canvas)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--smd-root", default="data/raw/smd/kaggle/extracted")
    ap.add_argument("--output", default="data/training/smd_yolo")
    ap.add_argument("--include", nargs="*", default=["VIS_Onshore", "VIS_Onboard"], help="Path tokens to include. Default: visible SMD only.")
    ap.add_argument("--object-filter", default="Vessel", help="Keep ObjectType containing this. Empty string disables filter.")
    ap.add_argument("--frame-stride", type=int, default=10)
    ap.add_argument("--max-videos", type=int, default=0)
    ap.add_argument("--max-frames-per-video", type=int, default=0)
    ap.add_argument("--val-fraction", type=float, default=0.2)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--jpeg-quality", type=int, default=92)
    ap.add_argument("--preview-count", type=int, default=12)
    ap.add_argument("--keep-empty", action="store_true")
    args = ap.parse_args()

    root = Path(args.smd_root)
    out = Path(args.output)
    for s in ("train", "val"):
        (out / "images" / s).mkdir(parents=True, exist_ok=True)
        (out / "labels" / s).mkdir(parents=True, exist_ok=True)

    raw_pairs = find_pairs(root, args.include)
    if args.max_videos:
        raw_pairs = raw_pairs[:args.max_videos]
    pairs = split_pairs(raw_pairs, args.val_fraction, args.seed)
    if not pairs:
        raise SystemExit("No matching SMD ObjectGT/video pairs found.")

    print("matched pairs:", len(pairs))
    for p in pairs[:12]:
        print(f"  {p.split:5s} {p.stem} -> {p.video.name}")

    summary = []
    previews = []
    total_images = 0
    total_boxes = 0
    object_filter = args.object_filter or None

    for pair in pairs:
        mat = loadmat(pair.mat, squeeze_me=True, struct_as_record=False)
        frames = np.atleast_1d(mat["structXML"])
        cap = cv2.VideoCapture(str(pair.video))
        if not cap.isOpened():
            print("WARNING: cannot open", pair.video)
            continue
        video_frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        limit = min(len(frames), video_frame_count if video_frame_count else len(frames))
        if args.max_frames_per_video:
            limit = min(limit, args.max_frames_per_video)

        image_count = 0
        box_count = 0
        for idx in range(0, limit, max(1, args.frame_stride)):
            boxes = frame_boxes(frames[idx], object_filter)
            if not boxes and not args.keep_empty:
                continue
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ok, image = cap.read()
            if not ok or image is None:
                continue
            h, w = image.shape[:2]
            lines = []
            for box in boxes:
                line = yolo_line(box, w, h)
                if line:
                    lines.append(line)
            if not lines and not args.keep_empty:
                continue
            stem = f"{pair.stem}_f{idx:06d}"
            cv2.imwrite(str(out / "images" / pair.split / f"{stem}.jpg"), image, [int(cv2.IMWRITE_JPEG_QUALITY), args.jpeg_quality])
            (out / "labels" / pair.split / f"{stem}.txt").write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
            image_count += 1
            box_count += len(lines)
            total_images += 1
            total_boxes += len(lines)
            if len(previews) < args.preview_count and lines:
                previews.append(draw_preview(image, lines))
        cap.release()
        summary.append({"split": pair.split, "stem": pair.stem, "video": str(pair.video), "mat": str(pair.mat), "frames_written": image_count, "boxes_written": box_count})

    (out / "classes.txt").write_text("boat\n", encoding="utf-8")
    (out / "data.yaml").write_text(f"path: {out.resolve()}\ntrain: images/train\nval: images/val\nnames:\n  0: boat\n", encoding="utf-8")
    with (out / "conversion_summary.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["split", "stem", "video", "mat", "frames_written", "boxes_written"])
        writer.writeheader()
        writer.writerows(summary)
    save_preview(previews, out / "preview_smd_yolo.jpg")

    print("\nwrote dataset:", out)
    print("images:", total_images)
    print("boxes:", total_boxes)
    print("train images:", len(list((out / "images/train").glob("*.jpg"))))
    print("val images:", len(list((out / "images/val").glob("*.jpg"))))
    print("preview:", out / "preview_smd_yolo.jpg")
    print("data yaml:", out / "data.yaml")


if __name__ == "__main__":
    main()
