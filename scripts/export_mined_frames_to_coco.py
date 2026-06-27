#!/usr/bin/env python3
import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Tuple


def load_json(path: Path, default):
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def load_manifest(path: Path) -> List[Dict[str, str]]:
    if not path.exists():
        return []
    with path.open("r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def resolve_path(raw: str, input_dir: Path) -> Path:
    p = Path(raw)
    if p.exists():
        return p
    q = input_dir / raw
    if q.exists():
        return q
    q = input_dir / "images" / Path(raw).name
    return q


def image_size(path: Path) -> Tuple[int, int]:
    try:
        import cv2

        image = cv2.imread(str(path))
        if image is not None:
            height, width = image.shape[:2]
            return int(width), int(height)
    except Exception:
        pass
    return 0, 0


def bbox_to_coco(det: Dict[str, Any]) -> List[float]:
    bbox = det.get("bbox") or {}

    x = float(bbox.get("x_min", bbox.get("x", 0.0)))
    y = float(bbox.get("y_min", bbox.get("y", 0.0)))
    w = float(bbox.get("width", 0.0))
    h = float(bbox.get("height", 0.0))

    if w <= 0.0 and "x_max" in bbox:
        w = max(0.0, float(bbox.get("x_max", 0.0)) - x)
    if h <= 0.0 and "y_max" in bbox:
        h = max(0.0, float(bbox.get("y_max", 0.0)) - y)

    return [x, y, max(0.0, w), max(0.0, h)]


def category_for(det: Dict[str, Any]) -> str:
    class_name = str(det.get("class_name") or "").strip()
    class_id = str(det.get("class_id") or "").strip()

    if class_name:
        return class_name
    if class_id:
        return class_id
    return "object"


def build_coco(input_dir: Path) -> Dict[str, Any]:
    predictions_path = input_dir / "predictions.json"
    manifest_path = input_dir / "manifest.csv"

    prediction_rows = load_json(predictions_path, [])
    manifest_rows = load_manifest(manifest_path)

    images = []
    annotations = []
    categories = []
    category_name_to_id: Dict[str, int] = {}

    def get_category_id(name: str) -> int:
        if name not in category_name_to_id:
            category_name_to_id[name] = len(category_name_to_id) + 1
            categories.append({"id": category_name_to_id[name], "name": name})
        return category_name_to_id[name]

    image_id_by_file: Dict[str, int] = {}
    annotation_id = 1

    for row in prediction_rows:
        image_file_raw = str(row.get("image_file", ""))
        image_path = resolve_path(image_file_raw, input_dir)
        width, height = image_size(image_path)

        image_id = len(images) + 1
        image_id_by_file[image_file_raw] = image_id

        images.append(
            {
                "id": image_id,
                "file_name": image_path.name,
                "width": width,
                "height": height,
                "source_path": image_file_raw,
                "saved_index": row.get("saved_index"),
                "reasons": row.get("reasons", []),
                "image_stamp": row.get("image_stamp", {}),
                "detection_stamp": row.get("detection_stamp", {}),
            }
        )

        for det in row.get("detections", []):
            bbox = bbox_to_coco(det)
            area = bbox[2] * bbox[3]
            category_name = category_for(det)

            annotations.append(
                {
                    "id": annotation_id,
                    "image_id": image_id,
                    "category_id": get_category_id(category_name),
                    "bbox": bbox,
                    "area": area,
                    "iscrowd": 0,
                    "score": det.get("confidence"),
                    "attributes": {
                        "source": "model_prediction",
                        "confidence": det.get("confidence"),
                        "class_id": det.get("class_id"),
                        "class_name": det.get("class_name"),
                        "detection_index": det.get("index"),
                        "mining_reasons": row.get("reasons", []),
                        "mining_metrics": row.get("metrics", {}),
                        "source_image_file": image_file_raw,
                    },
                }
            )
            annotation_id += 1

    if not prediction_rows:
        for row in manifest_rows:
            image_file_raw = row.get("image_file", "")
            image_path = resolve_path(image_file_raw, input_dir)
            width, height = image_size(image_path)

            images.append(
                {
                    "id": len(images) + 1,
                    "file_name": image_path.name,
                    "width": width,
                    "height": height,
                    "source_path": image_file_raw,
                    "saved_index": row.get("saved_index"),
                    "reasons": row.get("reasons", ""),
                }
            )

    if not categories:
        categories.append({"id": 1, "name": "object"})

    return {
        "info": {
            "description": "Mined uncertain-frame export for annotation review",
            "version": "1.0",
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "source_input": str(input_dir),
        },
        "licenses": [],
        "images": images,
        "annotations": annotations,
        "categories": categories,
    }


def main():
    parser = argparse.ArgumentParser(description="Export mined uncertain frames to COCO JSON.")
    parser.add_argument("--input", required=True, help="Input mined-frame folder.")
    parser.add_argument("--output", required=True, help="Output COCO JSON path.")
    args = parser.parse_args()

    input_dir = Path(args.input)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    coco = build_coco(input_dir)
    output_path.write_text(json.dumps(coco, indent=2, sort_keys=True), encoding="utf-8")

    print(f"wrote {output_path}")
    print(f"images={len(coco['images'])} annotations={len(coco['annotations'])} categories={len(coco['categories'])}")


if __name__ == "__main__":
    main()
