from dataclasses import dataclass

from sensor_msgs.msg import RegionOfInterest


@dataclass(frozen=True)
class WaterRoi:
    x_offset: int
    y_offset: int
    width: int
    height: int

    @property
    def x_min(self) -> int:
        return self.x_offset

    @property
    def y_min(self) -> int:
        return self.y_offset

    @property
    def x_max(self) -> int:
        return self.x_offset + self.width

    @property
    def y_max(self) -> int:
        return self.y_offset + self.height

    def to_msg(self) -> RegionOfInterest:
        msg = RegionOfInterest()
        msg.x_offset = int(self.x_offset)
        msg.y_offset = int(self.y_offset)
        msg.width = int(self.width)
        msg.height = int(self.height)
        msg.do_rectify = False
        return msg


def compute_heuristic_water_roi(
    *,
    image_width: int,
    image_height: int,
    valid_y_min_ratio: float,
    valid_y_max_ratio: float,
) -> WaterRoi:
    y_min_ratio = min(max(float(valid_y_min_ratio), 0.0), 1.0)
    y_max_ratio = min(max(float(valid_y_max_ratio), 0.0), 1.0)

    if y_max_ratio < y_min_ratio:
        y_min_ratio, y_max_ratio = y_max_ratio, y_min_ratio

    y_min = int(round(image_height * y_min_ratio))
    y_max = int(round(image_height * y_max_ratio))

    y_min = min(max(y_min, 0), image_height)
    y_max = min(max(y_max, y_min), image_height)

    return WaterRoi(
        x_offset=0,
        y_offset=y_min,
        width=int(image_width),
        height=int(y_max - y_min),
    )
