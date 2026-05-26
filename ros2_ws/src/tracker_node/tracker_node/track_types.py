from dataclasses import dataclass


@dataclass(frozen=True)
class DetectionInput:
    class_name: str
    confidence: float
    center_x: float
    center_y: float
    width: float
    height: float


@dataclass
class TrackState:
    track_id: int
    class_name: str
    confidence: float
    center_x: float
    center_y: float
    width: float
    height: float
    velocity_x: float = 0.0
    velocity_y: float = 0.0
    age: int = 1
    hits: int = 1
    missed_frames: int = 0

    @property
    def x1(self) -> float:
        return self.center_x - self.width / 2.0

    @property
    def y1(self) -> float:
        return self.center_y - self.height / 2.0

    @property
    def x2(self) -> float:
        return self.center_x + self.width / 2.0

    @property
    def y2(self) -> float:
        return self.center_y + self.height / 2.0

    def update(self, detection: DetectionInput) -> None:
        old_center_x = self.center_x
        old_center_y = self.center_y

        self.class_name = detection.class_name
        self.confidence = detection.confidence
        self.center_x = detection.center_x
        self.center_y = detection.center_y
        self.width = detection.width
        self.height = detection.height
        self.velocity_x = self.center_x - old_center_x
        self.velocity_y = self.center_y - old_center_y
        self.age += 1
        self.hits += 1
        self.missed_frames = 0

    def mark_missed(self) -> None:
        self.age += 1
        self.missed_frames += 1
