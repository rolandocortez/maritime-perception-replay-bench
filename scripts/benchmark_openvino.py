#!/usr/bin/env python3
import argparse
import csv
import statistics
import time
from pathlib import Path

import cv2
import numpy as np
import psutil


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def import_openvino_core():
    try:
        import openvino as ov
        return ov.Core()
    except Exception:
        from openvino.runtime import Core
        return Core()


def list_images(images_dir: Path):
    paths = sorted(
        p for p in images_dir.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
    )

    if not paths:
        raise FileNotFoundError(f"No image files found in {images_dir}")

    return paths


def static_dim(value, default):
    try:
        value = int(value)
        if value > 0:
            return value
    except Exception:
        pass

    return int(default)


def resolve_input_shape(input_port, default_size: int):
    shape = list(input_port.shape)

    if len(shape) != 4:
        raise ValueError(f"Unsupported OpenVINO input shape: {shape}")

    if int(shape[1]) in (1, 3):
        channels_first = True
        height = static_dim(shape[2], default_size)
        width = static_dim(shape[3], default_size)
    else:
        channels_first = False
        height = static_dim(shape[1], default_size)
        width = static_dim(shape[2], default_size)

    return {
        "shape": shape,
        "height": int(height),
        "width": int(width),
        "channels_first": channels_first,
    }


def preprocess_image(path: Path, *, height: int, width: int, channels_first: bool):
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)

    if image is None:
        raise ValueError(f"Could not read image: {path}")

    resized = cv2.resize(image, (width, height), interpolation=cv2.INTER_LINEAR)
    rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
    tensor = rgb.astype(np.float32) / 255.0

    if channels_first:
        tensor = np.transpose(tensor, (2, 0, 1))

    tensor = np.expand_dims(tensor, axis=0)
    return np.ascontiguousarray(tensor)


def percentile(values, pct):
    if not values:
        return 0.0

    return float(np.percentile(np.array(values, dtype=np.float64), pct))


def write_csv(path: Path, row: dict):
    path.parent.mkdir(parents=True, exist_ok=True)

    fields = [
        "runtime",
        "device",
        "model",
        "images",
        "image_count",
        "input_size",
        "input_height",
        "input_width",
        "warmup_iterations",
        "benchmark_iterations",
        "latency_ms_mean",
        "latency_ms_p50",
        "latency_ms_p95",
        "latency_ms_p99",
        "latency_ms_min",
        "latency_ms_max",
        "latency_ms_std",
        "throughput_fps",
        "cpu_percent",
        "memory_mb",
    ]

    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerow(row)


