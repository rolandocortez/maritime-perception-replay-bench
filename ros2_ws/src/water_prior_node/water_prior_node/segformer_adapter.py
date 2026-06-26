class SegFormerWaterPriorAdapter:
    """Optional future adapter for learned maritime water-region segmentation.

    The stable H17 path uses a deterministic heuristic ROI:
        valid_y_min_ratio <= y / image_height <= valid_y_max_ratio

    This adapter documents where a learned segmentation prior could plug in
    without changing downstream ROS2 topics.

    Intended future responsibilities:
      - load a lightweight SegFormer-style semantic segmentation model;
      - infer water / sky / obstacle masks;
      - convert the water mask into a RegionOfInterest or binary mask;
      - preserve /maritime/filtered_detections and /debug/water_prior_overlay.

    This file deliberately does not import torch, transformers, or other heavy
    frameworks. Those dependencies belong in optional analysis/runtime profiles,
    not in the default demo path.
    """

    def __init__(self, model_name: str = "", device: str = "cpu"):
        self.model_name = model_name
        self.device = device

    def is_available(self) -> bool:
        return False

    def predict_water_mask(self, image_bgr):
        raise NotImplementedError(
            "SegFormer water prior is a future extension. "
            "Use water_prior_node mode='heuristic' for the current pipeline."
        )

    def mask_to_roi(self, mask):
        raise NotImplementedError(
            "Mask-to-ROI conversion is not implemented yet."
        )
