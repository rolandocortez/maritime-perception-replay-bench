from __future__ import annotations

from pathlib import Path
import wave

import numpy as np


def _pcm24le_to_float32(raw: bytes) -> np.ndarray:
    data = np.frombuffer(raw, dtype=np.uint8)
    if len(data) % 3 != 0:
        data = data[: len(data) - (len(data) % 3)]
    data = data.reshape(-1, 3)
    values = (
        data[:, 0].astype(np.int32)
        | (data[:, 1].astype(np.int32) << 8)
        | (data[:, 2].astype(np.int32) << 16)
    )
    sign_bit = 1 << 23
    values = np.where(values & sign_bit, values | ~0xFFFFFF, values)
    return values.astype(np.float32) / float(1 << 23)


def read_wav_float32(path: str | Path) -> tuple[np.ndarray, int, int]:
    with wave.open(str(path), "rb") as wf:
        channels = wf.getnchannels()
        sample_rate = wf.getframerate()
        sample_width = wf.getsampwidth()
        raw = wf.readframes(wf.getnframes())

    if sample_width == 1:
        audio = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    elif sample_width == 2:
        audio = np.frombuffer(raw, dtype="<i2").astype(np.float32) / float(1 << 15)
    elif sample_width == 3:
        audio = _pcm24le_to_float32(raw)
    elif sample_width == 4:
        audio = np.frombuffer(raw, dtype="<i4").astype(np.float32) / float(1 << 31)
    else:
        raise ValueError(f"unsupported WAV sample width: {sample_width}")

    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)

    return audio.astype(np.float32), int(sample_rate), int(channels)


def slice_window(audio: np.ndarray, sample_rate: int, start_sec: float, duration_sec: float) -> np.ndarray:
    start = max(0, int(start_sec * sample_rate))
    end = min(len(audio), start + max(1, int(duration_sec * sample_rate)))
    if end <= start:
        return np.zeros(1, dtype=np.float32)
    return audio[start:end]


def rms_energy(window: np.ndarray) -> float:
    if window.size == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(window.astype(np.float32)))))


def downsample_for_message(window: np.ndarray, max_points: int = 512) -> list[float]:
    if window.size == 0:
        return []
    if window.size <= max_points:
        return window.astype(float).tolist()
    idx = np.linspace(0, window.size - 1, max_points).astype(np.int64)
    return window[idx].astype(float).tolist()


def estimate_activity_threshold(
    audio: np.ndarray,
    sample_rate: int,
    window_sec: float,
    start_sec: float,
    end_sec: float,
) -> float:
    if end_sec <= start_sec:
        end_sec = len(audio) / float(sample_rate)

    step = max(window_sec, 0.05)
    values: list[float] = []
    t = start_sec
    while t < end_sec:
        values.append(rms_energy(slice_window(audio, sample_rate, t, window_sec)))
        t += step

    if not values:
        return 0.0

    arr = np.array(values, dtype=np.float32)
    return float(max(np.median(arr) * 0.75, 1e-6))
