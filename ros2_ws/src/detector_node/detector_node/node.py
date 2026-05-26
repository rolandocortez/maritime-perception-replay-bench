from cv_bridge import CvBridge
import rclpy
from rclpy.node import Node
from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import Image
from std_msgs.msg import String
from vision_msgs.msg import (
    BoundingBox2D,
    Detection2D,
    Detection2DArray,
    ObjectHypothesisWithPose,
)

from detector_node.model_runner import YoloModelRunner
from detector_node.postprocessing import detections_to_json


class DetectorNode(Node):
    def __init__(self):
        super().__init__("detector_node")

        self.declare_parameter("model_backend", "ultralytics")
        self.declare_parameter("model_name", "yolo11n.pt")
        self.declare_parameter("device", "cpu")
        self.declare_parameter("image_topic", "/camera/image_raw")
        self.declare_parameter("detections_topic", "/detections")
        self.declare_parameter("detections_debug_topic", "/detections/debug_json")
        self.declare_parameter("confidence_threshold", 0.25)
        self.declare_parameter("iou_threshold", 0.45)
        self.declare_parameter("publish_debug_json", True)
        self.declare_parameter("max_detections", 100)
        self.declare_parameter("class_filter_enabled", False)
        self.declare_parameter("class_filter_names", [""])
        self.declare_parameter("log_every_n_frames", 10)

        self.model_backend = str(self.get_parameter("model_backend").value)
        self.model_name = str(self.get_parameter("model_name").value)
        self.device = str(self.get_parameter("device").value)
        self.image_topic = str(self.get_parameter("image_topic").value)
        self.detections_topic = str(self.get_parameter("detections_topic").value)
        self.detections_debug_topic = str(self.get_parameter("detections_debug_topic").value)
        self.confidence_threshold = float(self.get_parameter("confidence_threshold").value)
        self.iou_threshold = float(self.get_parameter("iou_threshold").value)
        self.publish_debug_json = bool(self.get_parameter("publish_debug_json").value)
        self.max_detections = int(self.get_parameter("max_detections").value)
        self.class_filter_enabled = bool(self.get_parameter("class_filter_enabled").value)
        raw_class_filter_names = self.get_parameter("class_filter_names").value or []
        self.class_filter_names = [
            str(name)
            for name in raw_class_filter_names
            if str(name).strip()
        ]
        self.log_every_n_frames = int(self.get_parameter("log_every_n_frames").value)

        if self.model_backend != "ultralytics":
            raise RuntimeError(f"Unsupported model_backend={self.model_backend}")

        self.bridge = CvBridge()
        self.frame_index = 0

        self.runner = YoloModelRunner(
            model_name=self.model_name,
            device=self.device,
            confidence_threshold=self.confidence_threshold,
            iou_threshold=self.iou_threshold,
            max_detections=self.max_detections,
            class_filter_enabled=self.class_filter_enabled,
            class_filter_names=self.class_filter_names,
        )

        image_qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=5,
        )

        detections_qos = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            history=HistoryPolicy.KEEP_LAST,
            depth=10,
        )

        debug_qos = QoSProfile(
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

        self.detections_pub = self.create_publisher(
            Detection2DArray,
            self.detections_topic,
            detections_qos,
        )

        self.debug_pub = self.create_publisher(
            String,
            self.detections_debug_topic,
            debug_qos,
        )

        self.get_logger().info(
            "Detector configured: "
            f"backend={self.model_backend}, "
            f"model={self.model_name}, "
            f"device={self.device}, "
            f"image_topic={self.image_topic}, "
            f"detections_topic={self.detections_topic}, "
            f"detections_debug_topic={self.detections_debug_topic}, "
            f"confidence_threshold={self.confidence_threshold}, "
            f"iou_threshold={self.iou_threshold}"
        )

    def on_image(self, msg):
        frame_stamp_sec = (
            float(msg.header.stamp.sec)
            + float(msg.header.stamp.nanosec) * 1e-9
        )

        try:
            image_bgr = self.bridge.imgmsg_to_cv2(msg, desired_encoding="bgr8")
            detections, inference_ms = self.runner.infer(image_bgr)
        except Exception as exc:
            self.get_logger().error(f"Detector failed on frame={self.frame_index}: {exc}")
            self.frame_index += 1
            return

        detections_msg = self._build_detection_array_msg(
            image_header=msg.header,
            detections=detections,
            inference_ms=inference_ms,
        )
        self.detections_pub.publish(detections_msg)

        if self.publish_debug_json:
            payload = detections_to_json(
                frame_index=self.frame_index,
                frame_stamp_sec=frame_stamp_sec,
                inference_ms=inference_ms,
                model_backend=self.model_backend,
                model_name=self.model_name,
                detections=detections,
            )
            out = String()
            out.data = payload
            self.debug_pub.publish(out)

        if self.frame_index % max(1, self.log_every_n_frames) == 0:
            self.get_logger().info(
                f"frame={self.frame_index} "
                f"detections={len(detections)} "
                f"inference_ms={inference_ms:.2f}"
            )

        self.frame_index += 1

    def _build_detection_array_msg(self, *, image_header, detections, inference_ms):
        array_msg = Detection2DArray()
        array_msg.header.stamp = image_header.stamp
        array_msg.header.frame_id = image_header.frame_id

        for index, det in enumerate(detections):
            detection_msg = Detection2D()
            detection_msg.header.stamp = image_header.stamp
            detection_msg.header.frame_id = image_header.frame_id
            detection_msg.id = f"frame_{self.frame_index}_det_{index}"

            bbox = BoundingBox2D()
            self._set_bbox_center(bbox, det.center_x, det.center_y)
            bbox.size_x = float(det.width)
            bbox.size_y = float(det.height)
            detection_msg.bbox = bbox

            hypothesis = ObjectHypothesisWithPose()
            hypothesis.hypothesis.class_id = str(det.class_name)
            hypothesis.hypothesis.score = float(det.confidence)
            detection_msg.results.append(hypothesis)

            array_msg.detections.append(detection_msg)

        return array_msg

    @staticmethod
    def _set_bbox_center(bbox, center_x, center_y):
        # Jazzy vision_msgs BoundingBox2D uses a Pose2D center.
        # Some versions expose center.position.x/y, others expose center.x/y.
        if hasattr(bbox.center, "position"):
            bbox.center.position.x = float(center_x)
            bbox.center.position.y = float(center_y)
        else:
            bbox.center.x = float(center_x)
            bbox.center.y = float(center_y)

        bbox.center.theta = 0.0


def main(args=None):
    rclpy.init(args=args)
    node = DetectorNode()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info("Detector interrupted by user.")
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
