from dataclasses import dataclass


@dataclass(frozen=True)
class StageTiming:
    stage: str
    sensor_to_stage_ms: float
    stage_processing_ms: float
    estimated_queue_delay_ms: float
    timestamp_skew_ms: float


def make_stage_timing(
    *,
    stage: str,
    sensor_stamp_sec: float,
    stage_receive_sec: float,
    upstream_receive_sec: float | None,
    reference_sensor_stamp_sec: float | None,
    estimated_queue_delay_ms: float,
) -> StageTiming:
    sensor_to_stage_ms = 0.0
    if sensor_stamp_sec > 0.0 and stage_receive_sec >= sensor_stamp_sec:
        sensor_to_stage_ms = (stage_receive_sec - sensor_stamp_sec) * 1000.0

    stage_processing_ms = 0.0
    if upstream_receive_sec is not None and stage_receive_sec >= upstream_receive_sec:
        stage_processing_ms = (stage_receive_sec - upstream_receive_sec) * 1000.0

    timestamp_skew_ms = 0.0
    if reference_sensor_stamp_sec is not None and sensor_stamp_sec > 0.0:
        timestamp_skew_ms = (sensor_stamp_sec - reference_sensor_stamp_sec) * 1000.0

    return StageTiming(
        stage=str(stage),
        sensor_to_stage_ms=float(sensor_to_stage_ms),
        stage_processing_ms=float(stage_processing_ms),
        estimated_queue_delay_ms=float(max(0.0, estimated_queue_delay_ms)),
        timestamp_skew_ms=float(timestamp_skew_ms),
    )


def diagnostic_status(
    *,
    timing: StageTiming,
    warn_latency_ms: float,
    warn_skew_ms: float,
) -> str:
    problems = []

    if timing.sensor_to_stage_ms > warn_latency_ms:
        problems.append(f"latency>{warn_latency_ms:.1f}ms")

    if abs(timing.timestamp_skew_ms) > warn_skew_ms:
        problems.append(f"skew>{warn_skew_ms:.1f}ms")

    if timing.estimated_queue_delay_ms > warn_latency_ms:
        problems.append(f"queue>{warn_latency_ms:.1f}ms")

    if not problems:
        return "ok"

    return ",".join(problems)
