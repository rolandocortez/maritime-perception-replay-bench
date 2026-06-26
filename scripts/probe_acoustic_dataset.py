#!/usr/bin/env python3
import argparse
import json
from pathlib import Path
import wave

import numpy as np


def pcm24_to_int32(raw: bytes) -> np.ndarray:
    data = np.frombuffer(raw, dtype=np.uint8)

    if len(data) % 3 != 0:
        raise ValueError("24-bit PCM byte stream length is not divisible by 3")

    triples = data.reshape(-1, 3).astype(np.int32)
    values = triples[:, 0] | (triples[:, 1] << 8) | (triples[:, 2] << 16)

    sign_bit = 1 << 23
    values = (values ^ sign_bit) - sign_bit

    return values.astype(np.int32)


def read_wav(path: Path):
    with wave.open(str(path), "rb") as wav:
        channels = wav.getnchannels()
        sample_rate = wav.getframerate()
        sample_width = wav.getsampwidth()
        frames = wav.getnframes()
        raw = wav.readframes(frames)

    if sample_width == 1:
        dtype = "uint8_pcm"
        audio = np.frombuffer(raw, dtype=np.uint8).astype(np.float32)
        audio = (audio - 128.0) / 128.0
    elif sample_width == 2:
        dtype = "int16_pcm"
        audio = np.frombuffer(raw, dtype="<i2").astype(np.float32)
        audio = audio / 32768.0
    elif sample_width == 3:
        dtype = "int24_pcm"
        audio = pcm24_to_int32(raw).astype(np.float32)
        audio = audio / float(1 << 23)
    elif sample_width == 4:
        dtype = "int32_pcm"
        audio = np.frombuffer(raw, dtype="<i4").astype(np.float32)
        audio = audio / float(1 << 31)
    else:
        raise ValueError(f"Unsupported WAV sample width: {sample_width} bytes")

    if channels > 0:
        audio = audio.reshape(-1, channels)

    duration_sec = frames / float(sample_rate) if sample_rate else 0.0

    rms = float(np.sqrt(np.mean(np.square(audio)))) if audio.size else 0.0
    peak = float(np.max(np.abs(audio))) if audio.size else 0.0

    return {
        "path": str(path),
        "sample_rate": int(sample_rate),
        "duration_sec": duration_sec,
        "channels": int(channels),
        "sample_width_bytes": int(sample_width),
        "dtype": dtype,
        "frames": int(frames),
        "rms_energy": rms,
        "peak_amplitude": peak,
    }


def parse_args():
    parser = argparse.ArgumentParser(
        description="Probe a local WAV file for acoustic-lane metadata and simple energy stats."
    )

    parser.add_argument("--input", required=True, help="Path to WAV file.")
    parser.add_argument("--json", action="store_true", help="Print JSON output.")

    return parser.parse_args()


def main():
    args = parse_args()
    path = Path(args.input)

    if not path.exists():
        raise SystemExit(f"Input WAV does not exist: {path}")

    result = read_wav(path)

    if args.json:
        print(json.dumps(result, indent=2))
        return

    for key, value in result.items():
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
