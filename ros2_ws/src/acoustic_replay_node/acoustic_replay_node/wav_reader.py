from dataclasses import dataclass
from pathlib import Path
import wave

import numpy as np


@dataclass(frozen=True)
class WavAudio:
    sample_rate: int
    samples: np.ndarray
    channels: int
    duration_sec: float
    source_path: str


def _pcm24_to_int32(raw: bytes) -> np.ndarray:
    data = np.frombuffer(raw, dtype=np.uint8)

    if len(data) % 3 != 0:
        raise ValueError("24-bit PCM byte stream length is not divisible by 3")

    triples = data.reshape(-1, 3).astype(np.int32)
    values = triples[:, 0] | (triples[:, 1] << 8) | (triples[:, 2] << 16)

    sign_bit = 1 << 23
    values = (values ^ sign_bit) - sign_bit

    return values.astype(np.int32)


def read_wav_mono(path: str | Path, *, normalize: bool = True) -> WavAudio:
    wav_path = Path(path)

    with wave.open(str(wav_path), "rb") as wav:
        channels = wav.getnchannels()
        sample_rate = wav.getframerate()
        sample_width = wav.getsampwidth()
        frames = wav.getnframes()
        raw = wav.readframes(frames)

    if sample_width == 1:
        audio = np.frombuffer(raw, dtype=np.uint8).astype(np.float32)
        audio = (audio - 128.0) / 128.0
    elif sample_width == 2:
        audio = np.frombuffer(raw, dtype="<i2").astype(np.float32)
        audio = audio / 32768.0
    elif sample_width == 3:
        audio = _pcm24_to_int32(raw).astype(np.float32)
        audio = audio / float(1 << 23)
    elif sample_width == 4:
        audio = np.frombuffer(raw, dtype="<i4").astype(np.float32)
        audio = audio / float(1 << 31)
    else:
        raise ValueError(f"Unsupported WAV sample width: {sample_width} bytes")

    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)
    else:
        audio = audio.reshape(-1)

    if normalize and audio.size:
        peak = float(np.max(np.abs(audio)))
        if peak > 0:
            audio = audio / peak

    return WavAudio(
        sample_rate=int(sample_rate),
        samples=audio.astype(np.float32),
        channels=1,
        duration_sec=float(frames) / float(sample_rate) if sample_rate else 0.0,
        source_path=str(wav_path),
    )