def write_markdown(path: Path, row: dict):
    path.parent.mkdir(parents=True, exist_ok=True)

    text = f"""# OpenVINO Benchmark

| Runtime | Device | Input size | p50 ms | p95 ms | FPS | CPU % | RAM MB |
|---|---|---:|---:|---:|---:|---:|---:|
| {row["runtime"]} | {row["device"]} | {row["input_size"]} | {row["latency_ms_p50"]:.3f} | {row["latency_ms_p95"]:.3f} | {row["throughput_fps"]:.3f} | {row["cpu_percent"]:.2f} | {row["memory_mb"]:.2f} |

## Run details

- Model: `{row["model"]}`
- Images: `{row["images"]}`
- Image count: `{row["image_count"]}`
- Device: `{row["device"]}`
- Warmup iterations: `{row["warmup_iterations"]}`
- Benchmark iterations: `{row["benchmark_iterations"]}`

## Notes

This benchmark measures OpenVINO compiled-model inference latency only. It does not include camera capture, ROS2 transport, detector post-processing, tracking, overlays, or operator display latency.
"""

    path.write_text(text, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Benchmark OpenVINO latency and throughput.")
    parser.add_argument("--model", required=True, help="Path to ONNX model.")
    parser.add_argument("--images", required=True, help="Directory with benchmark images.")
    parser.add_argument("--device", default="CPU", help="OpenVINO device, usually CPU.")
    parser.add_argument("--warmup", type=int, default=20, help="Warmup iterations.")
    parser.add_argument("--iterations", type=int, default=200, help="Benchmark iterations.")
    parser.add_argument("--input-size", type=int, default=640, help="Fallback input size.")
    parser.add_argument("--output", required=True, help="Output CSV path.")
    parser.add_argument("--report", default=None, help="Output Markdown report path.")
    args = parser.parse_args()

    model_path = Path(args.model)
    images_dir = Path(args.images)
    output_path = Path(args.output)
    report_path = Path(args.report) if args.report else output_path.with_name("openvino_benchmark.md")

    if not model_path.exists():
        raise FileNotFoundError(f"Missing model: {model_path}")

    if not images_dir.exists():
        raise FileNotFoundError(f"Missing images directory: {images_dir}")

    image_paths = list_images(images_dir)

    core = import_openvino_core()
    model = core.read_model(str(model_path))
    compiled_model = core.compile_model(model, args.device)
    input_port = compiled_model.input(0)
    input_spec = resolve_input_shape(input_port, args.input_size)
    infer_request = compiled_model.create_infer_request()

    input_name = input_port.any_name

    tensors = [
        preprocess_image(
            path,
            height=input_spec["height"],
            width=input_spec["width"],
            channels_first=input_spec["channels_first"],
        )
        for path in image_paths
    ]

    process = psutil.Process()

    print("runtime: OpenVINO")
    print(f"device: {args.device}")
    print(f"model: {model_path}")
    print(f"images: {images_dir} count={len(tensors)}")
    print(f"input: {input_spec['width']}x{input_spec['height']}")
    print(f"warmup_iterations: {args.warmup}")
    print(f"benchmark_iterations: {args.iterations}")

    for i in range(max(0, args.warmup)):
        tensor = tensors[i % len(tensors)]
        infer_request.infer({input_name: tensor})

    latency_ms = []
    max_rss_mb = process.memory_info().rss / (1024 * 1024)

    start_cpu = process.cpu_times()
    start_wall = time.perf_counter()

    for i in range(args.iterations):
        tensor = tensors[i % len(tensors)]

        t0 = time.perf_counter()
        infer_request.infer({input_name: tensor})
        t1 = time.perf_counter()

        latency_ms.append((t1 - t0) * 1000.0)

        rss_mb = process.memory_info().rss / (1024 * 1024)
        max_rss_mb = max(max_rss_mb, rss_mb)

    end_wall = time.perf_counter()
    end_cpu = process.cpu_times()

    elapsed_wall = max(1e-9, end_wall - start_wall)
    cpu_time = (end_cpu.user + end_cpu.system) - (start_cpu.user + start_cpu.system)

    cpu_percent = (cpu_time / elapsed_wall) * 100.0
    throughput_fps = args.iterations / elapsed_wall

    row = {
        "runtime": "OpenVINO",
        "device": args.device,
        "model": str(model_path),
        "images": str(images_dir),
        "image_count": len(tensors),
        "input_size": input_spec["width"],
        "input_height": input_spec["height"],
        "input_width": input_spec["width"],
        "warmup_iterations": args.warmup,
        "benchmark_iterations": args.iterations,
        "latency_ms_mean": round(float(statistics.mean(latency_ms)), 6),
        "latency_ms_p50": round(percentile(latency_ms, 50), 6),
        "latency_ms_p95": round(percentile(latency_ms, 95), 6),
        "latency_ms_p99": round(percentile(latency_ms, 99), 6),
        "latency_ms_min": round(float(min(latency_ms)), 6),
        "latency_ms_max": round(float(max(latency_ms)), 6),
        "latency_ms_std": round(float(statistics.pstdev(latency_ms)), 6),
        "throughput_fps": round(float(throughput_fps), 6),
        "cpu_percent": round(float(cpu_percent), 6),
        "memory_mb": round(float(max_rss_mb), 6),
    }

    write_csv(output_path, row)
    write_markdown(report_path, row)

    print(f"wrote {output_path}")
    print(f"wrote {report_path}")
    print(
        "summary: "
        f"mean={row['latency_ms_mean']:.3f}ms "
        f"p50={row['latency_ms_p50']:.3f}ms "
        f"p95={row['latency_ms_p95']:.3f}ms "
        f"p99={row['latency_ms_p99']:.3f}ms "
        f"fps={row['throughput_fps']:.3f}"
    )


if __name__ == "__main__":
    main()
