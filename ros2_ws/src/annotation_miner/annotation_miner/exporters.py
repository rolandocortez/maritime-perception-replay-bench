import csv
import json
from pathlib import Path
from typing import Dict, List, Any

import cv2


MANIFEST_FIELDS = [
    "saved_index",
    "image_file",
    "reasons",
    "detection_count",
    "low_confidence_count",
    "small_object_count",
    "near_waterline_count",
    "outside_water_roi_count",
    "image_stamp_sec",
    "image_stamp_nanosec",
    "detection_stamp_sec",
    "detection_stamp_nanosec",
]


class UncertaintyExporter:
    def __init__(self, output_dir: str):
        self.output_dir = Path(output_dir)
        self.images_dir = self.output_dir / "images"
        self.manifest_path = self.output_dir / "manifest.csv"
        self.predictions_path = self.output_dir / "predictions.json"

        self.images_dir.mkdir(parents=True, exist_ok=True)

        if not self.manifest_path.exists():
            with self.manifest_path.open("w", encoding="utf-8", newline="") as f:
                writer = csv.DictWriter(f, fieldnames=MANIFEST_FIELDS)
                writer.writeheader()

        if not self.predictions_path.exists():
            self.predictions_path.write_text("[]\n", encoding="utf-8")

    def _load_predictions(self) -> List[Dict[str, Any]]:
        try:
            return json.loads(self.predictions_path.read_text(encoding="utf-8"))
        except Exception:
            return []

    def _write_predictions(self, rows: List[Dict[str, Any]]):
        self.predictions_path.write_text(
            json.dumps(rows, indent=2, sort_keys=True),
            encoding="utf-8",
        )

    def save(
        self,
        *,
        saved_index: int,
        image,
        detections: List[Dict[str, Any]],
        reasons: List[str],
        metrics: Dict[str, Any],
        image_stamp,
        detection_stamp,
    ) -> Path:
        image_file = self.images_dir / f"frame_{saved_index:06d}.jpg"

        ok = cv2.imwrite(str(image_file), image)
        if not ok:
            raise RuntimeError(f"Failed to write image: {image_file}")

        manifest_row = {
            "saved_index": saved_index,
            "image_file": str(image_file),
            "reasons": "|".join(reasons),
            "detection_count": metrics.get("detection_count", 0),
            "low_confidence_count": metrics.get("low_confidence_count", 0),
            "small_object_count": metrics.get("small_object_count", 0),
            "near_waterline_count": metrics.get("near_waterline_count", 0),
            "outside_water_roi_count": metrics.get("outside_water_roi_count", 0),
            "image_stamp_sec": getattr(image_stamp, "sec", 0),
            "image_stamp_nanosec": getattr(image_stamp, "nanosec", 0),
            "detection_stamp_sec": getattr(detection_stamp, "sec", 0),
            "detection_stamp_nanosec": getattr(detection_stamp, "nanosec", 0),
        }

        with self.manifest_path.open("a", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=MANIFEST_FIELDS)
            writer.writerow(manifest_row)

        prediction_rows = self._load_predictions()
        prediction_rows.append(
            {
                "saved_index": saved_index,
                "image_file": str(image_file),
                "reasons": reasons,
                "metrics": metrics,
                "detections": detections,
                "image_stamp": {
                    "sec": getattr(image_stamp, "sec", 0),
                    "nanosec": getattr(image_stamp, "nanosec", 0),
                },
                "detection_stamp": {
                    "sec": getattr(detection_stamp, "sec", 0),
                    "nanosec": getattr(detection_stamp, "nanosec", 0),
                },
            }
        )
        self._write_predictions(prediction_rows)

        return image_file
