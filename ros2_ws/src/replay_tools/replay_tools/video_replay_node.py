import threading
import time
from pathlib import Path

import cv2
import rclpy
from cv_bridge import CvBridge
from maritime_msgs.msg import FrameDebug
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, HistoryPolicy
from sensor_msgs.msg import Image


IMAGE_TOPIC = "/camera/image_raw"
FRAME_DEBUG_TOPIC = "/debug/frame_info"
DEFAULT_SOURCE_FPS = 30.0


class VideoReplayNode(Node):
    def __init__(self):
        super().__init__("video_replay_node")

        self.declare_parameter("video_path", "data/samples/harbor_sample.mp4")
        self.declare_parameter("publish_rate_hz", 0.0)
        self.declare_parameter("loop", False)
        self.declare_parameter("frame_id", "camera_frame")
        self.declare_parameter("scenario_name", "clean_replay")

        self.video_path = str(self.get_parameter("video_path").value)
        self.publish_rate_hz = float(self.get_parameter("publish_rate_hz").value)
        self.loop = bool(self.get_parameter("loop").value)
        self.frame_id = str(self.get_parameter("frame_id").value)
        self.scenario_name = str(self.get_parameter("scenario_name").value)

        self.bridge = CvBridge()
        self.stop_event = threading.Event()
        self.frame_index = 0
        self.start_monotonic = time.monotonic()

        image_qos = QoSProfile(
            reliability=ReliabilityPolicy.BEST_EFFORT,
            history=HistoryPolicy.KEEP_LAST,
            depth=5,
        )
        debug_qos = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            history=HistoryPolicy.KEEP_LAST,
            depth=10,
        )

        self.image_pub = self.create_publisher(Image, IMAGE_TOPIC, image_qos)
        self.debug_pub = self.create_publisher(FrameDebug, FRAME_DEBUG_TOPIC, debug_qos)

        self.cap = cv2.VideoCapture(self.video_path)
        if not self.cap.isOpened():
            self.get_logger().error(f"Could not open video: {self.video_path}")
            self.valid = False
            return

        self.valid = True
        self.source_fps = float(self.cap.get(cv2.CAP_PROP_FPS) or 0.0)
        if self.source_fps <= 0.0:
            self.source_fps = DEFAULT_SOURCE_FPS

        self.effective_rate_hz = self.publish_rate_hz if self.publish_rate_hz > 0.0 else self.source_fps
        if self.effective_rate_hz <= 0.0:
            self.effective_rate_hz = DEFAULT_SOURCE_FPS

        self.period_sec = 1.0 / self.effective_rate_hz

        self.get_logger().info(
            "Video replay configured: "
            f"video_path={self.video_path}, "
            f"source_fps={self.source_fps:.3f}, "
            f"publish_rate_hz={self.effective_rate_hz:.3f}, "
            f"loop={self.loop}, "
            f"frame_id={self.frame_id}, "
            f"scenario_name={self.scenario_name}, "
            f"image_topic={IMAGE_TOPIC}, "
            f"debug_topic={FRAME_DEBUG_TOPIC}"
        )

        self.worker = threading.Thread(target=self._publish_loop, daemon=True)
        self.worker.start()

    def _publish_loop(self):
        while rclpy.ok() and not self.stop_event.is_set():
            ok, frame = self.cap.read()

            if not ok:
                if self.loop:
                    self.get_logger().info("End of video reached; looping to first frame.")
                    self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    self.frame_index = 0
                    self.start_monotonic = time.monotonic()
                    continue

                self.get_logger().info("End of video reached; stopping replay cleanly.")
                self.stop_event.set()
                rclpy.shutdown()
                break

            now = self.get_clock().now()
            header_stamp = now.to_msg()

            image_msg = self.bridge.cv2_to_imgmsg(frame, encoding="bgr8")
            image_msg.header.stamp = header_stamp
            image_msg.header.frame_id = self.frame_id

            # source_timestamp_sec is dataset/video time.
            # publish_timestamp_sec is ROS publication time.
            # Keeping both makes replay runs easier to debug and compare.
            source_timestamp_sec = float(self.frame_index) / self.source_fps
            elapsed_sec = time.monotonic() - self.start_monotonic
            frame_age_ms = max(0.0, (elapsed_sec - source_timestamp_sec) * 1000.0)

            debug_msg = FrameDebug()
            debug_msg.header = image_msg.header
            debug_msg.frame_index = self.frame_index
            debug_msg.source_timestamp_sec = source_timestamp_sec
            debug_msg.publish_timestamp_sec = float(header_stamp.sec) + float(header_stamp.nanosec) * 1e-9
            debug_msg.frame_age_ms = float(frame_age_ms)
            debug_msg.scenario_name = self.scenario_name
            debug_msg.source_uri = self.video_path
            debug_msg.is_fault_injected = False
            debug_msg.fault_type = ""

            self.image_pub.publish(image_msg)
            self.debug_pub.publish(debug_msg)

            self.get_logger().debug(
                f"Published frame_index={self.frame_index} "
                f"source_timestamp_sec={source_timestamp_sec:.3f}"
            )

            self.frame_index += 1
            time.sleep(self.period_sec)

    def stop(self):
        self.stop_event.set()
        if hasattr(self, "worker") and self.worker.is_alive():
            self.worker.join(timeout=2.0)
        if hasattr(self, "cap") and self.cap is not None:
            self.cap.release()


def main(args=None):
    rclpy.init(args=args)
    node = VideoReplayNode()

    if not getattr(node, "valid", False):
        node.destroy_node()
        rclpy.shutdown()
        return

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info("Video replay interrupted by user.")
    finally:
        node.stop()
        if rclpy.ok():
            node.destroy_node()
            rclpy.shutdown()


if __name__ == "__main__":
    main()
