#!/usr/bin/env python3
import argparse
import csv
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import yaml

try:
    import rclpy
    from rclpy.node import Node
    from maritime_msgs.msg import RuntimeMetricArray
except ImportError as exc:
    raise SystemExit(
        "Could not import ROS2 Python modules. Source the ROS environment first:\n"
        "  source /opt/ros/jazzy/setup.bash\n"
        "  source .venv/bin/activate\n"
        "  source ros2_ws/install/setup.bash\n"
        f"Original error: {exc}"
    )

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

from summarize_metrics import summarize_csv  # noqa: E402


class RuntimeMetricRecorder(Node):
    def __init__(self, metrics_csv):
        super().__init__("online_benchmark_recorder")
        self.metrics_csv = Path(metrics_csv)
        self.rows_written = 0

        self.metrics_csv.parent.mkdir(parents=True, exist_ok=True)
        self.file = self.metrics_csv.open("w", encoding="utf-8", newline="")
        self.writer = csv.DictWriter(
            self.file,
            fieldnames=[
                "wall_time_sec",
                "ros_time_sec",
                "frame_id",
                "name",
                "value",
                "unit",
                "window",
            ],
        )
        self.writer.writeheader()

        self.subscription = self.create_subscription(
            RuntimeMetricArray,
            "/metrics/runtime",
            self.on_metrics,
            10,
        )

    def on_metrics(self, msg):
        ros_time_sec = float(msg.header.stamp.sec) + float(msg.header.stamp.nanosec) * 1e-9

        for metric in msg.metrics:
            self.writer.writerow(
                {
                    "wall_time_sec": f"{time.time():.6f}",
                    "ros_time_sec": f"{ros_time_sec:.9f}",
                    "frame_id": msg.header.frame_id,
                    "name": metric.name,
                    "value": f"{float(metric.value):.9f}",
                    "unit": metric.unit,
                    "window": metric.window,
                }
            )
            self.rows_written += 1

        self.file.flush()

    def close(self):
        self.file.flush()
        self.file.close()


def load_scenario(config_path, scenario_name):
    config_path = Path(config_path)
    data = yaml.safe_load(config_path.read_text(encoding="utf-8"))

    scenarios = data.get("scenarios", {})

    if scenario_name not in scenarios:
        available = ", ".join(sorted(scenarios))
        raise SystemExit(f"Unknown scenario '{scenario_name}'. Available: {available}")

    scenario = dict(scenarios[scenario_name])
    scenario["name"] = scenario_name
    scenario["config_path"] = str(config_path)

    return scenario


def start_process(command, *, log_path):
    log_file = Path(log_path).open("w", encoding="utf-8")

    process = subprocess.Popen(
        command,
        cwd=str(REPO_ROOT),
        stdout=log_file,
        stderr=subprocess.STDOUT,
        text=True,
        preexec_fn=os.setsid,
    )

    return process, log_file


def stop_process(process, log_file, *, timeout_sec=8.0):
    if process.poll() is None:
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGINT)
            process.wait(timeout=timeout_sec)
        except subprocess.TimeoutExpired:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
            process.wait(timeout=timeout_sec)

    log_file.close()


def write_run_config(output_dir, scenario, args):
    perception_command = [
        "ros2",
        "launch",
        "maritime_bringup",
        "perception_core.launch.py",
        f"video_path:={scenario['video_path']}",
    ]

    if scenario.get("fault_profile") == "frame_drop":
        perception_command.append("enable_faults:=true")

    run_config = {
        "scenario": scenario,
        "output_dir": str(output_dir),
        "metrics_topic": "/metrics/runtime",
        "commands": {
            "perception": perception_command,
            "metrics": [
                "ros2",
                "launch",
                "metrics_node",
                "metrics.launch.py",
            ],
        },
        "benchmark": {
            "duration_sec": float(scenario.get("duration_sec", args.duration_sec or 15)),
            "warmup_sec": float(scenario.get("warmup_sec", args.warmup_sec)),
            "fault_profile": scenario.get("fault_profile", "none"),
        },
    }

    path = output_dir / "run_config.yaml"
    path.write_text(yaml.safe_dump(run_config, sort_keys=False), encoding="utf-8")

    return run_config


