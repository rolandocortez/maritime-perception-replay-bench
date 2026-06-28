\
from __future__ import annotations

import json
import os
from typing import Optional

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import cv2
import numpy as np
import rclpy
from rclpy.node import Node
from sensor_msgs.msg import Image
from std_msgs.msg import Float32, Float32MultiArray, String

from .acoustic_features import (
    downsample_for_message,
    estimate_activity_threshold,
    read_wav_float32,
    rms_energy,
    slice_window,
)
from .fusion_support import compute_fusion_state
from .manifest import PairedReplayManifest, load_manifest


def frame_to_image_msg(frame: np.ndarray, stamp, frame_id: str) -> Image:
    msg = Image()
    msg.header.stamp = stamp
    msg.header.frame_id = frame_id
    msg.height = int(frame.shape[0])
    msg.width = int(frame.shape[1])
    msg.encoding = "bgr8"
    msg.is_bigendian = False
    msg.step = int(frame.shape[1] * 3)
    msg.data = frame.tobytes()
    return msg


def draw_status_overlay(
    frame: np.ndarray,
    *,
    sample_id: str,
    vessel_type: str,
    elapsed_sec: float,
    visual_confidence: float,
    acoustic_score: float,
    acoustic_threshold: float,
    fusion_status: str,
    visual_degraded: bool,
    acoustic_active: bool,
) -> np.ndarray:
    out = frame.copy()
    h, w = out.shape[:2]

    panel_h = 210
    overlay = out.copy()
    cv2.rectangle(overlay, (20, 20), (min(w - 20, 860), 20 + panel_h), (0, 0, 0), -1)
    out = cv2.addWeighted(overlay, 0.55, out, 0.45, 0)

    lines = [
        f"sample: {sample_id}",
        f"vessel: {vessel_type} | t={elapsed_sec:05.2f}s",
        f"visual confidence: {visual_confidence:.2f}" + ("  DEGRADED" if visual_degraded else ""),
        f"acoustic support: {'active' if acoustic_active else 'inactive'}  score={acoustic_score:.4f} threshold={acoustic_threshold:.4f}",
        f"fusion status: {fusion_status}",
    ]

    y = 55
    for line in lines:
        cv2.putText(out, line, (40, y), cv2.FONT_HERSHEY_SIMPLEX, 0.72, (255, 255, 255), 2, cv2.LINE_AA)
        y += 36

    cv2.putText(
        out,
        "visual tracking: not connected in this node",
        (40, min(h - 40, 20 + panel_h + 42)),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.72,
        (255, 255, 255),
        2,
        cv2.LINE_AA,
    )

    return out


