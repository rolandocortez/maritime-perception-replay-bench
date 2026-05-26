from tracker_node.track_types import DetectionInput, TrackState


def bbox_iou(track: TrackState, detection: DetectionInput) -> float:
    det_x1 = detection.center_x - detection.width / 2.0
    det_y1 = detection.center_y - detection.height / 2.0
    det_x2 = detection.center_x + detection.width / 2.0
    det_y2 = detection.center_y + detection.height / 2.0

    inter_x1 = max(track.x1, det_x1)
    inter_y1 = max(track.y1, det_y1)
    inter_x2 = min(track.x2, det_x2)
    inter_y2 = min(track.y2, det_y2)

    inter_w = max(0.0, inter_x2 - inter_x1)
    inter_h = max(0.0, inter_y2 - inter_y1)
    inter_area = inter_w * inter_h

    track_area = max(0.0, track.width) * max(0.0, track.height)
    det_area = max(0.0, detection.width) * max(0.0, detection.height)
    union = track_area + det_area - inter_area

    if union <= 0.0:
        return 0.0

    return inter_area / union


class IouTracker:
    def __init__(
        self,
        *,
        iou_match_threshold: float = 0.3,
        max_age_frames: int = 15,
        min_hits: int = 2,
        class_aware: bool = True,
    ):
        self.iou_match_threshold = float(iou_match_threshold)
        self.max_age_frames = int(max_age_frames)
        self.min_hits = int(min_hits)
        self.class_aware = bool(class_aware)

        self._next_track_id = 1
        self._tracks: list[TrackState] = []

    @property
    def tracks(self) -> list[TrackState]:
        return list(self._tracks)

    def update(self, detections: list[DetectionInput]) -> tuple[list[TrackState], dict[str, int]]:
        matched_track_ids: set[int] = set()
        matched_detection_indexes: set[int] = set()

        matches: list[tuple[float, int, int]] = []

        # Match detections against tracks that existed before this frame.
        existing_tracks = list(self._tracks)

        for track_index, track in enumerate(existing_tracks):
            for detection_index, detection in enumerate(detections):
                if self.class_aware and track.class_name != detection.class_name:
                    continue

                score = bbox_iou(track, detection)
                if score >= self.iou_match_threshold:
                    matches.append((score, track_index, detection_index))

        matches.sort(key=lambda item: item[0], reverse=True)

        for _, track_index, detection_index in matches:
            track = existing_tracks[track_index]

            if track.track_id in matched_track_ids:
                continue
            if detection_index in matched_detection_indexes:
                continue

            track.update(detections[detection_index])
            matched_track_ids.add(track.track_id)
            matched_detection_indexes.add(detection_index)

        # Age unmatched tracks that existed before this frame.
        for track in existing_tracks:
            if track.track_id not in matched_track_ids:
                track.mark_missed()

        new_tracks = 0

        # Create tracks only after aging existing unmatched tracks, so newborn
        # tracks are not immediately counted as missed in their first frame.
        for detection_index, detection in enumerate(detections):
            if detection_index in matched_detection_indexes:
                continue

            self._tracks.append(
                TrackState(
                    track_id=self._next_track_id,
                    class_name=detection.class_name,
                    confidence=detection.confidence,
                    center_x=detection.center_x,
                    center_y=detection.center_y,
                    width=detection.width,
                    height=detection.height,
                )
            )
            self._next_track_id += 1
            new_tracks += 1

        before_prune = len(self._tracks)
        self._tracks = [
            track
            for track in self._tracks
            if track.missed_frames <= self.max_age_frames
        ]
        lost_tracks = before_prune - len(self._tracks)

        visible_tracks = [
            track
            for track in self._tracks
            if track.hits >= self.min_hits and track.missed_frames <= self.max_age_frames
        ]

        stats = {
            "active_tracks": len(visible_tracks),
            "new_tracks": new_tracks,
            "lost_tracks": lost_tracks,
        }

        return visible_tracks, stats
