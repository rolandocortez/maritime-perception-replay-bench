#!/usr/bin/env python3
"""Tiny OpenCV YOLO labeler for one-class boat annotation.

Controls:
  left mouse drag  draw box
  s                save labels and go next
  n                go next without changing current labels
  b                go back
  u                undo last box
  c                clear boxes
  q or ESC         quit

This is intentionally simpler than LabelImg and avoids PyQt crashes.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import cv2


class Labeler:
    def __init__(self, images_dir: Path, labels_dir: Path, class_id: int = 0, max_width: int = 1400):
        self.images_dir = images_dir
        self.labels_dir = labels_dir
        self.class_id = class_id
        self.max_width = max_width

        self.images = sorted([p for p in images_dir.glob("*") if p.suffix.lower() in {".jpg", ".jpeg", ".png"}])
        if not self.images:
            raise SystemExit(f"No images found in {images_dir}")

        self.labels_dir.mkdir(parents=True, exist_ok=True)
        self.index = 0
        self.boxes: list[tuple[int, int, int, int]] = []
        self.drawing = False
        self.start = None
        self.current = None
        self.image = None
        self.view = None
        self.scale = 1.0
        self.window = "simple_yolo_labeler"

    def label_path(self, image_path: Path) -> Path:
        return self.labels_dir / f"{image_path.stem}.txt"

    def load_boxes(self, image_path: Path) -> None:
        self.boxes = []
        img_h, img_w = self.image.shape[:2]
        p = self.label_path(image_path)
        if not p.exists():
            return

        for line in p.read_text(encoding="utf-8").splitlines():
            parts = line.strip().split()
            if len(parts) != 5:
                continue
            try:
                _, cx, cy, w, h = parts
                cx = float(cx) * img_w
                cy = float(cy) * img_h
                w = float(w) * img_w
                h = float(h) * img_h
            except ValueError:
                continue
            x1 = int(round(cx - w / 2))
            y1 = int(round(cy - h / 2))
            x2 = int(round(cx + w / 2))
            y2 = int(round(cy + h / 2))
            self.boxes.append(self.clip_box((x1, y1, x2, y2)))

    def save_boxes(self, image_path: Path) -> None:
        img_h, img_w = self.image.shape[:2]
        lines = []
        for box in self.boxes:
            x1, y1, x2, y2 = self.clip_box(box)
            if x2 - x1 < 2 or y2 - y1 < 2:
                continue
            cx = ((x1 + x2) / 2) / img_w
            cy = ((y1 + y2) / 2) / img_h
            w = (x2 - x1) / img_w
            h = (y2 - y1) / img_h
            lines.append(f"{self.class_id} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}")
        self.label_path(image_path).write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
        print(f"saved {self.label_path(image_path)} boxes={len(lines)}")

    def clip_box(self, box: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
        h, w = self.image.shape[:2]
        x1, y1, x2, y2 = box
        x1, x2 = sorted((max(0, min(w - 1, x1)), max(0, min(w - 1, x2))))
        y1, y2 = sorted((max(0, min(h - 1, y1)), max(0, min(h - 1, y2))))
        return x1, y1, x2, y2

    def view_to_image(self, x: int, y: int) -> tuple[int, int]:
        return int(round(x / self.scale)), int(round(y / self.scale))

    def mouse(self, event, x, y, flags, param) -> None:
        ix, iy = self.view_to_image(x, y)
        if event == cv2.EVENT_LBUTTONDOWN:
            self.drawing = True
            self.start = (ix, iy)
            self.current = (ix, iy)
        elif event == cv2.EVENT_MOUSEMOVE and self.drawing:
            self.current = (ix, iy)
        elif event == cv2.EVENT_LBUTTONUP and self.drawing:
            self.drawing = False
            if self.start is not None:
                x1, y1 = self.start
                x2, y2 = ix, iy
                box = self.clip_box((x1, y1, x2, y2))
                if box[2] - box[0] >= 2 and box[3] - box[1] >= 2:
                    self.boxes.append(box)
            self.start = None
            self.current = None

    def make_display(self) -> None:
        img = self.image.copy()

        for box in self.boxes:
            x1, y1, x2, y2 = self.clip_box(box)
            cv2.rectangle(img, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(img, "boat", (x1, max(18, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)

        if self.drawing and self.start is not None and self.current is not None:
            x1, y1 = self.start
            x2, y2 = self.current
            x1, y1, x2, y2 = self.clip_box((x1, y1, x2, y2))
            cv2.rectangle(img, (x1, y1), (x2, y2), (0, 200, 255), 2)

        h, w = img.shape[:2]
        self.scale = min(1.0, self.max_width / max(1, w))
        if self.scale < 1.0:
            img = cv2.resize(img, (int(w * self.scale), int(h * self.scale)))

        image_name = self.images[self.index].name
        status = f"{self.index + 1}/{len(self.images)} {image_name} boxes={len(self.boxes)} | s save+next, n next, b back, u undo, c clear, q quit"
        cv2.putText(img, status, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 3)
        cv2.putText(img, status, (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)

        self.view = img

    def load_current(self) -> None:
        p = self.images[self.index]
        self.image = cv2.imread(str(p))
        if self.image is None:
            raise RuntimeError(f"failed to read {p}")
        self.load_boxes(p)

    def run(self, start: int = 0) -> None:
        self.index = max(0, min(start, len(self.images) - 1))
        cv2.namedWindow(self.window, cv2.WINDOW_NORMAL)
        cv2.setMouseCallback(self.window, self.mouse)
        self.load_current()

        while True:
            self.make_display()
            cv2.imshow(self.window, self.view)
            key = cv2.waitKey(30) & 0xFF

            if key in (ord("q"), 27):
                break
            if key == ord("s"):
                self.save_boxes(self.images[self.index])
                if self.index < len(self.images) - 1:
                    self.index += 1
                    self.load_current()
            elif key == ord("n"):
                if self.index < len(self.images) - 1:
                    self.index += 1
                    self.load_current()
            elif key == ord("b"):
                if self.index > 0:
                    self.index -= 1
                    self.load_current()
            elif key == ord("u"):
                if self.boxes:
                    self.boxes.pop()
            elif key == ord("c"):
                self.boxes.clear()

        cv2.destroyAllWindows()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--images", required=True)
    parser.add_argument("--labels", required=True)
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--max-width", type=int, default=1400)
    args = parser.parse_args()

    Labeler(Path(args.images), Path(args.labels), max_width=args.max_width).run(start=args.start)


if __name__ == "__main__":
    main()
