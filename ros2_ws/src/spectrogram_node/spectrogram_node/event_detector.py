from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class AcousticEventCandidate:
    event_type: str
    confidence: float
    start_sec: float
    duration_sec: float
    energy: float
    dominant_frequency_hz: float


def rms_energy(samples: np.ndarray) -> float:
    audio = np.asarray(samples, dtype=np.float32).reshape(-1)

    if audio.size == 0:
        return 0.0

    return float(np.sqrt(np.mean(np.square(audio))))


def detect_event(
    samples: np.ndarray,
    *,
    event_method: str,
    energy_threshold: float,
    start_sec: float,
    duration_sec: float,
    min_event_duration_sec: float,
    dominant_frequency_hz: float,
    low_frequency_band_energy_value: float = 0.0,
    band_energy_threshold: float = 0.0,
) -> AcousticEventCandidate | None:
    if duration_sec < min_event_duration_sec:
        return None

    energy = rms_energy(samples)
    method = event_method.strip().lower()

    if method == "energy_threshold":
        if energy <= energy_threshold:
            return None

        confidence = min(1.0, energy / max(energy_threshold * 2.0, 1e-6))
        return AcousticEventCandidate(
            event_type="acoustic_event",
            confidence=float(confidence),
            start_sec=float(start_sec),
            duration_sec=float(duration_sec),
            energy=float(energy),
            dominant_frequency_hz=float(dominant_frequency_hz),
        )

    if method == "low_frequency_band":
        if low_frequency_band_energy_value <= band_energy_threshold:
            return None

        confidence = min(
            1.0,
            low_frequency_band_energy_value / max(band_energy_threshold * 2.0, 1e-6),
        )
        return AcousticEventCandidate(
            event_type="vessel_like_event_stub",
            confidence=float(confidence),
            start_sec=float(start_sec),
            duration_sec=float(duration_sec),
            energy=float(energy),
            dominant_frequency_hz=float(dominant_frequency_hz),
        )

    return None
