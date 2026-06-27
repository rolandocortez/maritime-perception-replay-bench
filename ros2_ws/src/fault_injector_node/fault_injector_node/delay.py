import heapq
import random
from dataclasses import dataclass, field
from typing import Any


@dataclass(order=True)
class DelayedMessage:
    release_time_sec: float
    sequence: int
    msg: Any = field(compare=False)
    applied_delay_ms: float = field(compare=False)


class DelayPolicy:
    def __init__(
        self,
        *,
        delay_ms: float,
        jitter_ms: float,
        deterministic: bool,
        random_seed: int,
    ):
        self.delay_ms = max(0.0, float(delay_ms))
        self.jitter_ms = max(0.0, float(jitter_ms))
        self._rng = random.Random(int(random_seed)) if deterministic else random.Random()

    def sample_delay_ms(self) -> float:
        if self.jitter_ms <= 0.0:
            return self.delay_ms

        jitter = self._rng.uniform(-self.jitter_ms, self.jitter_ms)
        return max(0.0, self.delay_ms + jitter)


class DelayQueue:
    def __init__(self, *, max_queue_size: int):
        self.max_queue_size = max(1, int(max_queue_size))
        self._heap = []
        self._sequence = 0
        self.dropped_due_to_queue = 0

    def push(self, *, msg, now_sec: float, delay_ms: float) -> float:
        self._sequence += 1
        release_time_sec = float(now_sec) + float(delay_ms) / 1000.0

        item = DelayedMessage(
            release_time_sec=release_time_sec,
            sequence=self._sequence,
            msg=msg,
            applied_delay_ms=float(delay_ms),
        )

        heapq.heappush(self._heap, item)

        while len(self._heap) > self.max_queue_size:
            heapq.heappop(self._heap)
            self.dropped_due_to_queue += 1

        return float(delay_ms)

    def pop_due(self, *, now_sec: float):
        if not self._heap:
            return None

        if self._heap[0].release_time_sec > float(now_sec):
            return None

        return heapq.heappop(self._heap)

    def __len__(self):
        return len(self._heap)
