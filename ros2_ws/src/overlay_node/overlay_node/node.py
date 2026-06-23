from cv_bridge import CvBridge
import rclpy
from rclpy.node import Node
from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy
from sensor_msgs.msg import Image
from vision_msgs.msg import Detection2DArray

from maritime_msgs.msg import Track2DArray
from overlay_node.draw import draw_detection, draw_hud, draw_track
from overlay_node.sync import is_within_sync_threshold, message_delta_ms, stamp_to_sec


class OverlayNode(Node):
    def __init__(self):
        super().__init__("overlay_node")

        self.declare_parameter("image_topic", "/camera/image_raw")
        self.declare_parameter("detections_topic", "/detections")
        self.declare_parameter("tracks_topic", "/tracks")
        self.declare_parameter("overlay_topic", "/debug/overlay_image")
        self.declare_parameter("draw_detections", True)
        self.declare_parameter("draw_tracks", True)
        self.declare_parameter("draw_confidence", True)
        self.declare_parameter("draw_track_age", True)
        self.declare_parameter("max_sync_delta_ms", 100.0)
        self.declare_parameter("publish_on_image", True)
        self.declare_parameter("log_every_n_frames", 30)

        self.image_topic = str(self.get_parameter("image_topic").value)
        self.detections_topic = str(self.get_parameter("detections_topic").value)
        self.tracks_topic = str(self.get_parameter("tracks_topic").value)
        self.overlay_topic = str(self.get_parameter("overlay_topic").value)
        self.draw_detections = bool(self.get_parameter("draw_detections").value)
        self.draw_tracks = bool(self.get_parameter("draw_tracks").value)
        self.draw_confidence = bool(self.get_parameter("draw_confidence").value)
        self.draw_track_age = bool(self.get_parameter("draw_track_age").value)
        self.max_sync_delta_ms = float(self.get_parameter("max_sync_delta_ms").value)
        self.publish_on_image = bool(self.get_parameter("publish_on_image").value)
        self.log_every_n_frames = int(self.get_parameter("log_every_n_frames").value)

        self.bridge = CvBridge()
        self.latest_detections = None
        self.latest_tracks = None
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

        self.tracks_sub = self.create_subscription(
            Track2DArray,
            self.tracks_topic,
            self.on_tracks,
            reliable_qos,
        )

        self.overlay_pub = self.create_publisher(
            Image,
            self.overlay_topic,
            image_qos,
        )

        self.get_logger().info(
            "Overlay configured: "
            f"image_topic={self.image_topic}, "
            f"detections_topic={self.detections_topic}, "
            f"tracks_topic={self.tracks_topic}, "
            f"overlay_topic={self.overlay_topic}, "
            f"draw_detections={self.draw_detections}, "
            f"draw_tracks={self.draw_tracks}, "
            f"max_sync_delta_ms={self.max_sync_delta_ms}"
        )

    def on_detections(self, msg: Detection2DArray) -> None:
        self.latest_detections = msg

    def on_tracks(self, msg: Track2DArray) -> None:
        self.latest_tracks = msg

    def on_image(self, msg: Image) -> None:
        try:
            image_bgr = self.bridge.imgmsg_to_cv2(msg, desired_encoding="bgr8")
        except Exception as exc:
            self.get_logger().error(f"Failed to convert image: {exc}")
            return

        overlay = image_bgr.copy()

        detections_used = 0
        tracks_used = 0
        detections_delta_ms = None
        tracks_delta_ms = None

        if self.draw_detections and self.latest_detections is not None:
            detections_delta_ms = message_delta_ms(
                msg.header.stamp,
                self.latest_detections.header.stamp,
            )

            if is_within_sync_threshold(
                msg.header.stamp,
                self.latest_detections.header.stamp,
                self.max_sync_delta_ms,
            ):
                for detection in self.latest_detections.detections:
                    draw_detection(
                        overlay,
                        detection,
                        draw_confidence=self.draw_confidence,
                    )
                detections_used = len(self.latest_detections.detections)

        if self.draw_tracks and self.latest_tracks is not None:
            tracks_delta_ms = message_delta_ms(
                msg.header.stamp,
                self.latest_tracks.header.stamp,
            )

            if is_within_sync_threshold(
                msg.header.stamp,
                self.latest_tracks.header.stamp,
                self.max_sync_delta_ms,
            ):
                for track in self.latest_tracks.tracks:
                    draw_track(
                        overlay,
                        track,
                        draw_confidence=self.draw_confidence,
                        draw_track_age=self.draw_track_age,
                    )
                tracks_used = len(self.latest_tracks.tracks)

        hud = [
            f"frame={self.frame_index}",
            f"stamp={stamp_to_sec(msg.header.stamp):.3f}",
            f"detections={detections_used}",
            f"tracks={tracks_used}",
        ]

        if detections_delta_ms is not None:
            hud.append(f"det_dt={detections_delta_ms:.1f}ms")
        if tracks_delta_ms is not None:
            hud.append(f"trk_dt={tracks_delta_ms:.1f}ms")

        draw_hud(overlay, hud)

        out = self.bridge.cv2_to_imgmsg(overlay, encoding="bgr8")
        out.header.stamp = msg.header.stamp
        out.header.frame_id = msg.header.frame_id
        self.overlay_pub.publish(out)

        if self.frame_index % max(1, self.log_every_n_frames) == 0:
            self.get_logger().info(
                f"frame={self.frame_index} "
                f"detections_used={detections_used} "
                f"tracks_used={tracks_used}"
            )

        self.frame_index += 1


def main(args=None):
    rclpy.init(args=args)
    node = OverlayNode()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info("Overlay interrupted by user.")
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