def write_notes(output_dir, scenario, rows_written, summary):
    metrics = summary.get("metrics", {})

    lines = [
        "# Online benchmark notes",
        "",
        f"- Scenario: `{scenario['name']}`",
        f"- Video: `{scenario['video_path']}`",
        f"- Fault profile: `{scenario.get('fault_profile', 'none')}`",
        f"- Runtime metric rows: `{rows_written}`",
        "",
        "## Key latest metrics",
        "",
    ]

    for key in [
        "input_fps",
        "detector_fps",
        "tracker_fps",
        "overlay_fps",
        "end_to_end_latency_ms_p95",
        "detector_latency_ms_p95",
        "active_tracks",
        "detections_per_frame",
        "dropped_frames_estimate",
    ]:
        payload = metrics.get(key)
        if payload:
            lines.append(f"- {key}: {payload['latest']:.3f} {payload['unit']}")

    lines.extend(
        [
            "",
            "## Reproducibility",
            "",
            "This run was generated from a named scenario config and exported as CSV plus JSON summary.",
            "Generated files are local benchmark artifacts and should not be committed.",
            "",
        ]
    )

    (output_dir / "notes.md").write_text("\n".join(lines), encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description="Run online replay benchmark and export metrics.")
    parser.add_argument("--scenario", required=True, help="Scenario name from config")
    parser.add_argument("--output", required=True, help="Output directory for benchmark artifacts")
    parser.add_argument(
        "--config",
        default=str(REPO_ROOT / "configs" / "benchmark_scenarios.yaml"),
        help="Benchmark scenario YAML",
    )
    parser.add_argument("--duration-sec", type=float, default=None)
    parser.add_argument("--warmup-sec", type=float, default=3.0)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    scenario = load_scenario(args.config, args.scenario)
    duration_sec = float(args.duration_sec or scenario.get("duration_sec", 15))
    warmup_sec = float(scenario.get("warmup_sec", args.warmup_sec))

    output_dir = Path(args.output)

    if output_dir.exists() and any(output_dir.iterdir()) and not args.overwrite:
        raise SystemExit(
            f"Output directory already exists and is not empty: {output_dir}\n"
            "Use --overwrite or choose a new output path."
        )

    output_dir.mkdir(parents=True, exist_ok=True)

    run_config = write_run_config(output_dir, scenario, args)

    perception_cmd = run_config["commands"]["perception"]
    metrics_cmd = run_config["commands"]["metrics"]

    print(f"scenario: {args.scenario}")
    print(f"output: {output_dir}")
    print(f"duration_sec: {duration_sec}")
    print(f"warmup_sec: {warmup_sec}")
    print("starting perception pipeline...")

    perception_process, perception_log = start_process(
        perception_cmd,
        log_path=output_dir / "perception.log",
    )

    time.sleep(2.0)

    fault_process = None
    fault_log = None

    if scenario.get("fault_profile") == "frame_drop":
        print("starting frame-drop fault injector...")
        fault_cmd = [
            "ros2",
            "launch",
            "fault_injector_node",
            "frame_drop.launch.py",
            f"drop_probability:={scenario.get('drop_probability', 0.15)}",
            f"deterministic:={str(scenario.get('deterministic', True)).lower()}",
            f"random_seed:={scenario.get('random_seed', 42)}",
        ]
        fault_process, fault_log = start_process(
            fault_cmd,
            log_path=output_dir / "fault_injector.log",
        )

    print("starting metrics node...")
    metrics_process, metrics_log = start_process(
        metrics_cmd,
        log_path=output_dir / "metrics_node.log",
    )

    time.sleep(warmup_sec)

    metrics_csv = output_dir / "metrics.csv"

    rclpy.init(args=None)
    recorder = RuntimeMetricRecorder(metrics_csv)

    deadline = time.monotonic() + duration_sec

    try:
        print("recording runtime metrics...")
        while time.monotonic() < deadline:
            rclpy.spin_once(recorder, timeout_sec=0.2)
    finally:
        recorder.close()
        recorder.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()

        stop_process(metrics_process, metrics_log)

        if fault_process is not None and fault_log is not None:
            stop_process(fault_process, fault_log)

        stop_process(perception_process, perception_log)

    summary = summarize_csv(metrics_csv)
    summary["scenario"] = scenario
    summary["rows_written"] = recorder.rows_written

    summary_path = output_dir / "summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")

    write_notes(output_dir, scenario, recorder.rows_written, summary)

    print(f"wrote {metrics_csv}")
    print(f"wrote {summary_path}")
    print(f"wrote {output_dir / 'run_config.yaml'}")
    print(f"wrote {output_dir / 'notes.md'}")
    print(f"rows_written: {recorder.rows_written}")


if __name__ == "__main__":
    main()
