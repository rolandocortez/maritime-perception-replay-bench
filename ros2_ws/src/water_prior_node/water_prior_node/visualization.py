import cv2

from water_prior_node.filters import detection_center_in_roi
from water_prior_node.heuristic import WaterRoi


def draw_label(image, text: str, x: int, y: int, color: tuple[int, int, int]) -> None:
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = 0.55
    thickness = 1

    (text_w, text_h), baseline = cv2.getTextSize(text, font, scale, thickness)

    x = max(0, int(x))
    y = max(text_h + 4, int(y))

    cv2.rectangle(
        image,
        (x, y - text_h - baseline - 4),
        (x + text_w + 6, y + baseline),
        color,
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


def bbox_to_xyxy(detection) -> tuple[int, int, int, int]:
    bbox = detection.bbox
    center_x = float(bbox.center.position.x)
    center_y = float(bbox.center.position.y)
    width = float(bbox.size_x)
    height = float(bbox.size_y)

    x1 = int(round(center_x - width / 2.0))
    y1 = int(round(center_y - height / 2.0))
    x2 = int(round(center_x + width / 2.0))
    y2 = int(round(center_y + height / 2.0))

    return x1, y1, x2, y2


def best_label(detection) -> str:
    if not detection.results:
        return "det"

    best = max(detection.results, key=lambda result: float(result.hypothesis.score))
    return f"{best.hypothesis.class_id} {float(best.hypothesis.score):.2f}"


def draw_water_roi(image, roi: WaterRoi) -> None:
    color = (255, 180, 0)

    overlay = image.copy()
    cv2.rectangle(
        overlay,
        (roi.x_min, roi.y_min),
        (roi.x_max, roi.y_max),
        color,
        thickness=-1,
    )
    cv2.addWeighted(overlay, 0.12, image, 0.88, 0.0, image)

    cv2.rectangle(
        image,
        (roi.x_min, roi.y_min),
        (roi.x_max, roi.y_max),
        color,
        thickness=2,
    )

    draw_label(
        image,
        "heuristic water ROI",
        roi.x_min + 8,
        roi.y_min + 24,
        color,
    )


def draw_detection_with_roi_status(image, detection, roi: WaterRoi) -> None:
    in_roi = detection_center_in_roi(detection, roi)
    color = (80, 220, 80) if in_roi else (0, 80, 255)

    x1, y1, x2, y2 = bbox_to_xyxy(detection)
    cv2.rectangle(image, (x1, y1), (x2, y2), color, 2)

    status = "in_roi" if in_roi else "out_roi"
    draw_label(image, f"{best_label(detection)} {status}", x1, y1 - 6, color)


def draw_hud(image, lines: list[str]) -> None:
    color = (40, 40, 40)
    y = 24

    for line in lines:
        draw_label(image, line, 8, y, color)
        y += 26
