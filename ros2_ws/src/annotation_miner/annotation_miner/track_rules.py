from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, List, Optional


@dataclass(frozen=True)
class TrackBox:
    center_x: float
    center_y: float
    width: float
    height: float


@dataclass(frozen=True)
class TrackObservation:
    track_id: int
    stamp_sec: float
    frame_index: int
    class_name: str
    confidence: float
    age: int
    missed_frames: int
    bbox: TrackBox


@dataclass(frozen=True)
class TrackEvent:
    event_type: str
    track_id: int
    stamp_sec: float
    frame_index: int
    reason: str
    severity: float
    class_name: str
    confidence: float
    age: int
    missed_frames: int
    bbox: TrackBox
    related_track_id: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["bbox"] = asdict(self.bbox)
        return data


def stamp_to_sec(stamp: Any) -> float:
    return float(getattr(stamp, "sec", 0)) + float(getattr(stamp, "nanosec", 0)) * 1e-9


def observation_from_track(track: Any, stamp_sec: float, frame_index: int) -> TrackObservation:
    return TrackObservation(
        track_id=int(getattr(track, "track_id", -1)),
        stamp_sec=stamp_sec,
        frame_index=frame_index,
        class_name=str(getattr(track, "class_name", "")),
        confidence=float(getattr(track, "confidence", 0.0)),
        age=int(getattr(track, "age", 0)),
        missed_frames=int(getattr(track, "missed_frames", 0)),
        bbox=TrackBox(
            center_x=float(getattr(track, "center_x", 0.0)),
            center_y=float(getattr(track, "center_y", 0.0)),
            width=float(getattr(track, "width", 0.0)),
            height=float(getattr(track, "height", 0.0)),
        ),
    )


def _center_distance(a: TrackBox, b: TrackBox) -> float:
    dx = a.center_x - b.center_x
    dy = a.center_y - b.center_y
    return (dx * dx + dy * dy) ** 0.5


def short_lived_event(
    obs: TrackObservation,
    min_track_age_for_stability: int,
) -> Optional[TrackEvent]:
    if obs.age >= min_track_age_for_stability:
        return None

    severity = 1.0 - (float(obs.age) / max(1.0, float(min_track_age_for_stability)))
    return TrackEvent(
        event_type="short_lived_track",
        track_id=obs.track_id,
        stamp_sec=obs.stamp_sec,
        frame_index=obs.frame_index,
        reason=f"track disappeared with age={obs.age} < min_track_age_for_stability={min_track_age_for_stability}",
        severity=severity,
        class_name=obs.class_name,
        confidence=obs.confidence,
        age=obs.age,
        missed_frames=obs.missed_frames,
        bbox=obs.bbox,
    )


def many_missed_event(
    obs: TrackObservation,
    max_missed_frames: int,
) -> Optional[TrackEvent]:
    if obs.missed_frames < max_missed_frames:
        return None

    severity = min(1.0, float(obs.missed_frames) / max(1.0, float(max_missed_frames * 2)))
    return TrackEvent(
        event_type="many_missed_frames",
        track_id=obs.track_id,
        stamp_sec=obs.stamp_sec,
        frame_index=obs.frame_index,
        reason=f"track missed_frames={obs.missed_frames} >= max_missed_frames={max_missed_frames}",
        severity=severity,
        class_name=obs.class_name,
        confidence=obs.confidence,
        age=obs.age,
        missed_frames=obs.missed_frames,
        bbox=obs.bbox,
    )


def possible_id_switch_events(
    new_tracks: Iterable[TrackObservation],
    recently_lost_tracks: Iterable[TrackObservation],
    max_center_distance_px: float,
) -> List[TrackEvent]:
    events: List[TrackEvent] = []

    for new_obs in new_tracks:
        if new_obs.age > 1:
            continue

        best_lost: Optional[TrackObservation] = None
        best_dist = max_center_distance_px

        for lost_obs in recently_lost_tracks:
            if lost_obs.track_id == new_obs.track_id:
                continue
            if lost_obs.class_name and new_obs.class_name and lost_obs.class_name != new_obs.class_name:
                continue

            dist = _center_distance(new_obs.bbox, lost_obs.bbox)
            if dist <= best_dist:
                best_dist = dist
                best_lost = lost_obs

        if best_lost is None:
            continue

        severity = max(0.2, 1.0 - best_dist / max(1.0, max_center_distance_px))
        events.append(
            TrackEvent(
                event_type="possible_id_switch",
                track_id=new_obs.track_id,
                related_track_id=best_lost.track_id,
                stamp_sec=new_obs.stamp_sec,
                frame_index=new_obs.frame_index,
                reason=f"new track_id={new_obs.track_id} appeared near recently lost track_id={best_lost.track_id}",
                severity=severity,
                class_name=new_obs.class_name,
                confidence=new_obs.confidence,
                age=new_obs.age,
                missed_frames=new_obs.missed_frames,
                bbox=new_obs.bbox,
            )
        )

    return events
