class SegmentationAdapter:
    """Placeholder for a future learned water/sky/obstacle segmentation prior.

    H17 starts with a deterministic heuristic ROI. This adapter exists so the
    node architecture can later support MaSTr1325/LaRS/SegFormer-style water
    masks without changing downstream topics.
    """

    def __init__(self, *args, **kwargs):
        raise NotImplementedError(
            "Segmentation mode is not implemented yet. Use mode='heuristic'."
        )
