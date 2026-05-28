import time

from detector_node.postprocessing import DetectionRecord
from detector_node.preprocessing import ensure_bgr8_contiguous


class YoloModelRunner:
    def __init__(
        self,
        *,
        model_name,
        device,
        confidence_threshold,
        iou_threshold,
        max_detections,
        class_filter_enabled,
        class_filter_names,
    ):
        try:
            from ultralytics import YOLO
        except ImportError as exc:
            raise RuntimeError(
                "Ultralytics is not installed. Install it with: "
                "python3 -m pip install --user --break-system-packages ultralytics"
            ) from exc

        self.model_name = model_name
        self.device = device
        self.confidence_threshold = confidence_threshold
        self.iou_threshold = iou_threshold
        self.max_detections = max_detections
        self.class_filter_enabled = class_filter_enabled
        self.class_filter_names = set(class_filter_names or [])

        self.model = YOLO(model_name)
        self.names = getattr(self.model, "names", {}) or {}

    def infer(self, image_bgr):
        image_bgr = ensure_bgr8_contiguous(image_bgr)

        start = time.perf_counter()

        results = self.model.predict(
            source=image_bgr,
            conf=self.confidence_threshold,
            iou=self.iou_threshold,
            max_det=self.max_detections,
            device=self.device,
            verbose=False,
        )

        end = time.perf_counter()
        inference_ms = (end - start) * 1000.0

        detections = []

        if not results:
            return detections, inference_ms

        result = results[0]
        boxes = getattr(result, "boxes", None)

        if boxes is None:
            return detections, inference_ms

        for box in boxes:
            xyxy = box.xyxy[0].detach().cpu().numpy().tolist()
            confidence = float(box.conf[0].detach().cpu().item())
            class_id = int(box.cls[0].detach().cpu().item())
            class_name = str(self.names.get(class_id, str(class_id)))

            if self.class_filter_enabled and class_name not in self.class_filter_names:
                continue

            detections.append(
                DetectionRecord(
                    class_id=class_id,
                    class_name=class_name,
                    confidence=confidence,
                    x_min=float(xyxy[0]),
                    y_min=float(xyxy[1]),
                    x_max=float(xyxy[2]),
                    y_max=float(xyxy[3]),
                )
            )

        return detections, inference_ms