class PairedReplayNode(Node):
    def __init__(self) -> None:
        super().__init__("paired_multimodal_replay")

        self.declare_parameter("manifest", "")
        self.declare_parameter("loop", False)
        self.declare_parameter("frame_id", "multimodal_replay")
        self.declare_parameter("raw_image_topic", "/multimodal/video/image_raw")
        self.declare_parameter("overlay_image_topic", "/multimodal/video/overlay")
        self.declare_parameter("waveform_topic", "/acoustic/waveform")
        self.declare_parameter("activity_topic", "/acoustic/activity")
        self.declare_parameter("fusion_debug_topic", "/fusion/debug_json")
        self.declare_parameter("contact_candidates_topic", "/fusion/contact_candidates")
        self.declare_parameter("audio_window_sec", 0.25)
        self.declare_parameter("degradation_start_sec", 4.0)
        self.declare_parameter("degradation_end_sec", 7.0)
        self.declare_parameter("normal_visual_confidence", 0.92)
        self.declare_parameter("degraded_visual_confidence", 0.35)
        self.declare_parameter("apply_visual_degradation", True)

        manifest_path = str(self.get_parameter("manifest").value)
        if not manifest_path:
            raise RuntimeError("Parameter 'manifest' is required.")

        self.manifest: PairedReplayManifest = load_manifest(manifest_path)
        self.loop = bool(self.get_parameter("loop").value)
        self.frame_id = str(self.get_parameter("frame_id").value)
        self.audio_window_sec = float(self.get_parameter("audio_window_sec").value)
        self.degradation_start_sec = float(self.get_parameter("degradation_start_sec").value)
        self.degradation_end_sec = float(self.get_parameter("degradation_end_sec").value)
        self.normal_visual_confidence = float(self.get_parameter("normal_visual_confidence").value)
        self.degraded_visual_confidence = float(self.get_parameter("degraded_visual_confidence").value)
        self.apply_visual_degradation = bool(self.get_parameter("apply_visual_degradation").value)

        self.cap = cv2.VideoCapture(str(self.manifest.video_path))
        if not self.cap.isOpened():
            raise RuntimeError(f"failed to open video: {self.manifest.video_path}")

        cap_fps = float(self.cap.get(cv2.CAP_PROP_FPS) or 0.0)
        self.fps = float(self.manifest.video_fps or cap_fps or 25.0)
        self.frame_index = int(max(0.0, self.manifest.video_start_sec) * self.fps)
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, self.frame_index)

        self.audio, self.sample_rate, self.channels = read_wav_float32(self.manifest.audio_path)
        self.acoustic_threshold = estimate_activity_threshold(
            self.audio,
            self.sample_rate,
            self.audio_window_sec,
            self.manifest.audio_start_sec,
            self.manifest.audio_end_sec,
        )

        self.raw_pub = self.create_publisher(Image, str(self.get_parameter("raw_image_topic").value), 10)
        self.overlay_pub = self.create_publisher(Image, str(self.get_parameter("overlay_image_topic").value), 10)
        self.waveform_pub = self.create_publisher(Float32MultiArray, str(self.get_parameter("waveform_topic").value), 10)
        self.activity_pub = self.create_publisher(Float32, str(self.get_parameter("activity_topic").value), 10)
        self.debug_pub = self.create_publisher(String, str(self.get_parameter("fusion_debug_topic").value), 10)
        self.contact_pub = self.create_publisher(String, str(self.get_parameter("contact_candidates_topic").value), 10)

        self.timer = self.create_timer(1.0 / self.fps, self._tick)

        self.get_logger().info(
            "paired replay started: "
            f"sample_id={self.manifest.sample_id}, fps={self.fps:.2f}, "
            f"sample_rate={self.sample_rate}, threshold={self.acoustic_threshold:.6f}"
        )

    def _current_elapsed_sec(self) -> float:
        return max(0.0, (self.frame_index / self.fps) - self.manifest.video_start_sec)

    def _tick(self) -> None:
        elapsed_sec = self._current_elapsed_sec()
        max_elapsed = self.manifest.video_end_sec - self.manifest.video_start_sec
        if max_elapsed > 0 and elapsed_sec > max_elapsed:
            if self.loop:
                self.frame_index = int(max(0.0, self.manifest.video_start_sec) * self.fps)
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, self.frame_index)
                elapsed_sec = self._current_elapsed_sec()
            else:
                self.get_logger().info("paired replay complete")
                self.timer.cancel()
                return

        ok, frame = self.cap.read()
        if not ok or frame is None:
            if self.loop:
                self.frame_index = int(max(0.0, self.manifest.video_start_sec) * self.fps)
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, self.frame_index)
                return
            self.get_logger().info("video stream ended")
            self.timer.cancel()
            return

        video_time_sec = self.manifest.video_start_sec + elapsed_sec
        audio_time_sec = self.manifest.audio_start_sec + elapsed_sec + self.manifest.audio_to_video_offset_sec
        window = slice_window(self.audio, self.sample_rate, audio_time_sec, self.audio_window_sec)
        activity_score = rms_energy(window)

        visual_degraded = self.degradation_start_sec <= elapsed_sec <= self.degradation_end_sec
        visual_confidence = self.degraded_visual_confidence if visual_degraded else self.normal_visual_confidence

        frame_for_overlay = frame
        if visual_degraded and self.apply_visual_degradation:
            frame_for_overlay = cv2.GaussianBlur(frame, (25, 25), 0)

        fusion = compute_fusion_state(
            visual_confidence=visual_confidence,
            visual_degraded=visual_degraded,
            acoustic_score=activity_score,
            acoustic_threshold=self.acoustic_threshold,
        )

        stamp = self.get_clock().now().to_msg()

        self.raw_pub.publish(frame_to_image_msg(frame, stamp, self.frame_id))

        overlay = draw_status_overlay(
            frame_for_overlay,
            sample_id=self.manifest.sample_id,
            vessel_type=self.manifest.vessel_type,
            elapsed_sec=elapsed_sec,
            visual_confidence=fusion.visual_confidence,
            acoustic_score=fusion.acoustic_score,
            acoustic_threshold=fusion.acoustic_threshold,
            fusion_status=fusion.fusion_status,
            visual_degraded=fusion.visual_degraded,
            acoustic_active=fusion.acoustic_active,
        )
        self.overlay_pub.publish(frame_to_image_msg(overlay, stamp, self.frame_id))

        wave_msg = Float32MultiArray()
        wave_msg.data = downsample_for_message(window, max_points=512)
        self.waveform_pub.publish(wave_msg)

        activity_msg = Float32()
        activity_msg.data = float(activity_score)
        self.activity_pub.publish(activity_msg)

        payload = {
            "sample_id": self.manifest.sample_id,
            "dataset": self.manifest.dataset,
            "license_review_required": self.manifest.license_review_required,
            "time": {
                "elapsed_sec": elapsed_sec,
                "video_time_sec": video_time_sec,
                "audio_time_sec": audio_time_sec,
            },
            "visual": {
                "track_id": None,
                "tracking_source": "not_connected_in_h56_node",
                "confidence": fusion.visual_confidence,
                "degraded": fusion.visual_degraded,
            },
            "acoustic": {
                "activity_score": fusion.acoustic_score,
                "activity_threshold": fusion.acoustic_threshold,
                "active": fusion.acoustic_active,
                "sample_rate_hz": self.sample_rate,
                "channels": self.channels,
            },
            "fusion_status": fusion.fusion_status,
        }

        msg = String()
        msg.data = json.dumps(payload, sort_keys=True)
        self.debug_pub.publish(msg)
        self.contact_pub.publish(msg)

        self.frame_index += 1


def main(args: Optional[list[str]] = None) -> None:
    rclpy.init(args=args)
    node: Optional[PairedReplayNode] = None
    try:
        node = PairedReplayNode()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
