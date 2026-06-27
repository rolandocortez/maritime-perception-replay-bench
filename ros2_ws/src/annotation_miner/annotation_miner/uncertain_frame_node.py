import importlib
from typing import Any, Dict, List, Optional

import cv2
import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data

from sensor_msgs.msg import Image

from annotation_miner.exporters import UncertaintyExporter
from annotation_miner.selection_rules import evaluate_frame


TRUE_VALUES = {"1", "true", "yes", "on"}


def to_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in TRUE_VALUES


def import_message_type(type_string: str):
    normalized = type_string.replace("/msg/", "/")
    parts = normalized.split("/")

    if len(parts) != 2:
        raise ValueError(
            "detections_type must look like 'vision_msgs/msg/Detection2DArray' "
            "or 'maritime_msgs/msg/DetectionArray'"
        )

    package_name, message_name = parts
    module = importlib.import_module(f"{package_name}.msg")
    return getattr(module, message_name)


def number_or_none(value):
    try:
        return float(value)
    except Exception:
        return None


def get_nested_attr(obj, path: str):
    value = obj

    for name in path.split("."):
        if value is None or not hasattr(value, name):
            return None
        value = getattr(value, name)

    return value


def first_number(obj, paths):
    for path in paths:
        value = get_nested_attr(obj, path)
        value = number_or_none(value)

        if value is not None:
            return value

    return None


def extract_confidence_and_class(det) -> Dict[str, Any]:
    confidence = first_number(det, ["confidence", "score", "probability"])
    class_id = None
    class_name = None

    for attr in ["class_id", "label_id", "id"]:
        if hasattr(det, attr):
            class_id = getattr(det, attr)
            break

    for attr in ["class_name", "label", "name"]:
        if hasattr(det, attr):
            class_name = getattr(det, attr)
            break

    results = getattr(det, "results", None)
    if results:
        best = None
        best_score = -1.0

        for result in results:
            score = first_number(result, ["score", "hypothesis.score"])

            if score is not None and score > best_score:
                best = result
                best_score = score

        if best is not None:
            confidence = best_score
            class_id = (
                get_nested_attr(best, "hypothesis.class_id")
                or get_nested_attr(best, "id")
                or class_id
            )
            class_name = str(class_id) if class_id is not None else class_name

    return {
        "confidence": confidence,
        "class_id": str(class_id) if class_id is not None else "",
        "class_name": str(class_name) if class_name is not None else "",
    }


def bbox_from_center(cx, cy, width, height):
    if None in [cx, cy, width, height]:
        return None

    width = float(width)
    height = float(height)
    x_min = float(cx) - width / 2.0
    y_min = float(cy) - height / 2.0

    return {
        "x_min": x_min,
        "y_min": y_min,
        "x_max": x_min + width,
        "y_max": y_min + height,
        "width": width,
        "height": height,
    }


def bbox_from_minmax(x_min, y_min, x_max, y_max):
    if None in [x_min, y_min, x_max, y_max]:
        return None

    x_min = float(x_min)
    y_min = float(y_min)
    x_max = float(x_max)
    y_max = float(y_max)

    return {
        "x_min": x_min,
        "y_min": y_min,
        "x_max": x_max,
        "y_max": y_max,
        "width": max(0.0, x_max - x_min),
        "height": max(0.0, y_max - y_min),
    }


def bbox_from_xywh(x, y, width, height):
    if None in [x, y, width, height]:
        return None

    x = float(x)
    y = float(y)
    width = float(width)
    height = float(height)

    return {
        "x_min": x,
        "y_min": y,
        "x_max": x + width,
        "y_max": y + height,
        "width": max(0.0, width),
        "height": max(0.0, height),
    }


