import json
import time
from typing import Optional

import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data

from sensor_msgs.msg import CameraInfo, Image
from std_msgs.msg import String


TRUE_VALUES = {"1", "true", "yes", "on"}


def to_bool(value) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).lower() in TRUE_VALUES


def make_image_msg(frame: np.ndarray, *, stamp, frame_id: str) -> Image:
    msg = Image()
    msg.header.stamp = stamp
    msg.header.frame_id = frame_id
    msg.height = int(frame.shape[0])
    msg.width = int(frame.shape[1])
    msg.encoding = "bgr8"
    msg.is_bigendian = 0
    msg.step = int(frame.shape[1] * frame.shape[2])
    msg.data = np.ascontiguousarray(frame).tobytes()
    return msg


def make_camera_info(*, width: int, height: int, stamp, frame_id: str) -> CameraInfo:
    msg = CameraInfo()
    msg.header.stamp = stamp
    msg.header.frame_id = frame_id
    msg.width = int(width)
    msg.height = int(height)
    return msg


class OakStatusNode(Node):
    def __init__(self):
        super().__init__("oak_status_node")

        self.declare_parameter("camera_name", "oak")
        self.declare_parameter("rgb_resolution", "1080p")
        self.declare_parameter("fps", 30.0)
        self.declare_parameter("publish_depth", False)
        self.declare_parameter("publish_imu", False)
        self.declare_parameter("remap_to_standard_camera_topics", False)
        self.declare_parameter("image_topic", "/oak/rgb/image_raw")
        self.declare_parameter("camera_info_topic", "/oak/rgb/camera_info")
        self.declare_parameter("standard_image_topic", "/camera/image_raw")
        self.declare_parameter("standard_camera_info_topic", "/camera/camera_info")
        self.declare_parameter("status_topic", "/oak/status")
        self.declare_parameter("frame_id", "oak_rgb_camera_frame")
        self.declare_parameter("status_log_every_n_frames", 30)

        self.camera_name = self.get_parameter("camera_name").value
        self.rgb_resolution = str(self.get_parameter("rgb_resolution").value).lower()
        self.fps = float(self.get_parameter("fps").value)
        self.publish_depth = to_bool(self.get_parameter("publish_depth").value)
        self.publish_imu = to_bool(self.get_parameter("publish_imu").value)
        self.remap_to_standard_camera_topics = to_bool(
            self.get_parameter("remap_to_standard_camera_topics").value
        )
        self.frame_id = self.get_parameter("frame_id").value
        self.status_log_every_n_frames = max(
            1,
            int(self.get_parameter("status_log_every_n_frames").value),
        )

        if self.remap_to_standard_camera_topics:
            self.image_topic = self.get_parameter("standard_image_topic").value
            self.camera_info_topic = self.get_parameter("standard_camera_info_topic").value
        else:
            self.image_topic = self.get_parameter("image_topic").value
            self.camera_info_topic = self.get_parameter("camera_info_topic").value

        self.status_topic = self.get_parameter("status_topic").value

        self.image_pub = self.create_publisher(Image, self.image_topic, qos_profile_sensor_data)
        self.camera_info_pub = self.create_publisher(CameraInfo, self.camera_info_topic, 10)
        self.status_pub = self.create_publisher(String, self.status_topic, 10)

        self.pipeline = None
        self.rgb_queue = None
        self.connected = False
        self.last_error = ""
        self.frames_published = 0
        self.started_at = time.monotonic()
        self.width = 0
        self.height = 0

        self._start_oak_v3()

        timer_period = 1.0 / max(1.0, self.fps)
        self.frame_timer = self.create_timer(timer_period, self._publish_frame)
        self.status_timer = self.create_timer(1.0, self._publish_status)

    def _resolution_size(self):
        mapping = {
            "720p": (1280, 720),
            "800p": (1280, 800),
            "1080p": (1920, 1080),
            "4k": (3840, 2160),
        }

        if self.rgb_resolution not in mapping:
            self.get_logger().warn(
                f"Unsupported rgb_resolution={self.rgb_resolution}; falling back to 1080p"
            )
            return mapping["1080p"]

        return mapping[self.rgb_resolution]

    def _start_oak_v3(self):
        try:
            import depthai as dai

            self.width, self.height = self._resolution_size()

            pipeline = dai.Pipeline()

            camera = pipeline.create(dai.node.Camera).build()
            output = camera.requestOutput(
                size=(self.width, self.height),
                type=dai.ImgFrame.Type.BGR888p,
                fps=float(self.fps),
            )
            self.rgb_queue = output.createOutputQueue()

            pipeline.start()
            self.pipeline = pipeline

            self.connected = True
            self.last_error = ""

            self.get_logger().info(
                "OAK ingest configured with DepthAI v3 API: "
                f"camera_name={self.camera_name}, resolution={self.rgb_resolution}, "
                f"size={self.width}x{self.height}, fps={self.fps}, "
                f"image_topic={self.image_topic}, camera_info_topic={self.camera_info_topic}, "
                f"status_topic={self.status_topic}, "
                f"remap_to_standard_camera_topics={self.remap_to_standard_camera_topics}"
            )

        except Exception as exc:
            self.connected = False
            self.last_error = str(exc)
            self.get_logger().error(
                "OAK device could not be started. "
                "The node will stay alive and publish status, but no images will be emitted. "
                f"error={exc}"
            )

    def _get_packet(self):
        if self.rgb_queue is None:
            return None

        if hasattr(self.rgb_queue, "tryGet"):
            return self.rgb_queue.tryGet()

        if hasattr(self.rgb_queue, "has") and self.rgb_queue.has():
            return self.rgb_queue.get()

        return None

    def _publish_frame(self):
        if not self.connected or self.rgb_queue is None:
            return

        packet = self._get_packet()
        if packet is None:
            return

        frame = packet.getCvFrame()
        stamp = self.get_clock().now().to_msg()

        image_msg = make_image_msg(frame, stamp=stamp, frame_id=self.frame_id)
        camera_info_msg = make_camera_info(
            width=frame.shape[1],
            height=frame.shape[0],
            stamp=stamp,
            frame_id=self.frame_id,
        )

        self.image_pub.publish(image_msg)
        self.camera_info_pub.publish(camera_info_msg)

        self.frames_published += 1

        if self.frames_published % self.status_log_every_n_frames == 0:
            elapsed = max(1e-6, time.monotonic() - self.started_at)
            observed_fps = self.frames_published / elapsed
            self.get_logger().info(
                f"OAK frames_published={self.frames_published} observed_fps={observed_fps:.2f}"
            )

    def _publish_status(self):
        elapsed = max(1e-6, time.monotonic() - self.started_at)
        observed_fps = self.frames_published / elapsed

        msg = String()
        msg.data = json.dumps(
            {
                "camera_name": self.camera_name,
                "connected": self.connected,
                "rgb_resolution": self.rgb_resolution,
                "configured_fps": self.fps,
                "observed_fps": observed_fps,
                "frames_published": self.frames_published,
                "image_topic": self.image_topic,
                "camera_info_topic": self.camera_info_topic,
                "status_topic": self.status_topic,
                "publish_depth": self.publish_depth,
                "publish_imu": self.publish_imu,
                "remap_to_standard_camera_topics": self.remap_to_standard_camera_topics,
                "last_error": self.last_error,
            },
            sort_keys=True,
        )
        self.status_pub.publish(msg)


def main(args: Optional[list] = None):
    rclpy.init(args=args)
    node = OakStatusNode()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node.pipeline is not None:
            try:
                node.pipeline.stop()
                node.pipeline.wait()
            except Exception:
                pass

        node.destroy_node()

        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
