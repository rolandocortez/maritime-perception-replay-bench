from dataclasses import dataclass, field
from typing import Dict, List, Any


@dataclass
class SelectionResult:
    selected: bool
    reasons: List[str] = field(default_factory=list)
    metrics: Dict[str, Any] = field(default_factory=dict)


def area_ratio(det: Dict[str, Any], image_width: int, image_height: int) -> float:
    bbox = det.get("bbox") or {}

    width = max(0.0, float(bbox.get("width", 0.0)))
    height = max(0.0, float(bbox.get("height", 0.0)))

    image_area = max(1.0, float(image_width * image_height))
    return (width * height) / image_area


def bbox_center_y_ratio(det: Dict[str, Any], image_height: int) -> float:
    bbox = det.get("bbox") or {}

    y_min = float(bbox.get("y_min", 0.0))
    height = float(bbox.get("height", 0.0))
    center_y = y_min + height / 2.0

    return center_y / max(1.0, float(image_height))


def evaluate_frame(
    detections: List[Dict[str, Any]],
    *,
    image_width: int,
    image_height: int,
    min_confidence: float,
    max_confidence: float,
    small_object_area_ratio: float,
    many_detections_count: int,
    waterline_y_ratio: float,
    waterline_margin_ratio: float,
    enable_waterline_rules: bool,
) -> SelectionResult:
    reasons = []

    low_confidence_count = 0
    small_object_count = 0
    near_waterline_count = 0
    outside_water_roi_count = 0

    for det in detections:
        confidence = det.get("confidence")

        if confidence is not None:
            confidence = float(confidence)
            if min_confidence <= confidence <= max_confidence:
                low_confidence_count += 1

        ratio = area_ratio(det, image_width, image_height)
        if ratio > 0.0 and ratio <= small_object_area_ratio:
            small_object_count += 1

        if enable_waterline_rules:
            cy_ratio = bbox_center_y_ratio(det, image_height)

            if abs(cy_ratio - waterline_y_ratio) <= waterline_margin_ratio:
                near_waterline_count += 1

            if cy_ratio < waterline_y_ratio:
                outside_water_roi_count += 1

    if low_confidence_count > 0:
        reasons.append("confidence_near_threshold")

    if small_object_count > 0:
        reasons.append("small_object")

    if len(detections) >= many_detections_count:
        reasons.append("many_detections")

    if near_waterline_count > 0:
        reasons.append("near_waterline")

    if outside_water_roi_count > 0:
        reasons.append("outside_water_roi")

    metrics = {
        "detection_count": len(detections),
        "low_confidence_count": low_confidence_count,
        "small_object_count": small_object_count,
        "near_waterline_count": near_waterline_count,
        "outside_water_roi_count": outside_water_roi_count,
        "many_detections_count": many_detections_count,
    }

    return SelectionResult(
        selected=bool(reasons),
        reasons=reasons,
        metrics=metrics,
    )
