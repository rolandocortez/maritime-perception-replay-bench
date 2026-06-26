import json
from dataclasses import asdict, dataclass


@dataclass
class FaultInjectionStatus:
    mode: str
    input_frames: int
    forwarded_frames: int
    dropped_frames: int
    drop_probability: float
    observed_drop_ratio: float
    deterministic: bool
    random_seed: int
    last_frame_dropped: bool
    input_topic: str
    output_topic: str


def make_status_json(status: FaultInjectionStatus) -> str:
    return json.dumps(asdict(status), sort_keys=True)
