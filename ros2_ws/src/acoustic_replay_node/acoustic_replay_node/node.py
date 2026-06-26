from pathlib import Path

import rclpy
from rclpy.node import Node

from maritime_msgs.msg import AcousticWindow

from acoustic_replay_node.wav_reader import read_wav_mono
from acoustic_replay_node.windowing import slice_window


class AcousticReplayNode(Node):
    def __init__(self):
        super().__init__("acoustic_replay_node")

        self.declare_parameter("wav_path", "data/acoustic/sample.wav")
        self.declare_parameter("waveform_topic", "/acoustic/waveform")
        self.declare_parameter("window_duration_sec", 1.0)
        self.declare_parameter("hop_duration_sec", 0.5)
        self.declare_parameter("publish_rate_hz", 2.0)
        self.declare_parameter("normalize", True)
        self.declare_parameter("loop", True)
        self.declare_parameter("frame_id", "acoustic_frame")

        wav_path = self.get_parameter("wav_path").value
        self.waveform_topic = self.get_parameter("waveform_topic").value
        self.window_duration_sec = float(self.get_parameter("window_duration_sec").value)
        self.hop_duration_sec = float(self.get_parameter("hop_duration_sec").value)
        self.publish_rate_hz = float(self.get_parameter("publish_rate_hz").value)
        normalize = bool(self.get_parameter("normalize").value)
        self.loop = bool(self.get_parameter("loop").value)
        self.frame_id = self.get_parameter("frame_id").value

        if self.window_duration_sec <= 0.0:
            raise ValueError("window_duration_sec must be > 0")

        if self.hop_duration_sec <= 0.0:
            raise ValueError("hop_duration_sec must be > 0")

        if self.publish_rate_hz <= 0.0:
            raise ValueError("publish_rate_hz must be > 0")

        if not Path(wav_path).exists():
            raise FileNotFoundError(f"WAV path does not exist: {wav_path}")

        self.audio = read_wav_mono(wav_path, normalize=normalize)
        self.window_samples = max(1, int(round(self.window_duration_sec * self.audio.sample_rate)))
        self.hop_samples = max(1, int(round(self.hop_duration_sec * self.audio.sample_rate)))
        self.cursor = 0
        self.frame_count = 0

        self.publisher = self.create_publisher(AcousticWindow, self.waveform_topic, 10)
        self.timer = self.create_timer(1.0 / self.publish_rate_hz, self.on_timer)

        self.get_logger().info(
            "Acoustic replay configured: "
            f"wav_path={wav_path}, sample_rate={self.audio.sample_rate}, "
            f"duration_sec={self.audio.duration_sec:.3f}, topic={self.waveform_topic}, "
            f"window_duration_sec={self.window_duration_sec}, hop_duration_sec={self.hop_duration_sec}, "
            f"publish_rate_hz={self.publish_rate_hz}, normalize={normalize}, loop={self.loop}"
        )

    def on_timer(self):
        window = slice_window(
            self.audio.samples,
            start_sample=self.cursor,
            window_samples=self.window_samples,
            sample_rate=self.audio.sample_rate,
            loop=self.loop,
        )

        if window is None:
            self.get_logger().info("Reached end of WAV; stopping acoustic replay timer.")
            self.timer.cancel()
            return

        msg = AcousticWindow()
        msg.header.stamp = self.get_clock().now().to_msg()
        msg.header.frame_id = self.frame_id
        msg.sample_rate = float(self.audio.sample_rate)
        msg.window_start_sec = float(window.start_sec)
        msg.window_duration_sec = float(window.duration_sec)
        msg.samples = [float(value) for value in window.samples]

        self.publisher.publish(msg)

        if self.frame_count % 10 == 0:
            self.get_logger().info(
                f"window={self.frame_count} start_sec={window.start_sec:.3f} "
                f"duration_sec={window.duration_sec:.3f} samples={len(msg.samples)}"
            )

        self.cursor += self.hop_samples

        if self.loop and self.cursor >= self.audio.samples.size:
            self.cursor = self.cursor % self.audio.samples.size

        self.frame_count += 1


def main(args=None):
    rclpy.init(args=args)
    node = AcousticReplayNode()

    try:
        rclpy.spin(node)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
