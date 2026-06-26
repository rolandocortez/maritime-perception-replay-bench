import cv2


def apply_jpeg_compression(image, *, jpeg_quality: int):
    quality = max(1, min(100, int(jpeg_quality)))

    ok, encoded = cv2.imencode(
        ".jpg",
        image,
        [int(cv2.IMWRITE_JPEG_QUALITY), quality],
    )

    if not ok:
        return image

    decoded = cv2.imdecode(encoded, cv2.IMREAD_UNCHANGED)

    if decoded is None:
        return image

    return decoded
