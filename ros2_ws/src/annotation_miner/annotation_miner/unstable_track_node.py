from __future__ import annotations

import csv
import json
import shutil
from collections import deque
from pathlib import Path
from typing import Deque, Dict, List, Optional, Set, Tuple

import cv2
import rclpy
from cv_bridge import CvBridge
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image

from maritime_msgs.msg import Track2DArray

from .track_rules import (
    TrackEvent,
    TrackObservation,
    many_missed_event,
    observation_from_track,
    possible_id_switch_events,
    short_lived_event,
    stamp_to_sec,
)


class UnstableTrackMiner(Node):
    def __init__(self) -> None:
        super().__init__("unstable_track_miner")

        self.declare_parameter("tracks_topic", "/tracks")
        self.declare_parameter("image_topic", "/camera/image_raw")
        self.declare_parameter("output_dir", "reports/annotation/unstable_tracks")
        self.declare_parameter("min_track_age_for_stability", 5)
        self.declare_parameter("max_missed_frames", 3)
        self.declare_parameter("recently_lost_ttl_frames", 20)
        self.declare_parameter("save_context_frames_before", 10)
        self.declare_parameter("max_saved_events", 200)
        self.declare_parameter("dedupe_window_frames", 30)
        self.declare_parameter("id_switch_max_center_distance_px", 80.0)

        self.tracks_topic = str(self.get_parameter("tracks_topic").value)
        self.image_topic = str(self.get_parameter("image_topic").value)
        self.output_dir = Path(str(self.get_parameter("output_dir").value))
        self.min_track_age_for_stability = int(self.get_parameter("min_track_age_for_stability").value)
        self.max_missed_frames = int(self.get_parameter("max_missed_frames").value)
        self.recently_lost_ttl_frames = int(self.get_parameter("recently_lost_ttl_frames").value)
        self.save_context_frames_before = int(self.get_parameter("save_context_frames_before").value)
        self.max_saved_events = int(self.get_parameter("max_saved_events").value)
        self.dedupe_window_frames = int(self.get_parameter("dedupe_window_frames").value)
        self.id_switch_max_center_distance_px = float(self.get_parameter("id_switch_max_center_distance_px").value)

        self.images_dir = self.output_dir / "images"
        self.clips_dir = self.output_dir / "clips"
        self.buffer_dir = self.output_dir / ".frame_buffer"
        self.events_path = self.output_dir / "track_events.json"
        self.manifest_path = self.output_dir / "manifest.csv"

        for d in [self.images_dir, self.clips_dir, self.buffer_dir]:
            d.mkdir(parents=True, exist_ok=True)

        self.bridge = CvBridge()
        self.frame_index = 0
        self.saved_events = 0
        self.events: List[dict] = []

        self.image_buffer: Deque[Tuple[int, float, Path]] = deque(
            maxlen=max(1, self.save_context_frames_before + 5)
        )
        self.last_seen_by_track: Dict[int, TrackObservation] = {}
        self.active_track_ids: Set[int] = set()
        self.recently_lost: Deque[Tuple[int, TrackObservation]] = deque()
        self.last_event_frame_by_key: Dict[Tuple[str, int, Optional[int]], int] = {}

        self._init_manifest()

        self.create_subscription(Image, self.image_topic, self.on_image, qos_profile_sensor_data)
        self.create_subscription(Track2DArray, self.tracks_topic, self.on_tracks, 10)

        self.get_logger().info(
            f"Unstable track miner started: tracks_topic={self.tracks_topic}, "
            f"image_topic={self.image_topic}, output_dir={self.output_dir}"
        )

    def _init_manifest(self) -> None:
        with self.manifest_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "event_index",
                    "event_type",
                    "track_id",
                    "related_track_id",
                    "frame_index",
                    "stamp_sec",
                    "severity",
                    "class_name",
                    "confidence",
                    "age",
                    "missed_frames",
                    "reason",
                    "image_path",
                    "clip_dir",
                ],
            )
            writer.writeheader()

    def on_image(self, msg: Image) -> None:
        stamp_sec = stamp_to_sec(msg.header.stamp)

        try:
            image = self.bridge.imgmsg_to_cv2(msg, desired_encoding="bgr8")
        except Exception as exc:
            self.get_logger().warning(f"Failed to convert image: {exc}")
            return

        image_path = self.buffer_dir / f"frame_{self.frame_index:06d}.jpg"
        cv2.imwrite(str(image_path), image)

        self.image_buffer.append((self.frame_index, stamp_sec, image_path))
        self.frame_index += 1

    def on_tracks(self, msg: Track2DArray) -> None:
        if self.saved_events >= self.max_saved_events:
            return

        stamp_sec = stamp_to_sec(msg.header.stamp)
        current_frame_index = max(0, self.frame_index - 1)

        observations = [
            observation_from_track(track, stamp_sec, current_frame_index)
            for track in msg.tracks
        ]

        current_ids = {obs.track_id for obs in observations}
        previous_ids = set(self.active_track_ids)

        lost_ids = previous_ids - current_ids
        new_ids = current_ids - previous_ids

        for lost_id in lost_ids:
            lost_obs = self.last_seen_by_track.get(lost_id)
            if lost_obs is None:
                continue

            self.recently_lost.append((current_frame_index, lost_obs))

            event = short_lived_event(
                lost_obs,
                min_track_age_for_stability=self.min_track_age_for_stability,
            )
            if event is not None:
                self._save_event(event)

        while self.recently_lost and (
            current_frame_index - self.recently_lost[0][0] > self.recently_lost_ttl_frames
        ):
            self.recently_lost.popleft()

        for obs in observations:
            self.last_seen_by_track[obs.track_id] = obs

            event = many_missed_event(
                obs,
                max_missed_frames=self.max_missed_frames,
            )
            if event is not None:
                self._save_event(event)

        new_tracks = [obs for obs in observations if obs.track_id in new_ids]
        lost_tracks = [obs for _, obs in self.recently_lost]

        for event in possible_id_switch_events(
            new_tracks=new_tracks,
            recently_lost_tracks=lost_tracks,
            max_center_distance_px=self.id_switch_max_center_distance_px,
        ):
            self._save_event(event)

        self.active_track_ids = current_ids

    def _is_duplicate(self, event: TrackEvent) -> bool:
        key = (event.event_type, event.track_id, event.related_track_id)
        previous_frame = self.last_event_frame_by_key.get(key)

        if previous_frame is not None and event.frame_index - previous_frame <= self.dedupe_window_frames:
            return True

        self.last_event_frame_by_key[key] = event.frame_index
        return False

    def _latest_image_path(self) -> Optional[Path]:
        if not self.image_buffer:
            return None
        return self.image_buffer[-1][2]

    def _save_context_clip(self, event_index: int) -> Path:
        clip_dir = self.clips_dir / f"event_{event_index:06d}"
        clip_dir.mkdir(parents=True, exist_ok=True)

        for frame_idx, _stamp, src_path in list(self.image_buffer):
            if src_path.exists():
                shutil.copy2(src_path, clip_dir / f"frame_{frame_idx:06d}.jpg")

        return clip_dir

    def _save_event(self, event: TrackEvent) -> None:
        if self.saved_events >= self.max_saved_events or self._is_duplicate(event):
            return

        event_index = self.saved_events + 1

        image_path = ""
        latest_image = self._latest_image_path()
        if latest_image is not None and latest_image.exists():
            dst = self.images_dir / (
                f"event_{event_index:06d}_{event.event_type}_"
                f"track_{event.track_id}_frame_{event.frame_index:06d}.jpg"
            )
            shutil.copy2(latest_image, dst)
            image_path = str(dst)

        clip_dir = self._save_context_clip(event_index)

        event_dict = event.to_dict()
        event_dict["event_index"] = event_index
        event_dict["image_path"] = image_path
        event_dict["clip_dir"] = str(clip_dir)

        self.events.append(event_dict)
        self.saved_events += 1

        self._write_events_json()
        self._append_manifest(event_dict)

        self.get_logger().info(
            f"Saved unstable track event #{event_index}: "
            f"type={event.event_type}, track_id={event.track_id}, reason={event.reason}"
        )

    def _write_events_json(self) -> None:
        with self.events_path.open("w", encoding="utf-8") as f:
            json.dump(
                {
                    "schema_version": "1.0",
                    "source": "unstable_track_miner",
                    "tracks_topic": self.tracks_topic,
                    "image_topic": self.image_topic,
                    "events": self.events,
                },
                f,
                indent=2,
            )

    def _append_manifest(self, event_dict: dict) -> None:
        with self.manifest_path.open("a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "event_index",
                    "event_type",
                    "track_id",
                    "related_track_id",
                    "frame_index",
                    "stamp_sec",
                    "severity",
                    "class_name",
                    "confidence",
                    "age",
                    "missed_frames",
                    "reason",
                    "image_path",
                    "clip_dir",
                ],
            )
            writer.writerow(
                {
                    "event_index": event_dict.get("event_index", ""),
                    "event_type": event_dict.get("event_type", ""),
                    "track_id": event_dict.get("track_id", ""),
                    "related_track_id": event_dict.get("related_track_id", ""),
                    "frame_index": event_dict.get("frame_index", ""),
                    "stamp_sec": event_dict.get("stamp_sec", ""),
                    "severity": event_dict.get("severity", ""),
                    "class_name": event_dict.get("class_name", ""),
                    "confidence": event_dict.get("confidence", ""),
                    "age": event_dict.get("age", ""),
                    "missed_frames": event_dict.get("missed_frames", ""),
                    "reason": event_dict.get("reason", ""),
                    "image_path": event_dict.get("image_path", ""),
                    "clip_dir": event_dict.get("clip_dir", ""),
                }
            )


def main(args=None) -> None:
    rclpy.init(args=args)
    node = UnstableTrackMiner()

    try:
        rclpy.spin(node)
    except (KeyboardInterrupt, ExternalShutdownException):
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
