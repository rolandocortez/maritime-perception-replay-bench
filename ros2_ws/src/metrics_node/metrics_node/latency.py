def stamp_to_sec(stamp) -> float:
    return float(stamp.sec) + float(stamp.nanosec) * 1e-9


def header_stamp_to_sec(header) -> float:
    return stamp_to_sec(header.stamp)


def clock_now_sec(clock) -> float:
    return stamp_to_sec(clock.now().to_msg())


def latency_ms_from_header(clock, header, *, max_reasonable_latency_sec: float) -> float | None:
    stamp_sec = header_stamp_to_sec(header)

    if stamp_sec <= 0.0:
        return None

    now_sec = clock_now_sec(clock)
    delta_sec = now_sec - stamp_sec

    if delta_sec < 0.0:
        return None

    if delta_sec > float(max_reasonable_latency_sec):
        return None

    return float(delta_sec * 1000.0)
