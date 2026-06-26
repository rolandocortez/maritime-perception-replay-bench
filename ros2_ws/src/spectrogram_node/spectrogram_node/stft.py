from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class SpectrogramResult:
    magnitude: np.ndarray
    magnitude_db: np.ndarray
    image_mono8: np.ndarray
    freqs_hz: np.ndarray
    times_sec: np.ndarray
    dominant_frequency_hz: float


def compute_spectrogram(
    samples: np.ndarray,
    *,
    sample_rate: float,
    n_fft: int,
    hop_length: int,
    dynamic_range_db: float = 80.0,
) -> SpectrogramResult:
    if n_fft <= 0:
        raise ValueError("n_fft must be > 0")

    if hop_length <= 0:
        raise ValueError("hop_length must be > 0")

    audio = np.asarray(samples, dtype=np.float32).reshape(-1)

    if audio.size == 0:
        audio = np.zeros(n_fft, dtype=np.float32)

    if audio.size < n_fft:
        audio = np.pad(audio, (0, n_fft - audio.size))

    starts = list(range(0, max(1, audio.size - n_fft + 1), hop_length))

    if not starts:
        starts = [0]

    window = np.hanning(n_fft).astype(np.float32)
    frames = []

    for start in starts:
        frame = audio[start:start + n_fft]

        if frame.size < n_fft:
            frame = np.pad(frame, (0, n_fft - frame.size))

        frames.append(frame * window)

    frame_matrix = np.stack(frames, axis=0)
    spectrum = np.fft.rfft(frame_matrix, n=n_fft, axis=1)
    magnitude = np.abs(spectrum).astype(np.float32).T

    magnitude_db = 20.0 * np.log10(magnitude + 1e-8)
    max_db = float(np.max(magnitude_db)) if magnitude_db.size else 0.0
    min_db = max_db - float(dynamic_range_db)

    normalized = (magnitude_db - min_db) / max(float(dynamic_range_db), 1e-6)
    image = np.clip(normalized * 255.0, 0.0, 255.0).astype(np.uint8)

    # Put low frequencies near the bottom when visualized as an image.
    image = np.flipud(image)

    freqs_hz = np.fft.rfftfreq(n_fft, d=1.0 / float(sample_rate)).astype(np.float32)
    times_sec = (np.asarray(starts, dtype=np.float32) / float(sample_rate)).astype(np.float32)

    if magnitude.size:
        mean_by_freq = np.mean(magnitude, axis=1)
        dominant_idx = int(np.argmax(mean_by_freq))
        dominant_frequency_hz = float(freqs_hz[dominant_idx])
    else:
        dominant_frequency_hz = 0.0

    return SpectrogramResult(
        magnitude=magnitude,
        magnitude_db=magnitude_db,
        image_mono8=image,
        freqs_hz=freqs_hz,
        times_sec=times_sec,
        dominant_frequency_hz=dominant_frequency_hz,
    )


def low_frequency_band_energy(
    magnitude: np.ndarray,
    freqs_hz: np.ndarray,
    *,
    max_frequency_hz: float,
) -> float:
    if magnitude.size == 0 or freqs_hz.size == 0:
        return 0.0

    mask = freqs_hz <= float(max_frequency_hz)

    if not np.any(mask):
        return 0.0

    return float(np.mean(magnitude[mask, :]))
