class ByteTrackAdapter:
    """Placeholder for a future ByteTrack integration.

    H15 intentionally starts with a small IoU tracker because it is deterministic,
    easy to debug, and has no extra heavy dependency.
    """

    def __init__(self, *args, **kwargs):
        raise NotImplementedError(
            "ByteTrack adapter is not implemented yet. Use tracker_type='iou'."
        )