def extract_bbox(det):
    bbox_obj = (
        getattr(det, "bbox", None)
        or getattr(det, "bounding_box", None)
        or getattr(det, "box", None)
    )

    candidates = []

    if bbox_obj is not None:
        candidates.extend([
            bbox_from_minmax(
                first_number(bbox_obj, ["x_min", "xmin", "left"]),
                first_number(bbox_obj, ["y_min", "ymin", "top"]),
                first_number(bbox_obj, ["x_max", "xmax", "right"]),
                first_number(bbox_obj, ["y_max", "ymax", "bottom"]),
            ),
            bbox_from_xywh(
                first_number(bbox_obj, ["x", "left"]),
                first_number(bbox_obj, ["y", "top"]),
                first_number(bbox_obj, ["width", "w"]),
                first_number(bbox_obj, ["height", "h"]),
            ),
            bbox_from_center(
                first_number(bbox_obj, ["center.x", "center.position.x", "center_x", "cx"]),
                first_number(bbox_obj, ["center.y", "center.position.y", "center_y", "cy"]),
                first_number(bbox_obj, ["size_x", "width", "w"]),
                first_number(bbox_obj, ["size_y", "height", "h"]),
            ),
        ])

    candidates.extend([
        bbox_from_minmax(
            first_number(det, ["x_min", "xmin", "left"]),
            first_number(det, ["y_min", "ymin", "top"]),
            first_number(det, ["x_max", "xmax", "right"]),
            first_number(det, ["y_max", "ymax", "bottom"]),
        ),
        bbox_from_xywh(
            first_number(det, ["x", "left"]),
            first_number(det, ["y", "top"]),
            first_number(det, ["width", "w"]),
            first_number(det, ["height", "h"]),
        ),
    ])

    for candidate in candidates:
        if candidate is not None:
            return candidate

    return {
        "x_min": 0.0,
        "y_min": 0.0,
        "x_max": 0.0,
        "y_max": 0.0,
        "width": 0.0,
        "height": 0.0,
    }


def normalize_detections(msg) -> List[Dict[str, Any]]:
    raw_detections = getattr(msg, "detections", [])

    normalized = []

    for index, det in enumerate(raw_detections):
        base = extract_confidence_and_class(det)
        bbox = extract_bbox(det)

        normalized.append({
            "index": index,
            "confidence": base["confidence"],
            "class_id": base["class_id"],
            "class_name": base["class_name"],
            "bbox": bbox,
        })

    return normalized


def image_msg_to_bgr(msg: Image):
    encoding = msg.encoding.lower()
    raw = np.frombuffer(msg.data, dtype=np.uint8)

    if encoding in {"bgr8", "rgb8"}:
        channels = 3
        rows = raw.reshape(msg.height, int(msg.step))
        usable = rows[:, : msg.width * channels]
        image = usable.reshape(msg.height, msg.width, channels).copy()

        if encoding == "rgb8":
            image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)

        return image

    if encoding in {"mono8", "8uc1"}:
        rows = raw.reshape(msg.height, int(msg.step))
        usable = rows[:, : msg.width]
        return usable.reshape(msg.height, msg.width).copy()

    raise ValueError(f"Unsupported image encoding: {msg.encoding}")


