import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data

from sensor_msgs.msg import Image
from std_msgs.msg import String

from fault_injector_node.delay import DelayPolicy, DelayQueue
from fault_injector_node.frame_drop import FrameDropPolicy
from fault_injector_node.image_utils import array_to_image, image_to_array
from fault_injector_node.status import make_status_json
from fault_injector_node.visual_degradation import VisualDegradationPipeline


def clock_now_sec(clock) -> float:
    return float(clock.now().nanoseconds) * 1e-9


class FaultInjectorNode(Node):
    def __init__(self):
        super().__init__("fault_injector_node")

        self.declare_parameter("input_image_topic", "/camera/image_raw")
        self.declare_parameter("output_image_topic", "/faults/image_raw")
        self.declare_parameter("status_topic", "/debug/fault_injection_status")
        self.declare_parameter("mode", "frame_drop")
        self.declare_parameter("drop_probability", 0.15)
        self.declare_parameter("deterministic", True)
        self.declare_parameter("random_seed", 42)
        self.declare_parameter("log_every_n_frames", 30)

        self.declare_parameter("visual_mode", "blur")
        self.declare_parameter("blur_kernel", 7)
        self.declare_parameter("jpeg_quality", 45)
        self.declare_parameter("brightness_delta", 20.0)
        self.declare_parameter("contrast_alpha", 1.2)
        self.declare_parameter("glare_enabled", True)
        self.declare_parameter("glare_strength", 0.25)
        self.declare_parameter("noise_sigma", 8.0)

        self.declare_parameter("delay_ms", 100.0)
        self.declare_parameter("jitter_ms", 20.0)
        self.declare_parameter("max_delay_queue", 500)
        self.declare_parameter("delay_timer_period_ms", 5.0)

        self.input_image_topic = self.get_parameter("input_image_topic").value
        self.output_image_topic = self.get_parameter("output_image_topic").value
        self.status_topic = self.get_parameter("status_topic").value
        self.mode = self.get_parameter("mode").value
        self.drop_probability = float(self.get_parameter("drop_probability").value)
        self.deterministic = bool(self.get_parameter("deterministic").value)
        self.random_seed = int(self.get_parameter("random_seed").value)
        self.log_every_n_frames = max(1, int(self.get_parameter("log_every_n_frames").value))

        self.visual_mode = self.get_parameter("visual_mode").value
        self.blur_kernel = int(self.get_parameter("blur_kernel").value)
        self.jpeg_quality = int(self.get_parameter("jpeg_quality").value)
        self.brightness_delta = float(self.get_parameter("brightness_delta").value)
        self.contrast_alpha = float(self.get_parameter("contrast_alpha").value)
        self.glare_enabled = bool(self.get_parameter("glare_enabled").value)
        self.glare_strength = float(self.get_parameter("glare_strength").value)
        self.noise_sigma = float(self.get_parameter("noise_sigma").value)

        self.delay_ms = float(self.get_parameter("delay_ms").value)
        self.jitter_ms = float(self.get_parameter("jitter_ms").value)
        self.max_delay_queue = int(self.get_parameter("max_delay_queue").value)
        self.delay_timer_period_ms = max(
            1.0,
            float(self.get_parameter("delay_timer_period_ms").value),
        )

        if self.mode not in ("frame_drop", "visual_degradation", "delay"):
            raise ValueError(f"Unsupported fault injection mode: {self.mode}")

        self.policy = FrameDropPolicy(
            drop_probability=self.drop_probability,
            deterministic=self.deterministic,
            random_seed=self.random_seed,
        )

        self.visual_pipeline = VisualDegradationPipeline(
            visual_mode=self.visual_mode,
            blur_kernel=self.blur_kernel,
            jpeg_quality=self.jpeg_quality,
            brightness_delta=self.brightness_delta,
            contrast_alpha=self.contrast_alpha,
            glare_enabled=self.glare_enabled,
            glare_strength=self.glare_strength,
            noise_sigma=self.noise_sigma,
            deterministic=self.deterministic,
            random_seed=self.random_seed,
        )

        self.delay_policy = DelayPolicy(
            delay_ms=self.delay_ms,
            jitter_ms=self.jitter_ms,
            deterministic=self.deterministic,
            random_seed=self.random_seed,
        )
        self.delay_queue = DelayQueue(max_queue_size=self.max_delay_queue)

        self.input_frames = 0
        self.forwarded_frames = 0
        self.dropped_frames = 0
        self.degraded_frames = 0
        self.delayed_frames = 0
        self.released_delayed_frames = 0
        self.last_applied_delay_ms = 0.0
        self.last_error = ""

        self.image_pub = self.create_publisher(
            Image,
            self.output_image_topic,
            qos_profile_sensor_data,
        )
        self.status_pub = self.create_publisher(
            String,
            self.status_topic,
            10,
        )
        self.image_sub = self.create_subscription(
            Image,
            self.input_image_topic,
            self.on_image,
            qos_profile_sensor_data,
        )

        self.delay_timer = self.create_timer(
            self.delay_timer_period_ms / 1000.0,
            self.release_delayed_messages,
        )

        self.get_logger().info(
            "Fault injector configured: "
            f"mode={self.mode}, visual_mode={self.visual_mode}, "
            f"input_image_topic={self.input_image_topic}, output_image_topic={self.output_image_topic}, "
            f"status_topic={self.status_topic}, drop_probability={self.drop_probability}, "
            f"deterministic={self.deterministic}, random_seed={self.random_seed}, "
            f"blur_kernel={self.blur_kernel}, jpeg_quality={self.jpeg_quality}, "
            f"brightness_delta={self.brightness_delta}, contrast_alpha={self.contrast_alpha}, "
            f"glare_enabled={self.glare_enabled}, glare_strength={self.glare_strength}, "
            f"noise_sigma={self.noise_sigma}, delay_ms={self.delay_ms}, "
            f"jitter_ms={self.jitter_ms}, max_delay_queue={self.max_delay_queue}"
        )

    def on_image(self, msg: Image):
        self.input_frames += 1
        dropped = False

        if self.mode == "frame_drop":
            dropped = self.policy.should_drop(self.input_frames)

            if dropped:
                self.dropped_frames += 1
            else:
                self.forwarded_frames += 1
                self.image_pub.publish(msg)

        elif self.mode == "visual_degradation":
            try:
                image, _ = image_to_array(msg)
                degraded = self.visual_pipeline.apply(image)
                output_msg = array_to_image(degraded, msg)
                self.forwarded_frames += 1
                self.degraded_frames += 1
                self.last_error = ""
                self.image_pub.publish(output_msg)
            except Exception as exc:
                self.last_error = str(exc)
                self.forwarded_frames += 1
                self.image_pub.publish(msg)
                self.get_logger().warn(
                    f"visual degradation failed; forwarding original frame: {exc}"
                )

        elif self.mode == "delay":
            delay_ms = self.delay_policy.sample_delay_ms()
            self.last_applied_delay_ms = delay_ms
            self.delayed_frames += 1
            self.delay_queue.push(
                msg=msg,
                now_sec=clock_now_sec(self.get_clock()),
                delay_ms=delay_ms,
            )

        self.publish_status(last_frame_dropped=dropped)

        if self.input_frames % self.log_every_n_frames == 0:
            ratio = self.dropped_frames / max(1, self.input_frames)
            self.get_logger().info(
                f"mode={self.mode} visual_mode={self.visual_mode} "
                f"frames_in={self.input_frames} forwarded={self.forwarded_frames} "
                f"dropped={self.dropped_frames} degraded={self.degraded_frames} "
                f"delayed={self.delayed_frames} released_delay={self.released_delayed_frames} "
                f"queued_delay={len(self.delay_queue)} "
                f"last_delay_ms={self.last_applied_delay_ms:.2f} "
                f"observed_drop_ratio={ratio:.3f}"
            )

    def release_delayed_messages(self):
        if self.mode != "delay":
            return

        now_sec = clock_now_sec(self.get_clock())
        released = 0

        while True:
            item = self.delay_queue.pop_due(now_sec=now_sec)

            if item is None:
                break

            self.image_pub.publish(item.msg)
            self.forwarded_frames += 1
            self.released_delayed_frames += 1
            self.last_applied_delay_ms = item.applied_delay_ms
            released += 1

        if released > 0:
            self.publish_status(last_frame_dropped=False)

    def publish_status(self, *, last_frame_dropped: bool):
        ratio = self.dropped_frames / max(1, self.input_frames)

        msg = String()
        msg.data = make_status_json(
            mode=self.mode,
            visual_mode=self.visual_mode,
            input_frames=self.input_frames,
            forwarded_frames=self.forwarded_frames,
            dropped_frames=self.dropped_frames,
            degraded_frames=self.degraded_frames,
            delayed_frames=self.delayed_frames,
            released_delayed_frames=self.released_delayed_frames,
            queued_delay_frames=len(self.delay_queue),
            dropped_due_to_delay_queue=self.delay_queue.dropped_due_to_queue,
            delay_ms=self.delay_ms,
            jitter_ms=self.jitter_ms,
            last_applied_delay_ms=self.last_applied_delay_ms,
            drop_probability=self.drop_probability,
            observed_drop_ratio=ratio,
            deterministic=self.deterministic,
            random_seed=self.random_seed,
            last_frame_dropped=bool(last_frame_dropped),
            input_topic=self.input_image_topic,
            output_topic=self.output_image_topic,
            blur_kernel=self.blur_kernel,
            jpeg_quality=self.jpeg_quality,
            brightness_delta=self.brightness_delta,
            contrast_alpha=self.contrast_alpha,
            glare_enabled=self.glare_enabled,
            glare_strength=self.glare_strength,
            noise_sigma=self.noise_sigma,
            last_error=self.last_error,
        )
        self.status_pub.publish(msg)


def main(args=None):
    rclpy.init(args=args)
    node = FaultInjectorNode()

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
