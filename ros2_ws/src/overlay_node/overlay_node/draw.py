import cv2


def draw_label(image, text: str, x: int, y: int, color: tuple[int, int, int]) -> None:
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = 0.55
    thickness = 1

    (text_w, text_h), baseline = cv2.getTextSize(text, font, scale, thickness)

    x = max(0, x)
    y = max(text_h + 4, y)

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


def bbox_to_xyxy(center_x: float, center_y: float, width: float, height: float) -> tuple[int, int, int, int]:
    x1 = int(round(center_x - width / 2.0))
    y1 = int(round(center_y - height / 2.0))
    x2 = int(round(center_x + width / 2.0))
    y2 = int(round(center_y + height / 2.0))
    return x1, y1, x2, y2


def draw_detection(image, detection, draw_confidence: bool = True) -> None:
    color = (0, 180, 255)

    bbox = detection.bbox
    x1, y1, x2, y2 = bbox_to_xyxy(
        bbox.center.position.x,
        bbox.center.position.y,
        bbox.size_x,
        bbox.size_y,
    )

    cv2.rectangle(image, (x1, y1), (x2, y2), color, 2)

    label = "det"
    if detection.results:
        best = max(detection.results, key=lambda result: float(result.hypothesis.score))
        label = str(best.hypothesis.class_id)
        if draw_confidence:
            label += f" {float(best.hypothesis.score):.2f}"

    draw_label(image, label, x1, y1 - 6, color)


def draw_track(image, track, draw_confidence: bool = True, draw_track_age: bool = True) -> None:
    color = (80, 220, 80)

    x1, y1, x2, y2 = bbox_to_xyxy(
        track.center_x,
        track.center_y,
        track.width,
        track.height,
    )

    cv2.rectangle(image, (x1, y1), (x2, y2), color, 2)

    label = f"id={track.track_id} {track.class_name}"
    if draw_confidence:
        label += f" {float(track.confidence):.2f}"
    if draw_track_age:
        label += f" age={track.age} miss={track.missed_frames}"

    draw_label(image, label, x1, y1 - 6, color)


def draw_hud(image, lines: list[str]) -> None:
    color = (40, 40, 40)
    y = 24

    for line in lines:
        draw_label(image, line, 8, y, color)
        y += 26
