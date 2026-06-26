from collections import deque


class QueueDelayEstimator:
    def __init__(self, maxlen: int):
        self.samples_ms = deque(maxlen=max(5, int(maxlen)))

    def estimate_delay_ms(self, observed_latency_ms: float) -> float:
        observed = float(max(0.0, observed_latency_ms))

        if len(self.samples_ms) < 5:
            self.samples_ms.append(observed)
            return 0.0

        baseline = min(self.samples_ms)
        self.samples_ms.append(observed)

        return float(max(0.0, observed - baseline))


class ArrivalGapDiagnostics:
    def __init__(self):
        self.last_receive_sec = None

    def update(self, receive_sec: float) -> float:
        now = float(receive_sec)

        if self.last_receive_sec is None:
            self.last_receive_sec = now
            return 0.0

        gap_sec = max(0.0, now - self.last_receive_sec)
        self.last_receive_sec = now
        return float(gap_sec)
