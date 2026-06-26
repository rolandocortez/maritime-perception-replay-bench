import numpy as np
import rclpy
from rclpy.node import Node

from sensor_msgs.msg import Image

from maritime_msgs.msg import AcousticEvent, AcousticEventArray, AcousticWindow

from spectrogram_node.event_detector import detect_event
from spectrogram_node.stft import compute_spectrogram, low_frequency_band_energy


class SpectrogramNode(Node):
    def __init__(self):
        super().__init__("spectrogram_node")

        self.declare_parameter("waveform_topic", "/acoustic/waveform")
        self.declare_parameter("spectrogram_topic", "/acoustic/spectrogram")
        self.declare_parameter("events_topic", "/acoustic/events")
        self.declare_parameter("n_fft", 1024)
        self.declare_parameter("hop_length", 256)
        self.declare_parameter("dynamic_range_db", 80.0)
        self.declare_parameter("event_method", "energy_threshold")
        self.declare_parameter("energy_threshold", 0.15)
        self.declare_parameter("min_event_duration_sec", 0.5)
        self.declare_parameter("low_frequency_max_hz", 500.0)
        self.declare_parameter("band_energy_threshold", 0.05)
        self.declare_parameter(
            "baseline_note",
            "Stub event interface only; not a validated acoustic classifier.",
        )
        self.declare_parameter("log_every_n_windows", 10)

        self.waveform_topic = self.get_parameter("waveform_topic").value
        self.spectrogram_topic = self.get_parameter("spectrogram_topic").value
        self.events_topic = self.get_parameter("events_topic").value
        self.n_fft = int(self.get_parameter("n_fft").value)
        self.hop_length = int(self.get_parameter("hop_length").value)
        self.dynamic_range_db = float(self.get_parameter("dynamic_range_db").value)
        self.event_method = self.get_parameter("event_method").value
        self.energy_threshold = float(self.get_parameter("energy_threshold").value)
        self.min_event_duration_sec = float(
            self.get_parameter("min_event_duration_sec").value
        )
        self.low_frequency_max_hz = float(self.get_parameter("low_frequency_max_hz").value)
        self.band_energy_threshold = float(
            self.get_parameter("band_energy_threshold").value
        )
        self.baseline_note = self.get_parameter("baseline_note").value
        self.log_every_n_windows = max(1, int(self.get_parameter("log_every_n_windows").value))

        self.spectrogram_pub = self.create_publisher(Image, self.spectrogram_topic, 10)
        self.events_pub = self.create_publisher(AcousticEventArray, self.events_topic, 10)

        self.subscription = self.create_subscription(
            AcousticWindow,
            self.waveform_topic,
            self.on_waveform,
            10,
        )

        self.window_count = 0

        self.get_logger().info(
            "Spectrogram node configured: "
            f"waveform_topic={self.waveform_topic}, "
            f"spectrogram_topic={self.spectrogram_topic}, events_topic={self.events_topic}, "
            f"n_fft={self.n_fft}, hop_length={self.hop_length}, "
            f"event_method={self.event_method}, energy_threshold={self.energy_threshold}"
        )
        self.get_logger().info(self.baseline_note)

    def on_waveform(self, msg: AcousticWindow):
        samples = np.asarray(msg.samples, dtype=np.float32)
        sample_rate = float(msg.sample_rate)

        spec = compute_spectrogram(
            samples,
            sample_rate=sample_rate,
            n_fft=self.n_fft,
            hop_length=self.hop_length,
            dynamic_range_db=self.dynamic_range_db,
        )

        image_msg = self._to_image_msg(spec.image_mono8, msg)
        self.spectrogram_pub.publish(image_msg)

        band_energy = low_frequency_band_energy(
            spec.magnitude,
            spec.freqs_hz,
            max_frequency_hz=self.low_frequency_max_hz,
        )

        candidate = detect_event(
            samples,
            event_method=self.event_method,
            energy_threshold=self.energy_threshold,
            start_sec=float(msg.window_start_sec),
            duration_sec=float(msg.window_duration_sec),
            min_event_duration_sec=self.min_event_duration_sec,
            dominant_frequency_hz=spec.dominant_frequency_hz,
            low_frequency_band_energy_value=band_energy,
            band_energy_threshold=self.band_energy_threshold,
        )

        event_array = AcousticEventArray()
        event_array.header = msg.header

        if candidate is not None:
            event = AcousticEvent()
            event.header = msg.header
            event.event_type = candidate.event_type
            event.confidence = float(candidate.confidence)
            event.start_sec = float(candidate.start_sec)
            event.duration_sec = float(candidate.duration_sec)
            event.energy = float(candidate.energy)
            event.dominant_frequency_hz = float(candidate.dominant_frequency_hz)
            event_array.events.append(event)

        self.events_pub.publish(event_array)

        if self.window_count % self.log_every_n_windows == 0:
            self.get_logger().info(
                f"window={self.window_count} "
                f"start_sec={msg.window_start_sec:.3f} "
                f"spectrogram={image_msg.width}x{image_msg.height} "
                f"events={len(event_array.events)} "
                f"dominant_frequency_hz={spec.dominant_frequency_hz:.1f}"
            )

        self.window_count += 1

    @staticmethod
    def _to_image_msg(image: np.ndarray, waveform_msg: AcousticWindow) -> Image:
        image_u8 = np.asarray(image, dtype=np.uint8)

        msg = Image()
        msg.header = waveform_msg.header
        msg.height = int(image_u8.shape[0])
        msg.width = int(image_u8.shape[1])
        msg.encoding = "mono8"
        msg.is_bigendian = False
        msg.step = int(msg.width)
        msg.data = image_u8.tobytes()

        return msg


def main(args=None):
    rclpy.init(args=args)
    node = SpectrogramNode()

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