class UncertainFrameNode(Node):
    def __init__(self):
        super().__init__("uncertain_frame_miner")

        self.declare_parameter("image_topic", "/camera/image_raw")
        self.declare_parameter("detections_topic", "/detections")
        self.declare_parameter("detections_type", "vision_msgs/msg/Detection2DArray")
        self.declare_parameter("output_dir", "reports/annotation/uncertain_frames")

        self.declare_parameter("min_confidence", 0.20)
        self.declare_parameter("max_confidence", 0.45)
        self.declare_parameter("small_object_area_ratio", 0.01)
        self.declare_parameter("many_detections_count", 5)
        self.declare_parameter("waterline_y_ratio", 0.35)
        self.declare_parameter("waterline_margin_ratio", 0.05)
        self.declare_parameter("enable_waterline_rules", True)

        self.declare_parameter("save_every_n_frames", 1)
        self.declare_parameter("max_saved_frames", 200)

        self.image_topic = self.get_parameter("image_topic").value
        self.detections_topic = self.get_parameter("detections_topic").value
        self.detections_type = self.get_parameter("detections_type").value
        self.output_dir = self.get_parameter("output_dir").value

        self.min_confidence = float(self.get_parameter("min_confidence").value)
        self.max_confidence = float(self.get_parameter("max_confidence").value)
        self.small_object_area_ratio = float(
            self.get_parameter("small_object_area_ratio").value
        )
        self.many_detections_count = int(self.get_parameter("many_detections_count").value)
        self.waterline_y_ratio = float(self.get_parameter("waterline_y_ratio").value)
        self.waterline_margin_ratio = float(
            self.get_parameter("waterline_margin_ratio").value
        )
        self.enable_waterline_rules = to_bool(
            self.get_parameter("enable_waterline_rules").value
        )

        self.save_every_n_frames = max(1, int(self.get_parameter("save_every_n_frames").value))
        self.max_saved_frames = max(1, int(self.get_parameter("max_saved_frames").value))

        self.latest_image_msg: Optional[Image] = None
        self.images_seen = 0
        self.detection_messages_seen = 0
        self.saved_frames = 0

        self.exporter = UncertaintyExporter(self.output_dir)

        detection_msg_type = import_message_type(self.detections_type)

        self.image_sub = self.create_subscription(
            Image,
            self.image_topic,
            self._on_image,
            qos_profile_sensor_data,
        )

        self.detection_sub = self.create_subscription(
            detection_msg_type,
            self.detections_topic,
            self._on_detections,
            10,
        )

        self.get_logger().info(
            "Uncertain-frame miner configured: "
            f"image_topic={self.image_topic}, detections_topic={self.detections_topic}, "
            f"detections_type={self.detections_type}, output_dir={self.output_dir}, "
            f"confidence_range=[{self.min_confidence}, {self.max_confidence}], "
            f"small_object_area_ratio={self.small_object_area_ratio}, "
            f"many_detections_count={self.many_detections_count}, "
            f"max_saved_frames={self.max_saved_frames}"
        )

    def _on_image(self, msg: Image):
        self.latest_image_msg = msg
        self.images_seen += 1

    def _on_detections(self, msg):
        self.detection_messages_seen += 1

        if self.latest_image_msg is None:
            return

        if self.saved_frames >= self.max_saved_frames:
            return

        if self.detection_messages_seen % self.save_every_n_frames != 0:
            return

        image_msg = self.latest_image_msg

        try:
            image = image_msg_to_bgr(image_msg)
        except Exception as exc:
            self.get_logger().warn(f"Could not convert image for mining: {exc}")
            return

        detections = normalize_detections(msg)

        result = evaluate_frame(
            detections,
            image_width=image_msg.width,
            image_height=image_msg.height,
            min_confidence=self.min_confidence,
            max_confidence=self.max_confidence,
            small_object_area_ratio=self.small_object_area_ratio,
            many_detections_count=self.many_detections_count,
            waterline_y_ratio=self.waterline_y_ratio,
            waterline_margin_ratio=self.waterline_margin_ratio,
            enable_waterline_rules=self.enable_waterline_rules,
        )

        if not result.selected:
            return

        self.saved_frames += 1

        detection_stamp = getattr(getattr(msg, "header", None), "stamp", None)
        image_stamp = getattr(image_msg.header, "stamp", None)

        try:
            image_file = self.exporter.save(
                saved_index=self.saved_frames,
                image=image,
                detections=detections,
                reasons=result.reasons,
                metrics=result.metrics,
                image_stamp=image_stamp,
                detection_stamp=detection_stamp,
            )

            self.get_logger().info(
                f"saved uncertain frame index={self.saved_frames} "
                f"file={image_file} reasons={','.join(result.reasons)} "
                f"detections={len(detections)}"
            )

        except Exception as exc:
            self.get_logger().error(f"Failed to save uncertain frame: {exc}")


def main(args=None):
    rclpy.init(args=args)
    node = UncertainFrameNode()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()

        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
