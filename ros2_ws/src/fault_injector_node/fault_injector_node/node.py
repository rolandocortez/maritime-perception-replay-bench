import rclpy
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data

from sensor_msgs.msg import Image
from std_msgs.msg import String

from fault_injector_node.frame_drop import FrameDropPolicy
from fault_injector_node.status import FaultInjectionStatus, make_status_json


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

        self.input_image_topic = self.get_parameter("input_image_topic").value
        self.output_image_topic = self.get_parameter("output_image_topic").value
        self.status_topic = self.get_parameter("status_topic").value
        self.mode = self.get_parameter("mode").value
        self.drop_probability = float(self.get_parameter("drop_probability").value)
        self.deterministic = bool(self.get_parameter("deterministic").value)
        self.random_seed = int(self.get_parameter("random_seed").value)
        self.log_every_n_frames = max(1, int(self.get_parameter("log_every_n_frames").value))

        if self.mode != "frame_drop":
            raise ValueError(f"Unsupported fault injection mode: {self.mode}")

        self.policy = FrameDropPolicy(
            drop_probability=self.drop_probability,
            deterministic=self.deterministic,
            random_seed=self.random_seed,
        )

        self.input_frames = 0
        self.forwarded_frames = 0
        self.dropped_frames = 0

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

        self.get_logger().info(
            "Fault injector configured: "
            f"mode={self.mode}, input_image_topic={self.input_image_topic}, "
            f"output_image_topic={self.output_image_topic}, status_topic={self.status_topic}, "
            f"drop_probability={self.drop_probability}, deterministic={self.deterministic}, "
            f"random_seed={self.random_seed}"
        )

    def on_image(self, msg: Image):
        self.input_frames += 1

        dropped = self.policy.should_drop(self.input_frames)

        if dropped:
            self.dropped_frames += 1
        else:
            self.forwarded_frames += 1
            self.image_pub.publish(msg)

        self.publish_status(last_frame_dropped=dropped)

        if self.input_frames % self.log_every_n_frames == 0:
            ratio = self.dropped_frames / max(1, self.input_frames)
            self.get_logger().info(
                f"frames_in={self.input_frames} forwarded={self.forwarded_frames} "
                f"dropped={self.dropped_frames} observed_drop_ratio={ratio:.3f}"
            )

    def publish_status(self, *, last_frame_dropped: bool):
        ratio = self.dropped_frames / max(1, self.input_frames)

        status = FaultInjectionStatus(
            mode=self.mode,
            input_frames=self.input_frames,
            forwarded_frames=self.forwarded_frames,
            dropped_frames=self.dropped_frames,
            drop_probability=self.drop_probability,
            observed_drop_ratio=ratio,
            deterministic=self.deterministic,
            random_seed=self.random_seed,
            last_frame_dropped=bool(last_frame_dropped),
            input_topic=self.input_image_topic,
            output_topic=self.output_image_topic,
        )

        msg = String()
        msg.data = make_status_json(status)
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
