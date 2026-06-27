import numpy as np


class NoiseGenerator:
    def __init__(self, *, deterministic: bool, random_seed: int):
        self.rng = np.random.default_rng(int(random_seed) if deterministic else None)

    def apply_noise(self, image, *, noise_sigma: float):
        sigma = max(0.0, float(noise_sigma))

        if sigma <= 0.0:
            return image

        noise = self.rng.normal(0.0, sigma, image.shape)
        degraded = image.astype(np.float32) + noise

        return np.clip(degraded, 0, 255).astype(np.uint8)
