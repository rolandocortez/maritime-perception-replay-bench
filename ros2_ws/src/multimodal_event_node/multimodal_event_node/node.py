import rclpy
from rclpy.node import Node

from maritime_msgs.msg import (
    AcousticEventArray,
    ContactCandidate,
    ContactCandidateArray,
    Track2DArray,
)

from multimodal_event_node.temporal_association import (
    fuse_confidence,
    within_temporal_window,
)


def stamp_to_sec(header) -> float:
    return float(header.stamp.sec) + float(header.stamp.nanosec) * 1e-9


def get_track_id(track) -> int:
    for field in ("track_id", "id"):
        if hasattr(track, field):
            return int(getattr(track, field))

    return -1


def get_track_confidence(track) -> float:
    for field in ("confidence", "score", "detection_score"):
        if hasattr(track, field):
            return float(getattr(track, field))

    return 1.0


class MultimodalEventNode(Node):
    def __init__(self):
        super().__init__("multimodal_event_node")

        self.declare_parameter("tracks_topic", "/tracks")
        self.declare_parameter("acoustic_events_topic", "/acoustic/events")
        self.declare_parameter("contact_candidates_topic", "/fusion/contact_candidates")
        self.declare_parameter("association_window_sec", 2.0)
        self.declare_parameter("fusion_policy", "temporal_only")
        self.declare_parameter("publish_acoustic_only_candidates", True)
        self.declare_parameter("publish_empty_candidates", False)
        self.declare_parameter(
            "baseline_note",
            "Temporal association interface only; no localization or operational target claim.",
        )
        self.declare_parameter("log_every_n_messages", 10)

        self.tracks_topic = self.get_parameter("tracks_topic").value
        self.acoustic_events_topic = self.get_parameter("acoustic_events_topic").value
        self.contact_candidates_topic = self.get_parameter("contact_candidates_topic").value
        self.association_window_sec = float(
            self.get_parameter("association_window_sec").value
        )
        self.fusion_policy = self.get_parameter("fusion_policy").value
        self.publish_acoustic_only_candidates = bool(
            self.get_parameter("publish_acoustic_only_candidates").value
        )
        self.publish_empty_candidates = bool(
            self.get_parameter("publish_empty_candidates").value
        )
        self.baseline_note = self.get_parameter("baseline_note").value
        self.log_every_n_messages = max(
            1,
            int(self.get_parameter("log_every_n_messages").value),
        )

        self.latest_tracks_msg = None
        self.latest_events_msg = None
        self.publish_count = 0

        self.publisher = self.create_publisher(
            ContactCandidateArray,
            self.contact_candidates_topic,
            10,
        )

        self.tracks_sub = self.create_subscription(
            Track2DArray,
            self.tracks_topic,
            self.on_tracks,
            10,
        )

        self.events_sub = self.create_subscription(
            AcousticEventArray,
            self.acoustic_events_topic,
            self.on_events,
            10,
        )

        self.get_logger().info(
            "Multimodal event node configured: "
            f"tracks_topic={self.tracks_topic}, "
            f"acoustic_events_topic={self.acoustic_events_topic}, "
            f"contact_candidates_topic={self.contact_candidates_topic}, "
            f"association_window_sec={self.association_window_sec}, "
            f"fusion_policy={self.fusion_policy}"
        )
        self.get_logger().info(self.baseline_note)

    def on_tracks(self, msg: Track2DArray):
        self.latest_tracks_msg = msg
        self.publish_candidates(trigger="tracks")

    def on_events(self, msg: AcousticEventArray):
        self.latest_events_msg = msg
        self.publish_candidates(trigger="acoustic_events")

    def publish_candidates(self, *, trigger: str):
        if self.latest_events_msg is None:
            return

        event_msg = self.latest_events_msg
        events = list(getattr(event_msg, "events", []))
        tracks = []

        if self.latest_tracks_msg is not None:
            tracks = list(getattr(self.latest_tracks_msg, "tracks", []))

        candidate_array = ContactCandidateArray()
        candidate_array.header = event_msg.header

        event_stamp_sec = stamp_to_sec(event_msg.header)
        track_stamp_sec = None
        association = None

        if self.latest_tracks_msg is not None:
            track_stamp_sec = stamp_to_sec(self.latest_tracks_msg.header)
            association = within_temporal_window(
                visual_stamp_sec=track_stamp_sec,
                acoustic_stamp_sec=event_stamp_sec,
                association_window_sec=self.association_window_sec,
            )

        if tracks and events and association is not None and association.within_window:
            for track in tracks:
                for event in events:
                    candidate_array.candidates.append(
                        self.make_candidate(
                            header=event_msg.header,
                            track_id=get_track_id(track),
                            has_visual_track=True,
                            has_acoustic_event=True,
                            visual_confidence=get_track_confidence(track),
                            acoustic_confidence=float(event.confidence),
                            explanation=(
                                "temporal_only: acoustic event within "
                                f"+/-{self.association_window_sec:.2f}s of visual track update; "
                                f"delta_sec={association.delta_sec:.3f}; "
                                "not a localization claim"
                            ),
                        )
                    )

        elif events and self.publish_acoustic_only_candidates:
            for event in events:
                candidate_array.candidates.append(
                    self.make_candidate(
                        header=event_msg.header,
                        track_id=-1,
                        has_visual_track=False,
                        has_acoustic_event=True,
                        visual_confidence=0.0,
                        acoustic_confidence=float(event.confidence),
                        explanation=(
                            "acoustic_event_only: event stream is available, "
                            "but no temporally associated visual track is present yet"
                        ),
                    )
                )

        if candidate_array.candidates or self.publish_empty_candidates:
            self.publisher.publish(candidate_array)

            if self.publish_count % self.log_every_n_messages == 0:
                delta_text = "n/a" if association is None else f"{association.delta_sec:.3f}"
                self.get_logger().info(
                    f"trigger={trigger} candidates={len(candidate_array.candidates)} "
                    f"tracks={len(tracks)} events={len(events)} delta_sec={delta_text}"
                )

            self.publish_count += 1

    @staticmethod
    def make_candidate(
        *,
        header,
        track_id: int,
        has_visual_track: bool,
        has_acoustic_event: bool,
        visual_confidence: float,
        acoustic_confidence: float,
        explanation: str,
    ) -> ContactCandidate:
        candidate = ContactCandidate()
        candidate.header = header
        candidate.track_id = int(track_id)
        candidate.has_visual_track = bool(has_visual_track)
        candidate.has_acoustic_event = bool(has_acoustic_event)
        candidate.visual_confidence = float(visual_confidence)
        candidate.acoustic_confidence = float(acoustic_confidence)
        candidate.fused_confidence = fuse_confidence(
            visual_confidence=float(visual_confidence),
            acoustic_confidence=float(acoustic_confidence),
            has_visual_track=bool(has_visual_track),
            has_acoustic_event=bool(has_acoustic_event),
        )
        candidate.explanation = explanation

        return candidate


def main(args=None):
    rclpy.init(args=args)
    node = MultimodalEventNode()

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
