from sensor_msgs.msg import Image
import numpy as np


SUPPORTED_COLOR_ENCODINGS = {"bgr8": 3, "rgb8": 3}
SUPPORTED_MONO_ENCODINGS = {"mono8": 1}


def image_to_array(msg: Image):
    encoding = msg.encoding.lower()

    if encoding in SUPPORTED_COLOR_ENCODINGS:
        channels = SUPPORTED_COLOR_ENCODINGS[encoding]
        array = np.frombuffer(msg.data, dtype=np.uint8).reshape(
            msg.height,
            msg.width,
            channels,
        )
        return array.copy(), encoding

    if encoding in SUPPORTED_MONO_ENCODINGS:
        array = np.frombuffer(msg.data, dtype=np.uint8).reshape(
            msg.height,
            msg.width,
        )
        return array.copy(), encoding

    raise ValueError(f"Unsupported image encoding for visual degradation: {msg.encoding}")


def array_to_image(array, original_msg: Image) -> Image:
    output = Image()
    output.header = original_msg.header
    output.height = original_msg.height
    output.width = original_msg.width
    output.encoding = original_msg.encoding
    output.is_bigendian = original_msg.is_bigendian
    output.step = int(array.strides[0])
    output.data = array.astype(np.uint8).tobytes()
    return output
