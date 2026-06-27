#!/usr/bin/env python3
import argparse
import csv
import statistics
import time
from pathlib import Path

import cv2
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import psutil
import torch
from ultralytics import YOLO


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def list_images(images_dir: Path):
    paths = sorted(
        p for p in images_dir.iterdir()
        if p.is_file() and p.suffix.lower() in IMAGE_EXTENSIONS
    )

    if not paths:
        raise FileNotFoundError(f"No image files found in {images_dir}")

    return paths


def percentile(values, pct):
    if not values:
        return 0.0

    return float(np.percentile(np.array(values, dtype=np.float64), pct))


def read_single_row_csv(path: Path):
    with path.open("r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    if not rows:
        raise ValueError(f"No rows found in {path}")

    return rows[0]


def preprocess_for_torch(path: Path, *, input_size: int):
    image = cv2.imread(str(path), cv2.IMREAD_COLOR)

    if image is None:
        raise ValueError(f"Could not read image: {path}")

    resized = cv2.resize(image, (input_size, input_size), interpolation=cv2.INTER_LINEAR)
    rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)
    tensor = rgb.astype(np.float32) / 255.0
    tensor = np.transpose(tensor, (2, 0, 1))
    tensor = np.expand_dims(tensor, axis=0)

    return torch.from_numpy(np.ascontiguousarray(tensor))


def benchmark_pytorch(model_path: Path, images_dir: Path, *, input_size: int, warmup: int, iterations: int):
    image_paths = list_images(images_dir)

    model = YOLO(str(model_path))
    torch_model = model.model
    torch_model.eval()
    torch_model.to("cpu")

    tensors = [
        preprocess_for_torch(path, input_size=input_size)
        for path in image_paths
    ]

    process = psutil.Process()

    print("runtime: PyTorch CPU")
    print(f"model: {model_path}")
    print(f"images: {images_dir} count={len(tensors)}")
    print(f"input: {input_size}x{input_size}")
    print(f"warmup_iterations: {warmup}")
    print(f"benchmark_iterations: {iterations}")

    with torch.no_grad():
        for i in range(max(0, warmup)):
            tensor = tensors[i % len(tensors)]
            _ = torch_model(tensor)

        latency_ms = []
        max_rss_mb = process.memory_info().rss / (1024 * 1024)

        start_cpu = process.cpu_times()
        start_wall = time.perf_counter()

        for i in range(iterations):
            tensor = tensors[i % len(tensors)]

            t0 = time.perf_counter()
            _ = torch_model(tensor)
            t1 = time.perf_counter()

            latency_ms.append((t1 - t0) * 1000.0)
            max_rss_mb = max(max_rss_mb, process.memory_info().rss / (1024 * 1024))

        end_wall = time.perf_counter()
        end_cpu = process.cpu_times()

    elapsed_wall = max(1e-9, end_wall - start_wall)
    cpu_time = (end_cpu.user + end_cpu.system) - (start_cpu.user + start_cpu.system)

    cpu_percent = (cpu_time / elapsed_wall) * 100.0
    throughput_fps = iterations / elapsed_wall

    return {
        "runtime": "PyTorch",
        "model": "YOLO baseline",
        "input_size": input_size,
        "latency_ms_mean": round(float(statistics.mean(latency_ms)), 6),
        "latency_ms_p50": round(percentile(latency_ms, 50), 6),
        "latency_ms_p95": round(percentile(latency_ms, 95), 6),
        "latency_ms_p99": round(percentile(latency_ms, 99), 6),
        "latency_ms_std": round(float(statistics.pstdev(latency_ms)), 6),
        "throughput_fps": round(float(throughput_fps), 6),
        "cpu_percent": round(float(cpu_percent), 6),
        "memory_mb": round(float(max_rss_mb), 6),
        "notes": "baseline forward pass",
    }


def row_from_runtime_csv(path: Path, *, runtime_label: str, model_label: str, notes: str):
    row = read_single_row_csv(path)

    return {
        "runtime": runtime_label,
        "model": model_label,
        "input_size": int(float(row.get("input_size", 640))),
        "latency_ms_mean": float(row["latency_ms_mean"]),
        "latency_ms_p50": float(row["latency_ms_p50"]),
        "latency_ms_p95": float(row["latency_ms_p95"]),
        "latency_ms_p99": float(row["latency_ms_p99"]),
        "latency_ms_std": float(row.get("latency_ms_std", 0.0)),
        "throughput_fps": float(row["throughput_fps"]),
        "cpu_percent": float(row.get("cpu_percent", 0.0)),
        "memory_mb": float(row.get("memory_mb", 0.0)),
        "notes": notes,
    }


def write_comparison_csv(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)

    fields = [
        "runtime",
        "model",
        "input_size",
        "latency_ms_mean",
        "latency_ms_p50",
        "latency_ms_p95",
        "latency_ms_p99",
        "latency_ms_std",
        "throughput_fps",
        "cpu_percent",
        "memory_mb",
        "notes",
    ]

    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def best_by(rows, key, reverse=False):
    return sorted(rows, key=lambda row: float(row[key]), reverse=reverse)[0]


def stability_score(row):
    return float(row["latency_ms_p95"]) - float(row["latency_ms_p50"])


