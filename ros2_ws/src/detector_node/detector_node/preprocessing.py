import numpy as np


def ensure_bgr8_contiguous(image):
    if image is None:
        raise ValueError("Input image is None")

    if len(image.shape) != 3 or image.shape[2] != 3:
        raise ValueError(f"Expected BGR image with shape HxWx3, got {image.shape}")

    return np.ascontiguousarray(image)
