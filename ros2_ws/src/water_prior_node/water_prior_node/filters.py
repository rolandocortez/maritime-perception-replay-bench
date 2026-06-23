from copy import deepcopy

from vision_msgs.msg import Detection2DArray

from water_prior_node.heuristic import WaterRoi


def detection_center_in_roi(detection, roi: WaterRoi) -> bool:
    center_x = float(detection.bbox.center.position.x)
    center_y = float(detection.bbox.center.position.y)

    return (
        roi.x_min <= center_x <= roi.x_max
        and roi.y_min <= center_y <= roi.y_max
    )


def penalize_detection_confidence(detection, soft_penalty: float) -> None:
    penalty = min(max(float(soft_penalty), 0.0), 1.0)
    multiplier = 1.0 - penalty

    for result in detection.results:
        result.hypothesis.score = float(result.hypothesis.score) * multiplier


def annotate_detection_id(detection, suffix: str) -> None:
    current_id = str(detection.id) if detection.id else "det"
    if suffix not in current_id:
        detection.id = f"{current_id}:{suffix}"


def apply_water_roi_filter(
    *,
    detections_msg: Detection2DArray,
    roi: WaterRoi,
    filter_policy: str,
    soft_penalty: float,
) -> tuple[Detection2DArray, dict[str, int]]:
    policy = str(filter_policy).lower().strip()
    if policy not in {"soft", "hard", "off"}:
        raise ValueError(f"Unsupported filter_policy={filter_policy}")

    output = Detection2DArray()
    output.header = detections_msg.header

    kept = 0
    penalized = 0
    dropped = 0
    outside_roi = 0

    for detection in detections_msg.detections:
        in_roi = detection_center_in_roi(detection, roi)

        if in_roi or policy == "off":
            output.detections.append(deepcopy(detection))
            kept += 1
            continue

        outside_roi += 1

        if policy == "hard":
            dropped += 1
            continue

        filtered_detection = deepcopy(detection)
        penalize_detection_confidence(filtered_detection, soft_penalty)
        annotate_detection_id(filtered_detection, "out_of_water_roi")
        output.detections.append(filtered_detection)
        kept += 1
        penalized += 1

    stats = {
        "input": len(detections_msg.detections),
        "kept": kept,
        "outside_roi": outside_roi,
        "penalized": penalized,
        "dropped": dropped,
    }

    return output, stats
