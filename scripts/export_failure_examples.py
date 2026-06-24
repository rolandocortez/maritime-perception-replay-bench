#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
from typing import Optional

import cv2
from cv_bridge import CvBridge
import rclpy
from rclpy.node import Node
from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import Image, RegionOfInterest
from vision_msgs.msg import Detection2DArray


def stamp_to_sec(stamp) -> float:
    return float(stamp.sec) + float(stamp.nanosec) * 1e-9


def bbox_to_xyxy(detection):
    bbox = detection.bbox
    cx = float(bbox.center.position.x)
    cy = float(bbox.center.position.y)
    w = float(bbox.size_x)
    h = float(bbox.size_y)

    return (
        int(round(cx - w / 2.0)),
        int(round(cy - h / 2.0)),
        int(round(cx + w / 2.0)),
        int(round(cy + h / 2.0)),
    )


def best_result(detection):
    if not detection.results:
        return "", 0.0

    best = max(detection.results, key=lambda result: float(result.hypothesis.score))
    return str(best.hypothesis.class_id), float(best.hypothesis.score)


def draw_label(image, text: str, x: int, y: int, color) -> None:
    font = cv2.FONT_HERSHEY_SIMPLEX
    scale = 0.55
    thickness = 1

    (tw, th), baseline = cv2.getTextSize(text, font, scale, thickness)
    x = max(0, int(x))
    y = max(th + 4, int(y))

    cv2.rectangle(
        image,
        (x, y - th - baseline - 4),
        (x + tw + 6, y + baseline),
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


class FailureSliceExporter(Node):
    def __init__(self, args):
        super().__init__("failure_slice_exporter")

        self.args = args
        self.bridge = CvBridge()

        self.latest_image = None
        self.latest_image_stamp_sec: Optional[float] = None
        self.latest_image_frame_id = ""
        self.latest_water_roi: Optional[RegionOfInterest] = None

        self.output_dir = Path(args.output)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.events_path = self.output_dir.parent / "failure_slices_events.jsonl"
        self.summary_path = self.output_dir.parent / "failure_slices_summary.json"

        self.saved_count = 0
        self.frame_counter = 0
        self.slice_counts = {
            "small_objects": 0,
            "horizon_clutter": 0,
            "glare_reflections": 0,
        }

        image_qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=5,
        )

        reliable_qos = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            history=HistoryPolicy.KEEP_LAST,
            depth=10,
        )

        self.create_subscription(Image, args.image_topic, self.on_image, image_qos)
        self.create_subscription(
            Detection2DArray,
            args.detections_topic,
            self.on_detections,
            reliable_qos,
        )
        self.create_subscription(
            RegionOfInterest,
            args.water_roi_topic,
            self.on_water_roi,
            reliable_qos,
        )

        self.get_logger().info(
            "Failure slice exporter configured: "
            f"slice={args.slice}, output={self.output_dir}, max_examples={args.max_examples}"
        )

    def on_image(self, msg: Image) -> None:
        try:
            self.latest_image = self.bridge.imgmsg_to_cv2(msg, desired_encoding="bgr8")
            self.latest_image_stamp_sec = stamp_to_sec(msg.header.stamp)
            self.latest_image_frame_id = msg.header.frame_id
        except Exception as exc:
            self.get_logger().error(f"Failed to convert image: {exc}")

    def on_water_roi(self, msg: RegionOfInterest) -> None:
        self.latest_water_roi = msg

    def on_detections(self, msg: Detection2DArray) -> None:
        if self.latest_image is None or self.latest_image_stamp_sec is None:
            return

        det_stamp_sec = stamp_to_sec(msg.header.stamp)
        delta_ms = abs(det_stamp_sec - self.latest_image_stamp_sec) * 1000.0

        if delta_ms > self.args.max_sync_delta_ms:
            return

        image_h, image_w = self.latest_image.shape[:2]
        image_area = float(image_w * image_h)

        candidates = []

        for detection in msg.detections:
            class_name, score = best_result(detection)

            bbox = detection.bbox
            center_x = float(bbox.center.position.x)
            center_y = float(bbox.center.position.y)
            width = float(bbox.size_x)
            height = float(bbox.size_y)

            area_ratio = (width * height) / image_area if image_area > 0.0 else 0.0

            matched_slices = self.classify_detection(
                center_y=center_y,
                area_ratio=area_ratio,
                score=score,
                image_height=image_h,
            )

            if self.args.slice != "all":
                matched_slices = [
                    name for name in matched_slices if name == self.args.slice
                ]

            if not matched_slices:
                continue

            candidates.append(
                {
                    "detection": detection,
                    "class_name": class_name,
                    "score": score,
                    "center_x": center_x,
                    "center_y": center_y,
                    "width": width,
                    "height": height,
                    "area_ratio": area_ratio,
                    "slices": matched_slices,
                }
            )

        if not candidates:
            self.frame_counter += 1
            return

        self.save_example(
            image=self.latest_image.copy(),
            candidates=candidates,
            msg=msg,
            delta_ms=delta_ms,
            image_width=image_w,
            image_height=image_h,
        )

        self.frame_counter += 1

        if self.saved_count >= self.args.max_examples:
            self.write_summary()
            self.get_logger().info("Reached max examples; shutting down.")
            rclpy.shutdown()

    def classify_detection(self, *, center_y, area_ratio, score, image_height):
        slices = []

        if area_ratio < self.args.small_area_ratio:
            slices.append("small_objects")

        if self.is_near_horizon_band(center_y=center_y, image_height=image_height):
            slices.append("horizon_clutter")

        if score <= self.args.glare_confidence_max and self.is_in_or_near_water_roi(center_y):
            slices.append("glare_reflections")

        return slices

    def is_near_horizon_band(self, *, center_y, image_height):
        if self.latest_water_roi is not None:
            waterline_y = float(self.latest_water_roi.y_offset)
            return abs(float(center_y) - waterline_y) <= float(self.args.horizon_band_px)

        y_ratio = float(center_y) / float(image_height)
        return self.args.horizon_y_ratio_min <= y_ratio <= self.args.horizon_y_ratio_max

    def is_in_or_near_water_roi(self, center_y):
        if self.latest_water_roi is None:
            return True

        y_min = float(self.latest_water_roi.y_offset) - float(self.args.horizon_band_px)
        y_max = float(self.latest_water_roi.y_offset + self.latest_water_roi.height)

        return y_min <= float(center_y) <= y_max

    def save_example(self, *, image, candidates, msg, delta_ms, image_width, image_height):
        primary_slice = candidates[0]["slices"][0]
        self.slice_counts[primary_slice] += 1

        filename = (
            f"{primary_slice}_{self.saved_count + 1:03d}"
            f"_frame_{self.frame_counter:06d}.png"
        )
        path = self.output_dir / filename

        for item in candidates:
            detection = item["detection"]
            x1, y1, x2, y2 = bbox_to_xyxy(detection)

            color = self.color_for_slice(item["slices"][0])
            cv2.rectangle(image, (x1, y1), (x2, y2), color, 2)

            label = (
                f"{'+'.join(item['slices'])} "
                f"{item['class_name']} {item['score']:.2f} "
                f"area={item['area_ratio']:.4f}"
            )
            draw_label(image, label, x1, y1 - 6, color)

        hud = [
            f"H18 failure slice: {primary_slice}",
            f"frame={self.frame_counter} detections={len(candidates)}",
            f"sync_delta={delta_ms:.1f}ms",
            f"image={image_width}x{image_height}",
        ]

        y = 24
        for line in hud:
            draw_label(image, line, 8, y, (40, 40, 40))
            y += 26

        cv2.imwrite(str(path), image)

        event = {
            "path": str(path),
            "primary_slice": primary_slice,
            "all_candidate_count": len(candidates),
            "stamp_sec": stamp_to_sec(msg.header.stamp),
            "frame_id": msg.header.frame_id,
            "sync_delta_ms": delta_ms,
            "detections": [
                {
                    "class_name": item["class_name"],
                    "score": item["score"],
                    "center_x": item["center_x"],
                    "center_y": item["center_y"],
                    "width": item["width"],
                    "height": item["height"],
                    "area_ratio": item["area_ratio"],
                    "slices": item["slices"],
                }
                for item in candidates
            ],
        }

        with self.events_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")

        self.saved_count += 1
        self.get_logger().info(f"saved {path}")

    @staticmethod
    def color_for_slice(slice_name):
        if slice_name == "small_objects":
            return (80, 220, 80)
        if slice_name == "horizon_clutter":
            return (0, 180, 255)
        if slice_name == "glare_reflections":
            return (0, 80, 255)
        return (255, 255, 255)

    def write_summary(self):
        summary = {
            "saved_count": self.saved_count,
            "slice_counts": self.slice_counts,
            "output_dir": str(self.output_dir),
            "events_jsonl": str(self.events_path),
            "notes": [
                "These are qualitative failure/debug slices, not ground truth metrics.",
                "Use them to inspect small objects, horizon clutter, and low-confidence water-region detections.",
            ],
        }

        self.summary_path.write_text(
            json.dumps(summary, indent=2) + "\n",
            encoding="utf-8",
        )


def parse_args():
    parser = argparse.ArgumentParser(
        description="Export maritime perception failure slice screenshots from live ROS2 topics."
    )

    parser.add_argument("--slice", choices=["all", "small_objects", "horizon_clutter", "glare_reflections"], default="all")
    parser.add_argument("--output", default="reports/failure_slices/examples")
    parser.add_argument("--max-examples", type=int, default=10)
    parser.add_argument("--image-topic", default="/camera/image_raw")
    parser.add_argument("--detections-topic", default="/detections")
    parser.add_argument("--water-roi-topic", default="/maritime/water_roi")
    parser.add_argument("--small-area-ratio", type=float, default=0.01)
    parser.add_argument("--horizon-band-px", type=float, default=120.0)
    parser.add_argument("--horizon-y-ratio-min", type=float, default=0.24)
    parser.add_argument("--horizon-y-ratio-max", type=float, default=0.40)
    parser.add_argument("--glare-confidence-max", type=float, default=0.35)
    parser.add_argument("--max-sync-delta-ms", type=float, default=250.0)

    return parser.parse_args()


def main():
    args = parse_args()

    rclpy.init()
    node = FailureSliceExporter(args)

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info("Interrupted by user.")
        node.write_summary()
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
