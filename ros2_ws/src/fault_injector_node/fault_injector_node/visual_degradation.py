from fault_injector_node.blur import apply_blur
from fault_injector_node.compression import apply_jpeg_compression
from fault_injector_node.glare import apply_brightness_contrast, apply_glare
from fault_injector_node.noise import NoiseGenerator


class VisualDegradationPipeline:
    def __init__(
        self,
        *,
        visual_mode: str,
        blur_kernel: int,
        jpeg_quality: int,
        brightness_delta: float,
        contrast_alpha: float,
        glare_enabled: bool,
        glare_strength: float,
        noise_sigma: float,
        deterministic: bool,
        random_seed: int,
    ):
        self.visual_mode = str(visual_mode)
        self.blur_kernel = int(blur_kernel)
        self.jpeg_quality = int(jpeg_quality)
        self.brightness_delta = float(brightness_delta)
        self.contrast_alpha = float(contrast_alpha)
        self.glare_enabled = bool(glare_enabled)
        self.glare_strength = float(glare_strength)
        self.noise_sigma = float(noise_sigma)
        self.noise = NoiseGenerator(
            deterministic=deterministic,
            random_seed=random_seed,
        )

    def apply(self, image):
        output = image

        if self.visual_mode in ("blur", "combined"):
            output = apply_blur(output, blur_kernel=self.blur_kernel)

        if self.visual_mode in ("compression", "combined"):
            output = apply_jpeg_compression(output, jpeg_quality=self.jpeg_quality)

        if self.visual_mode in ("brightness_contrast", "glare", "combined"):
            output = apply_brightness_contrast(
                output,
                brightness_delta=self.brightness_delta,
                contrast_alpha=self.contrast_alpha,
            )

        if self.visual_mode in ("glare", "combined") and self.glare_enabled:
            output = apply_glare(output, glare_strength=self.glare_strength)

        if self.visual_mode in ("noise", "combined"):
            output = self.noise.apply_noise(output, noise_sigma=self.noise_sigma)

        return output
