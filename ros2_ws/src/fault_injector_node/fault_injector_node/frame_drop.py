import random


class FrameDropPolicy:
    def __init__(
        self,
        *,
        drop_probability: float,
        deterministic: bool,
        random_seed: int,
    ):
        self.drop_probability = max(0.0, min(1.0, float(drop_probability)))
        self.deterministic = bool(deterministic)
        self.random_seed = int(random_seed)

        self._rng = random.Random(self.random_seed) if self.deterministic else random.Random()

    def should_drop(self, frame_index: int) -> bool:
        if self.drop_probability <= 0.0:
            return False

        if self.drop_probability >= 1.0:
            return True

        return self._rng.random() < self.drop_probability
