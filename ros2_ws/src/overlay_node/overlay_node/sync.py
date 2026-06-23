def stamp_to_sec(stamp) -> float:
    return float(stamp.sec) + float(stamp.nanosec) * 1e-9


def message_delta_ms(image_stamp, message_stamp) -> float:
    return abs(stamp_to_sec(image_stamp) - stamp_to_sec(message_stamp)) * 1000.0


def is_within_sync_threshold(image_stamp, message_stamp, max_sync_delta_ms: float) -> bool:
    return message_delta_ms(image_stamp, message_stamp) <= float(max_sync_delta_ms)
