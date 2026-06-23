from cv_bridge import CvBridge
import rclpy
from rclpy.node import Node
from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import Image, RegionOfInterest
from vision_msgs.msg import Detection2DArray

from water_prior_node.filters import apply_water_roi_filter
from water_prior_node.heuristic import WaterRoi, compute_heuristic_water_roi
from water_prior_node.visualization import (
    draw_detection_with_roi_status,
    draw_hud,
    draw_water_roi,
)


class WaterPriorNode(Node):
    def __init__(self):
        super().__init__("water_prior_node")

        self.declare_parameter("image_topic", "/camera/image_raw")
        self.declare_parameter("detections_topic", "/detections")
        self.declare_parameter("filtered_detections_topic", "/maritime/filtered_detections")
        self.declare_parameter("water_roi_topic", "/maritime/water_roi")
        self.declare_parameter("water_prior_overlay_topic", "/debug/water_prior_overlay")
        self.declare_parameter("mode", "heuristic")
        self.declare_parameter("valid_y_min_ratio", 0.30)
        self.declare_parameter("valid_y_max_ratio", 1.00)
        self.declare_parameter("filter_policy", "soft")
        self.declare_parameter("soft_penalty", 0.25)
        self.declare_parameter("publish_overlay", True)
        self.declare_parameter("log_every_n_frames", 10)

        self.image_topic = str(self.get_parameter("image_topic").value)
        self.detections_topic = str(self.get_parameter("detections_topic").value)
        self.filtered_detections_topic = str(
            self.get_parameter("filtered_detections_topic").value
        )
        self.water_roi_topic = str(self.get_parameter("water_roi_topic").value)
        self.water_prior_overlay_topic = str(
            self.get_parameter("water_prior_overlay_topic").value
        )
        self.mode = str(self.get_parameter("mode").value)
        self.valid_y_min_ratio = float(self.get_parameter("valid_y_min_ratio").value)
        self.valid_y_max_ratio = float(self.get_parameter("valid_y_max_ratio").value)
        self.filter_policy = str(self.get_parameter("filter_policy").value)
        self.soft_penalty = float(self.get_parameter("soft_penalty").value)
        self.publish_overlay = bool(self.get_parameter("publish_overlay").value)
        self.log_every_n_frames = int(self.get_parameter("log_every_n_frames").value)

        if self.mode != "heuristic":
            raise RuntimeError(
                f"Unsupported mode={self.mode}. H17 currently supports mode='heuristic'."
            )

        self.bridge = CvBridge()
        self.latest_image_msg = None
        self.latest_image_bgr = None
        self.latest_roi: WaterRoi | None = None
        self.frame_index = 0

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

        self.image_sub = self.create_subscription(
            Image,
            self.image_topic,
            self.on_image,
            image_qos,
        )

        self.detections_sub = self.create_subscription(
            Detection2DArray,
            self.detections_topic,
            self.on_detections,
            reliable_qos,
        )

        self.filtered_detections_pub = self.create_publisher(
            Detection2DArray,
            self.filtered_detections_topic,
            reliable_qos,
        )

        self.water_roi_pub = self.create_publisher(
            RegionOfInterest,
            self.water_roi_topic,
            reliable_qos,
        )

        self.overlay_pub = self.create_publisher(
            Image,
            self.water_prior_overlay_topic,
            image_qos,
        )

        self.get_logger().info(
            "Water prior configured: "
            f"mode={self.mode}, "
            f"image_topic={self.image_topic}, "
            f"detections_topic={self.detections_topic}, "
            f"filtered_detections_topic={self.filtered_detections_topic}, "
            f"water_roi_topic={self.water_roi_topic}, "
            f"water_prior_overlay_topic={self.water_prior_overlay_topic}, "
            f"valid_y_min_ratio={self.valid_y_min_ratio}, "
            f"valid_y_max_ratio={self.valid_y_max_ratio}, "
            f"filter_policy={self.filter_policy}, "
            f"soft_penalty={self.soft_penalty}"
        )

    def on_image(self, msg: Image) -> None:
        try:
            self.latest_image_bgr = self.bridge.imgmsg_to_cv2(msg, desired_encoding="bgr8")
            self.latest_image_msg = msg
        except Exception as exc:
            self.get_logger().error(f"Failed to convert image: {exc}")
            return

        self.latest_roi = compute_heuristic_water_roi(
            image_width=int(msg.width),
            image_height=int(msg.height),
            valid_y_min_ratio=self.valid_y_min_ratio,
            valid_y_max_ratio=self.valid_y_max_ratio,
        )

        self.water_roi_pub.publish(self.latest_roi.to_msg())

    def on_detections(self, msg: Detection2DArray) -> None:
        if self.latest_roi is None:
            self.get_logger().warn("Skipping detections because no image/ROI has been received yet.")
            return

        filtered, stats = apply_water_roi_filter(
            detections_msg=msg,
            roi=self.latest_roi,
            filter_policy=self.filter_policy,
            soft_penalty=self.soft_penalty,
        )

        self.filtered_detections_pub.publish(filtered)

        if self.publish_overlay and self.latest_image_bgr is not None and self.latest_image_msg is not None:
            self._publish_overlay(
                detections_msg=filtered,
                stats=stats,
                roi=self.latest_roi,
            )

        if self.frame_index % max(1, self.log_every_n_frames) == 0:
            self.get_logger().info(
                f"frame={self.frame_index} "
                f"input={stats['input']} "
                f"kept={stats['kept']} "
                f"outside_roi={stats['outside_roi']} "
                f"penalized={stats['penalized']} "
                f"dropped={stats['dropped']}"
            )

        self.frame_index += 1

    def _publish_overlay(
        self,
        *,
        detections_msg: Detection2DArray,
        stats: dict[str, int],
        roi: WaterRoi,
    ) -> None:
        overlay = self.latest_image_bgr.copy()

        draw_water_roi(overlay, roi)

        for detection in detections_msg.detections:
            draw_detection_with_roi_status(overlay, detection, roi)

        draw_hud(
            overlay,
            [
                f"water_prior frame={self.frame_index}",
                f"policy={self.filter_policy} penalty={self.soft_penalty:.2f}",
                f"input={stats['input']} kept={stats['kept']}",
                f"outside={stats['outside_roi']} penalized={stats['penalized']} dropped={stats['dropped']}",
                f"roi_y=[{roi.y_min},{roi.y_max}]",
            ],
        )

        out = self.bridge.cv2_to_imgmsg(overlay, encoding="bgr8")
        out.header.stamp = detections_msg.header.stamp
        out.header.frame_id = detections_msg.header.frame_id
        self.overlay_pub.publish(out)


def main(args=None):
    rclpy.init(args=args)
    node = WaterPriorNode()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info("Water prior interrupted by user.")
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