def write_markdown(path: Path, rows):
    fastest_p95 = best_by(rows, "latency_ms_p95")
    fastest_fps = best_by(rows, "throughput_fps", reverse=True)
    most_stable = sorted(rows, key=stability_score)[0]

    lines = [
        "# Runtime Comparison",
        "",
        "| Runtime | Model | Input size | p50 ms | p95 ms | FPS | Notes |",
        "|---|---|---:|---:|---:|---:|---|",
    ]

    for row in rows:
        lines.append(
            f"| {row['runtime']} | {row['model']} | {row['input_size']} | "
            f"{float(row['latency_ms_p50']):.3f} | {float(row['latency_ms_p95']):.3f} | "
            f"{float(row['throughput_fps']):.3f} | {row['notes']} |"
        )

    lines.extend([
        "",
        "## Interpretation",
        "",
        f"**Which runtime was fastest?** By p95 latency, `{fastest_p95['runtime']}` was fastest in this run. By throughput, `{fastest_fps['runtime']}` had the highest FPS.",
        "",
        f"**Which runtime was most stable?** `{most_stable['runtime']}` had the smallest p95-p50 spread in this run, which is a simple tail-latency stability proxy.",
        "",
        "**What runtime would I use for a demo?** ONNX Runtime is the safest default demo runtime because it is portable and simple to reproduce. OpenVINO is also viable here because it ran successfully on the Intel CPU path.",
        "",
        "**What runtime would I use for production edge with more time?** I would continue evaluating OpenVINO for Intel CPU deployment, but only after checking output parity, packaging stability, warmup behavior, thermal behavior, and end-to-end ROS2 latency.",
        "",
        "**What can this benchmark not prove?** It does not prove detection accuracy parity, full ROS2 pipeline latency, camera ingest performance, thermal throttling behavior, long-duration stability, or behavior on other edge devices.",
        "",
        "## Notes",
        "",
        "- PyTorch is measured as a CPU model forward pass.",
        "- ONNX Runtime and OpenVINO results are imported from their benchmark CSV files.",
        "- These numbers measure runtime inference only, not preprocessing, postprocessing, tracking, overlay drawing, transport, or display.",
        "- p95 is more important than mean latency for field-debugging because occasional slow frames can create stale outputs.",
        "",
    ])

    path.write_text("\n".join(lines), encoding="utf-8")


def write_plot(path: Path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)

    labels = [row["runtime"] for row in rows]
    p50 = [float(row["latency_ms_p50"]) for row in rows]
    p95 = [float(row["latency_ms_p95"]) for row in rows]

    x = np.arange(len(labels))
    width = 0.35

    fig, ax = plt.subplots(figsize=(8, 4.5))
    ax.bar(x - width / 2, p50, width, label="p50 ms")
    ax.bar(x + width / 2, p95, width, label="p95 ms")
    ax.set_ylabel("Latency ms")
    ax.set_title("Runtime latency comparison")
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=160)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description="Compare PyTorch, ONNX Runtime, and OpenVINO benchmark results.")
    parser.add_argument("--pytorch-model", default="yolo11n.pt")
    parser.add_argument("--images", default="data/sample_frames")
    parser.add_argument("--onnx-results", default="reports/edge/onnx_runtime_results.csv")
    parser.add_argument("--openvino-results", default="reports/edge/openvino_results.csv")
    parser.add_argument("--input-size", type=int, default=640)
    parser.add_argument("--warmup", type=int, default=20)
    parser.add_argument("--iterations", type=int, default=200)
    parser.add_argument("--output-csv", default="reports/edge/runtime_comparison.csv")
    parser.add_argument("--output-md", default="reports/edge/runtime_comparison.md")
    parser.add_argument("--output-png", default="reports/edge/runtime_comparison.png")
    args = parser.parse_args()

    pytorch_model = Path(args.pytorch_model)
    images_dir = Path(args.images)
    onnx_results = Path(args.onnx_results)
    openvino_results = Path(args.openvino_results)

    if not pytorch_model.exists():
        raise FileNotFoundError(f"Missing PyTorch model: {pytorch_model}")

    if not images_dir.exists():
        raise FileNotFoundError(f"Missing images directory: {images_dir}")

    if not onnx_results.exists():
        raise FileNotFoundError(f"Missing ONNX Runtime results: {onnx_results}")

    if not openvino_results.exists():
        raise FileNotFoundError(f"Missing OpenVINO results: {openvino_results}")

    rows = [
        benchmark_pytorch(
            pytorch_model,
            images_dir,
            input_size=args.input_size,
            warmup=args.warmup,
            iterations=args.iterations,
        ),
        row_from_runtime_csv(
            onnx_results,
            runtime_label="ONNX Runtime",
            model_label="exported ONNX",
            notes="portable runtime",
        ),
        row_from_runtime_csv(
            openvino_results,
            runtime_label="OpenVINO",
            model_label="ONNX/OpenVINO",
            notes="optional Intel CPU path",
        ),
    ]

    output_csv = Path(args.output_csv)
    output_md = Path(args.output_md)
    output_png = Path(args.output_png)

    write_comparison_csv(output_csv, rows)
    write_markdown(output_md, rows)
    write_plot(output_png, rows)

    print(f"wrote {output_csv}")
    print(f"wrote {output_md}")
    print(f"wrote {output_png}")

    for row in rows:
        print(
            f"{row['runtime']}: "
            f"p50={float(row['latency_ms_p50']):.3f}ms "
            f"p95={float(row['latency_ms_p95']):.3f}ms "
            f"fps={float(row['throughput_fps']):.3f}"
        )


if __name__ == "__main__":
    main()
