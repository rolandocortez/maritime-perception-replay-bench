#!/usr/bin/env python3
"""Build a local YOLO dataset from extracted HearMyShip frames.

Input:
  data/training/hearmyship_frames/images/*.jpg

Output:
  data/training/hearmyship_yolo/
    images/train/*.jpg
    images/val/*.jpg
    labels/train/*.txt
    labels/val/*.txt
    classes.txt
    data.yaml

Labels are created empty so a lightweight labeler can fill them later.
Generated data stays ignored by Git.
"""

from __future__ import annotations

import argparse
import random
import shutil
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", default="data/training/hearmyship_frames/images")
    parser.add_argument("--output", default="data/training/hearmyship_yolo")
    parser.add_argument("--val-fraction", type=float, default=0.2)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    source = Path(args.source)
    output = Path(args.output)

    images = sorted([p for p in source.glob("*") if p.suffix.lower() in {".jpg", ".jpeg", ".png"}])
    if not images:
        raise SystemExit(f"No images found in {source}")

    if output.exists() and args.force:
        shutil.rmtree(output)

    for subset in ["train", "val"]:
        (output / "images" / subset).mkdir(parents=True, exist_ok=True)
        (output / "labels" / subset).mkdir(parents=True, exist_ok=True)

    rng = random.Random(args.seed)
    shuffled = images[:]
    rng.shuffle(shuffled)
    val_count = max(1, int(round(len(shuffled) * args.val_fraction)))
    val_set = set(shuffled[:val_count])

    counts = {"train": 0, "val": 0}
    for img in images:
        subset = "val" if img in val_set else "train"
        dst_img = output / "images" / subset / img.name
        dst_lbl = output / "labels" / subset / f"{img.stem}.txt"

        if not dst_img.exists():
            shutil.copy2(img, dst_img)
        if not dst_lbl.exists():
            dst_lbl.touch()

        counts[subset] += 1

    (output / "classes.txt").write_text("boat\n", encoding="utf-8")
    (output / "data.yaml").write_text(
        f"""path: {output.resolve()}
train: images/train
val: images/val
names:
  0: boat
""",
        encoding="utf-8",
    )

    print(f"wrote {output}")
    print("train images:", counts["train"])
    print("val images:", counts["val"])
    print("classes:", output / "classes.txt")
    print("data yaml:", output / "data.yaml")


if __name__ == "__main__":
    main()
