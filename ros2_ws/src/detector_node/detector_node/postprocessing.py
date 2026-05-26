from dataclasses import asdict, dataclass
import json


@dataclass
class DetectionRecord:
    class_id: int
    class_name: str
    confidence: float
    x_min: float
    y_min: float
    x_max: float
    y_max: float

    @property
    def width(self):
        return self.x_max - self.x_min

    @property
    def height(self):
        return self.y_max - self.y_min

    @property
    def center_x(self):
        return self.x_min + self.width / 2.0

    @property
    def center_y(self):
        return self.y_min + self.height / 2.0


def detections_to_json(
    *,
    frame_index,
    frame_stamp_sec,
    inference_ms,
    model_backend,
    model_name,
    detections,
):
    payload = {
        "frame_index": frame_index,
        "frame_stamp_sec": frame_stamp_sec,
        "inference_ms": inference_ms,
        "model_backend": model_backend,
        "model_name": model_name,
        "num_detections": len(detections),
        "detections": [asdict(det) for det in detections],
    }
    return json.dumps(payload, sort_keys=True)
