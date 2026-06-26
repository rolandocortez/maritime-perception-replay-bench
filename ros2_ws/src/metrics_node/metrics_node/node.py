import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data

from sensor_msgs.msg import Image
from vision_msgs.msg import Detection2DArray

from maritime_msgs.msg import RuntimeMetricArray, TimingDiagnostic, TimingDiagnosticArray
from maritime_msgs.msg import Track2DArray

from metrics_node.latency import clock_now_sec, header_stamp_to_sec, latency_ms_from_header
from metrics_node.publishers import append_metric
from metrics_node.queue_diagnostics import QueueDelayEstimator
from metrics_node.rolling_stats import RollingTimestamps, RollingValues
from metrics_node.timing_diagnostics import diagnostic_status, make_stage_timing


class MetricsNode(Node):
    def __init__(self):
        super().__init__("metrics_node")

        self.declare_parameter("image_topic", "/camera/image_raw")
        self.declare_parameter("detections_topic", "/detections")
        self.declare_parameter("tracks_topic", "/tracks")
        self.declare_parameter("overlay_topic", "/debug/overlay_image")
        self.declare_parameter("metrics_topic", "/metrics/runtime")
        self.declare_parameter("pipeline_topic", "/metrics/pipeline")
        self.declare_parameter("timing_topic", "/metrics/timing")
        self.declare_parameter("diagnostics_topic", "/metrics/diagnostics")
        self.declare_parameter("window_size", 200)
        self.declare_parameter("publish_rate_hz", 1.0)
        self.declare_parameter("estimate_dropped_frames", True)
        self.declare_parameter("drop_gap_factor", 1.5)
        self.declare_parameter("target_input_fps", 0.0)
        self.declare_parameter("max_reasonable_latency_sec", 60.0)
        self.declare_parameter("timing_diagnostics_enabled", True)
        self.declare_parameter("warn_latency_ms", 100.0)
        self.declare_parameter("warn_skew_ms", 50.0)
        self.declare_parameter("log_every_n_publishes", 10)

        self.image_topic = self.get_parameter("image_topic").value
        self.detections_topic = self.get_parameter("detections_topic").value
        self.tracks_topic = self.get_parameter("tracks_topic").value
        self.overlay_topic = self.get_parameter("overlay_topic").value
        self.metrics_topic = self.get_parameter("metrics_topic").value
        self.pipeline_topic = self.get_parameter("pipeline_topic").value
        self.timing_topic = self.get_parameter("timing_topic").value
        self.diagnostics_topic = self.get_parameter("diagnostics_topic").value
        self.window_size = int(self.get_parameter("window_size").value)
        self.publish_rate_hz = float(self.get_parameter("publish_rate_hz").value)
        self.estimate_dropped_frames = bool(
            self.get_parameter("estimate_dropped_frames").value
        )
        self.drop_gap_factor = float(self.get_parameter("drop_gap_factor").value)
        self.target_input_fps = float(self.get_parameter("target_input_fps").value)
        self.max_reasonable_latency_sec = float(
            self.get_parameter("max_reasonable_latency_sec").value
        )
        self.timing_diagnostics_enabled = bool(
            self.get_parameter("timing_diagnostics_enabled").value
        )
        self.warn_latency_ms = float(self.get_parameter("warn_latency_ms").value)
        self.warn_skew_ms = float(self.get_parameter("warn_skew_ms").value)
        self.log_every_n_publishes = max(
            1,
            int(self.get_parameter("log_every_n_publishes").value),
        )

        if self.publish_rate_hz <= 0.0:
            raise ValueError("publish_rate_hz must be > 0")

        self.input_arrivals = RollingTimestamps(self.window_size)
        self.detection_arrivals = RollingTimestamps(self.window_size)
        self.track_arrivals = RollingTimestamps(self.window_size)
        self.overlay_arrivals = RollingTimestamps(self.window_size)

        self.detector_latency_ms = RollingValues(self.window_size)
        self.end_to_end_latency_ms = RollingValues(self.window_size)
        self.detections_per_frame = RollingValues(self.window_size)
        self.input_intervals_sec = RollingValues(self.window_size)
        self.dropped_frame_estimates = RollingValues(self.window_size)

        self.queue_estimators = {
            "detection": QueueDelayEstimator(self.window_size),
            "tracking": QueueDelayEstimator(self.window_size),
            "overlay": QueueDelayEstimator(self.window_size),
        }

        self.latest_timing = {}
        self.last_image_arrival_sec = None
        self.latest_image_header_stamp_sec = None
        self.latest_detection_receive_sec = None
        self.latest_track_receive_sec = None
        self.latest_active_tracks = 0
        self.publish_count = 0

        self.metrics_pub = self.create_publisher(RuntimeMetricArray, self.metrics_topic, 10)
        self.pipeline_pub = self.create_publisher(RuntimeMetricArray, self.pipeline_topic, 10)
        self.timing_pub = self.create_publisher(TimingDiagnosticArray, self.timing_topic, 10)
        self.diagnostics_pub = self.create_publisher(
            TimingDiagnosticArray,
            self.diagnostics_topic,
            10,
        )

        self.image_sub = self.create_subscription(
            Image,
            self.image_topic,
            self.on_image,
            qos_profile_sensor_data,
        )
        self.detections_sub = self.create_subscription(
            Detection2DArray,
            self.detections_topic,
            self.on_detections,
            10,
        )
        self.tracks_sub = self.create_subscription(
            Track2DArray,
            self.tracks_topic,
            self.on_tracks,
            10,
        )
        self.overlay_sub = self.create_subscription(
            Image,
            self.overlay_topic,
            self.on_overlay,
            qos_profile_sensor_data,
        )

        self.timer = self.create_timer(1.0 / self.publish_rate_hz, self.publish_metrics)

        self.get_logger().info(
            "Metrics node configured: "
            f"image_topic={self.image_topic}, detections_topic={self.detections_topic}, "
            f"tracks_topic={self.tracks_topic}, overlay_topic={self.overlay_topic}, "
            f"metrics_topic={self.metrics_topic}, pipeline_topic={self.pipeline_topic}, "
            f"timing_topic={self.timing_topic}, diagnostics_topic={self.diagnostics_topic}, "
            f"window_size={self.window_size}, publish_rate_hz={self.publish_rate_hz}"
        )

    def on_image(self, msg: Image):
        now_sec = clock_now_sec(self.get_clock())
        self.input_arrivals.add(now_sec)
        self.latest_image_header_stamp_sec = header_stamp_to_sec(msg.header)

        if self.last_image_arrival_sec is not None:
            interval_sec = now_sec - self.last_image_arrival_sec

            if interval_sec > 0.0:
                self.input_intervals_sec.add(interval_sec)
                self.dropped_frame_estimates.add(
                    self.estimate_drops_for_interval(interval_sec)
                )

        self.last_image_arrival_sec = now_sec

    def on_detections(self, msg: Detection2DArray):
        now_sec = clock_now_sec(self.get_clock())
        self.detection_arrivals.add(now_sec)
        self.detections_per_frame.add(len(msg.detections))

        latency = latency_ms_from_header(
            self.get_clock(),
            msg.header,
            max_reasonable_latency_sec=self.max_reasonable_latency_sec,
        )

        if latency is not None:
            self.detector_latency_ms.add(latency)

        self.record_stage_timing(
            stage="detection",
            header=msg.header,
            receive_sec=now_sec,
            upstream_receive_sec=self.last_image_arrival_sec,
        )
        self.latest_detection_receive_sec = now_sec

    def on_tracks(self, msg: Track2DArray):
        now_sec = clock_now_sec(self.get_clock())
        self.track_arrivals.add(now_sec)
        self.latest_active_tracks = len(msg.tracks)

        self.record_stage_timing(
            stage="tracking",
            header=msg.header,
            receive_sec=now_sec,
            upstream_receive_sec=self.latest_detection_receive_sec,
        )
        self.latest_track_receive_sec = now_sec

    def on_overlay(self, msg: Image):
        now_sec = clock_now_sec(self.get_clock())
        self.overlay_arrivals.add(now_sec)

        latency = latency_ms_from_header(
            self.get_clock(),
            msg.header,
            max_reasonable_latency_sec=self.max_reasonable_latency_sec,
        )

        if latency is not None:
            self.end_to_end_latency_ms.add(latency)

        self.record_stage_timing(
            stage="overlay",
            header=msg.header,
            receive_sec=now_sec,
            upstream_receive_sec=self.latest_track_receive_sec,
        )

    def record_stage_timing(self, *, stage: str, header, receive_sec: float, upstream_receive_sec):
        if not self.timing_diagnostics_enabled:
            return

        sensor_stamp_sec = header_stamp_to_sec(header)
        observed_latency_ms = 0.0

        if sensor_stamp_sec > 0.0 and receive_sec >= sensor_stamp_sec:
            observed_latency_ms = (receive_sec - sensor_stamp_sec) * 1000.0

        queue_delay_ms = self.queue_estimators[stage].estimate_delay_ms(
            observed_latency_ms
        )

        self.latest_timing[stage] = make_stage_timing(
            stage=stage,
            sensor_stamp_sec=sensor_stamp_sec,
            stage_receive_sec=receive_sec,
            upstream_receive_sec=upstream_receive_sec,
            reference_sensor_stamp_sec=self.latest_image_header_stamp_sec,
            estimated_queue_delay_ms=queue_delay_ms,
        )

    def estimate_drops_for_interval(self, interval_sec: float) -> int:
        if not self.estimate_dropped_frames:
            return 0

        if self.target_input_fps > 0.0:
            expected_period_sec = 1.0 / self.target_input_fps
        else:
            expected_period_sec = self.input_intervals_sec.percentile(50.0)

        if expected_period_sec <= 0.0:
            return 0

        if interval_sec <= expected_period_sec * self.drop_gap_factor:
            return 0

        return max(0, int(round(interval_sec / expected_period_sec)) - 1)

    def publish_metrics(self):
        msg = RuntimeMetricArray()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = "metrics_runtime"

        window_label = f"last_{self.window_size}_samples"

        entries = [
            ("input_fps", self.input_arrivals.rate_hz(), "Hz"),
            ("detector_fps", self.detection_arrivals.rate_hz(), "Hz"),
            ("tracker_fps", self.track_arrivals.rate_hz(), "Hz"),
            ("overlay_fps", self.overlay_arrivals.rate_hz(), "Hz"),
            (
                "end_to_end_latency_ms_p50",
                self.end_to_end_latency_ms.percentile(50.0),
                "ms",
            ),
            (
                "end_to_end_latency_ms_p95",
                self.end_to_end_latency_ms.percentile(95.0),
                "ms",
            ),
            (
                "detector_latency_ms_p50",
                self.detector_latency_ms.percentile(50.0),
                "ms",
            ),
            (
                "detector_latency_ms_p95",
                self.detector_latency_ms.percentile(95.0),
                "ms",
            ),
            ("active_tracks", float(self.latest_active_tracks), "count"),
            ("detections_per_frame", self.detections_per_frame.mean(), "count/frame"),
            (
                "dropped_frames_estimate",
                self.dropped_frame_estimates.total(),
                "frames",
            ),
        ]

        for name, value, unit in entries:
            append_metric(
                msg,
                name=name,
                value=value,
                unit=unit,
                window=window_label,
            )

        self.metrics_pub.publish(msg)
        self.pipeline_pub.publish(msg)
        self.publish_timing_diagnostics(msg.header)

        if self.publish_count % self.log_every_n_publishes == 0:
            self.get_logger().info(
                "runtime metrics: "
                f"input_fps={self.input_arrivals.rate_hz():.2f}, "
                f"detector_fps={self.detection_arrivals.rate_hz():.2f}, "
                f"tracker_fps={self.track_arrivals.rate_hz():.2f}, "
                f"overlay_fps={self.overlay_arrivals.rate_hz():.2f}, "
                f"e2e_p95_ms={self.end_to_end_latency_ms.percentile(95.0):.2f}, "
                f"detector_p95_ms={self.detector_latency_ms.percentile(95.0):.2f}, "
                f"active_tracks={self.latest_active_tracks}, "
                f"dropped_est={self.dropped_frame_estimates.total():.0f}"
            )

        self.publish_count += 1

    def publish_timing_diagnostics(self, header):
        if not self.timing_diagnostics_enabled:
            return

        msg = TimingDiagnosticArray()
        msg.header = header
        msg.header.frame_id = "metrics_timing"

        for stage in ("detection", "tracking", "overlay"):
            timing = self.latest_timing.get(stage)

            if timing is None:
                continue

            diagnostic = TimingDiagnostic()
            diagnostic.header = msg.header
            diagnostic.stage = timing.stage
            diagnostic.sensor_to_stage_ms = timing.sensor_to_stage_ms
            diagnostic.stage_processing_ms = timing.stage_processing_ms
            diagnostic.estimated_queue_delay_ms = timing.estimated_queue_delay_ms
            diagnostic.timestamp_skew_ms = timing.timestamp_skew_ms
            msg.diagnostics.append(diagnostic)

            status = diagnostic_status(
                timing=timing,
                warn_latency_ms=self.warn_latency_ms,
                warn_skew_ms=self.warn_skew_ms,
            )

            if status != "ok":
                self.get_logger().warn(
                    f"timing diagnostic stage={timing.stage} status={status} "
                    f"sensor_to_stage_ms={timing.sensor_to_stage_ms:.2f} "
                    f"stage_processing_ms={timing.stage_processing_ms:.2f} "
                    f"queue_delay_ms={timing.estimated_queue_delay_ms:.2f} "
                    f"timestamp_skew_ms={timing.timestamp_skew_ms:.2f}"
                )

        self.timing_pub.publish(msg)
        self.diagnostics_pub.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = MetricsNode()

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
