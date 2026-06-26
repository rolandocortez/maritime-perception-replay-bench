from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class AudioWindow:
    samples: np.ndarray
    start_sample: int
    start_sec: float
    duration_sec: float


def slice_window(
    samples: np.ndarray,
    *,
    start_sample: int,
    window_samples: int,
    sample_rate: int,
    loop: bool,
) -> AudioWindow | None:
    if samples.size == 0:
        return None

    if start_sample >= samples.size:
        if not loop:
            return None
        start_sample = start_sample % samples.size

    end_sample = start_sample + window_samples

    if end_sample <= samples.size:
        window = samples[start_sample:end_sample]
    else:
        if not loop:
            window = samples[start_sample:samples.size]
        else:
            first = samples[start_sample:samples.size]
            remaining = end_sample - samples.size
            second = samples[: remaining % samples.size] if remaining > samples.size else samples[:remaining]
            window = np.concatenate([first, second])

    if window.size == 0:
        return None

    return AudioWindow(
        samples=window.astype(np.float32),
        start_sample=int(start_sample),
        start_sec=float(start_sample) / float(sample_rate),
        duration_sec=float(window.size) / float(sample_rate),
    )
