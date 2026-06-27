import cv2


def apply_blur(image, *, blur_kernel: int):
    kernel = max(1, int(blur_kernel))

    if kernel % 2 == 0:
        kernel += 1

    if kernel <= 1:
        return image

    return cv2.GaussianBlur(image, (kernel, kernel), 0)
