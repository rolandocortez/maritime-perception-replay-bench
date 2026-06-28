import rclpy
from rclpy.node import Node
from rclpy.qos import HistoryPolicy, QoSProfile, ReliabilityPolicy
from vision_msgs.msg import Detection2DArray

from maritime_msgs.msg import Track2D, Track2DArray
from tracker_node.iou_tracker import IouTracker
from tracker_node.track_types import DetectionInput


class TrackerNode(Node):
    def __init__(self):
        super().__init__("tracker_node")

        self.declare_parameter("detections_topic", "/detections")
        self.declare_parameter("tracks_topic", "/tracks")
        self.declare_parameter("tracker_type", "iou")
        self.declare_parameter("iou_match_threshold", 0.3)
        self.declare_parameter("max_age_frames", 4)
        self.declare_parameter("min_hits", 1)
        self.declare_parameter("class_aware", True)
        self.declare_parameter("log_every_n_frames", 10)

        self.detections_topic = str(self.get_parameter("detections_topic").value)
        self.tracks_topic = str(self.get_parameter("tracks_topic").value)
        self.tracker_type = str(self.get_parameter("tracker_type").value)
        self.iou_match_threshold = float(self.get_parameter("iou_match_threshold").value)
        self.max_age_frames = int(self.get_parameter("max_age_frames").value)
        self.min_hits = int(self.get_parameter("min_hits").value)
        self.class_aware = bool(self.get_parameter("class_aware").value)
        self.log_every_n_frames = int(self.get_parameter("log_every_n_frames").value)

        if self.tracker_type != "iou":
            raise RuntimeError(
                f"Unsupported tracker_type={self.tracker_type}. "
                "H15 currently supports tracker_type='iou'."
            )

        self.tracker = IouTracker(
            iou_match_threshold=self.iou_match_threshold,
            max_age_frames=self.max_age_frames,
            min_hits=self.min_hits,
            class_aware=self.class_aware,
        )

        self.frame_index = 0

        detections_qos = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            history=HistoryPolicy.KEEP_LAST,
            depth=10,
        )

        tracks_qos = QoSProfile(
            reliability=ReliabilityPolicy.RELIABLE,
            history=HistoryPolicy.KEEP_LAST,
            depth=10,
        )

        self.detections_sub = self.create_subscription(
            Detection2DArray,
            self.detections_topic,
            self.on_detections,
            detections_qos,
        )

        self.tracks_pub = self.create_publisher(
            Track2DArray,
            self.tracks_topic,
            tracks_qos,
        )

        self.get_logger().info(
            "Tracker configured: "
            f"tracker_type={self.tracker_type}, "
            f"detections_topic={self.detections_topic}, "
            f"tracks_topic={self.tracks_topic}, "
            f"iou_match_threshold={self.iou_match_threshold}, "
            f"max_age_frames={self.max_age_frames}, "
            f"min_hits={self.min_hits}, "
            f"class_aware={self.class_aware}"
        )

    def on_detections(self, msg: Detection2DArray) -> None:
        detections = self._parse_detections(msg)
        tracks, stats = self.tracker.update(detections)

        out = Track2DArray()
        out.header.stamp = msg.header.stamp
        out.header.frame_id = msg.header.frame_id

        for track in tracks:
            track_msg = Track2D()
            track_msg.header.stamp = msg.header.stamp
            track_msg.header.frame_id = msg.header.frame_id
            track_msg.track_id = int(track.track_id)
            track_msg.class_name = str(track.class_name)
            track_msg.confidence = float(track.confidence)
            track_msg.center_x = float(track.center_x)
            track_msg.center_y = float(track.center_y)
            track_msg.width = float(track.width)
            track_msg.height = float(track.height)
            track_msg.velocity_x = float(track.velocity_x)
            track_msg.velocity_y = float(track.velocity_y)
            track_msg.age = int(track.age)
            track_msg.missed_frames = int(track.missed_frames)
            out.tracks.append(track_msg)

        self.tracks_pub.publish(out)

        if self.frame_index % max(1, self.log_every_n_frames) == 0:
            self.get_logger().info(
                f"frame={self.frame_index} "
                f"detections={len(detections)} "
                f"active_tracks={stats['active_tracks']} "
                f"new_tracks={stats['new_tracks']} "
                f"lost_tracks={stats['lost_tracks']}"
            )

        self.frame_index += 1

    @staticmethod
    def _parse_detections(msg: Detection2DArray) -> list[DetectionInput]:
        parsed: list[DetectionInput] = []

        for detection in msg.detections:
            if not detection.results:
                continue

            best_result = max(
                detection.results,
                key=lambda result: float(result.hypothesis.score),
            )

            class_name = str(best_result.hypothesis.class_id)
            confidence = float(best_result.hypothesis.score)

            parsed.append(
                DetectionInput(
                    class_name=class_name,
                    confidence=confidence,
                    center_x=float(detection.bbox.center.position.x),
                    center_y=float(detection.bbox.center.position.y),
                    width=float(detection.bbox.size_x),
                    height=float(detection.bbox.size_y),
                )
            )

        return parsed


def main(args=None):
    rclpy.init(args=args)
    node = TrackerNode()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        node.get_logger().info("Tracker interrupted by user.")
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
