from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class FusionState:
    visual_confidence: float
    visual_degraded: bool
    acoustic_score: float
    acoustic_threshold: float
    acoustic_active: bool
    fusion_status: str


def compute_fusion_state(
    *,
    visual_confidence: float,
    visual_degraded: bool,
    acoustic_score: float,
    acoustic_threshold: float,
) -> FusionState:
    acoustic_active = acoustic_score >= acoustic_threshold if acoustic_threshold > 0 else acoustic_score > 0

    if visual_degraded and acoustic_active:
        status = "track_supported"
    elif visual_degraded and not acoustic_active:
        status = "visual_degraded_no_acoustic_support"
    elif acoustic_active:
        status = "visual_track_with_acoustic_context"
    else:
        status = "visual_only"

    return FusionState(
        visual_confidence=float(visual_confidence),
        visual_degraded=bool(visual_degraded),
        acoustic_score=float(acoustic_score),
        acoustic_threshold=float(acoustic_threshold),
        acoustic_active=bool(acoustic_active),
        fusion_status=status,
    )
