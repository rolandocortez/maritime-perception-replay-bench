from dataclasses import dataclass


@dataclass(frozen=True)
class TemporalAssociation:
    delta_sec: float
    within_window: bool


def within_temporal_window(
    *,
    visual_stamp_sec: float,
    acoustic_stamp_sec: float,
    association_window_sec: float,
) -> TemporalAssociation:
    delta_sec = abs(float(visual_stamp_sec) - float(acoustic_stamp_sec))

    return TemporalAssociation(
        delta_sec=delta_sec,
        within_window=delta_sec <= float(association_window_sec),
    )


def fuse_confidence(
    *,
    visual_confidence: float,
    acoustic_confidence: float,
    has_visual_track: bool,
    has_acoustic_event: bool,
) -> float:
    if has_visual_track and has_acoustic_event:
        return float(max(0.0, min(1.0, 0.5 * visual_confidence + 0.5 * acoustic_confidence)))

    if has_visual_track:
        return float(max(0.0, min(1.0, 0.5 * visual_confidence)))

    if has_acoustic_event:
        return float(max(0.0, min(1.0, 0.5 * acoustic_confidence)))

    return 0.0
