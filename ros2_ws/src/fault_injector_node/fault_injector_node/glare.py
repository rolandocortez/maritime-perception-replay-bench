import cv2
import numpy as np


def apply_brightness_contrast(image, *, brightness_delta: float, contrast_alpha: float):
    return cv2.convertScaleAbs(
        image,
        alpha=float(contrast_alpha),
        beta=float(brightness_delta),
    )


def apply_glare(image, *, glare_strength: float):
    strength = max(0.0, min(1.0, float(glare_strength)))

    if strength <= 0.0:
        return image

    h, w = image.shape[:2]
    center = (int(w * 0.72), int(h * 0.28))
    radius = max(8, int(min(w, h) * 0.28))

    overlay = image.copy()
    mask = np.zeros((h, w), dtype=np.uint8)
    cv2.circle(mask, center, radius, 255, -1)
    mask = cv2.GaussianBlur(mask, (0, 0), sigmaX=max(1.0, radius / 3.0))
    alpha = (mask.astype(np.float32) / 255.0) * strength

    if image.ndim == 3:
        alpha = alpha[:, :, None]
        glare_color = np.full_like(image, 255, dtype=np.uint8)
    else:
        glare_color = np.full_like(image, 255, dtype=np.uint8)

    blended = image.astype(np.float32) * (1.0 - alpha) + glare_color.astype(np.float32) * alpha

    return np.clip(blended, 0, 255).astype(np.uint8)
