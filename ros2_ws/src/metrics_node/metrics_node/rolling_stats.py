from collections import deque
from typing import Iterable


class RollingValues:
    def __init__(self, maxlen: int):
        self.values = deque(maxlen=max(1, int(maxlen)))

    def add(self, value: float):
        self.values.append(float(value))

    def clear(self):
        self.values.clear()

    def __len__(self):
        return len(self.values)

    def as_list(self) -> list[float]:
        return list(self.values)

    def mean(self) -> float:
        if not self.values:
            return 0.0
        return float(sum(self.values) / len(self.values))

    def total(self) -> float:
        return float(sum(self.values))

    def last(self, default: float = 0.0) -> float:
        if not self.values:
            return float(default)
        return float(self.values[-1])

    def percentile(self, percentile: float) -> float:
        if not self.values:
            return 0.0

        ordered = sorted(self.values)
        p = max(0.0, min(100.0, float(percentile)))
        k = (len(ordered) - 1) * (p / 100.0)
        lower = int(k)
        upper = min(lower + 1, len(ordered) - 1)
        weight = k - lower

        return float(ordered[lower] * (1.0 - weight) + ordered[upper] * weight)


class RollingTimestamps:
    def __init__(self, maxlen: int):
        self.times = deque(maxlen=max(2, int(maxlen)))

    def add(self, stamp_sec: float):
        self.times.append(float(stamp_sec))

    def __len__(self):
        return len(self.times)

    def rate_hz(self) -> float:
        if len(self.times) < 2:
            return 0.0

        duration = self.times[-1] - self.times[0]

        if duration <= 0.0:
            return 0.0

        return float((len(self.times) - 1) / duration)


def count_items(container: Iterable | None) -> int:
    if container is None:
        return 0

    try:
        return len(container)
    except TypeError:
        return sum(1 for _ in container)
