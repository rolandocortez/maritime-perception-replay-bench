# Maritime Perception Replay Bench

A ROS2-based replay and debugging bench for maritime perception workflows.

## Current status

The project has completed Part 1: the replay foundation.

Implemented so far:

- dataset/source configuration;
- video inspection utility;
- video-to-frames utility;
- scenario configuration for clean, hard and degraded replay cases;
- acoustic lane scoped as a future optional plugin;
- local-only data and artifact layout;
- ROS2 workspace with package skeletons;
- custom ROS2 messages for tracking, runtime metrics and frame debug metadata;
- ROS2 topic schema configuration;
- launch-based replay entry point;
- video replay publisher for `/camera/image_raw`;
- frame debug publisher for `/debug/frame_info`;
- rosbag recording and replay workflow;
- timing and QoS policy;
- Part 1 artifact and acceptance configuration.

## Repository policy

This repository is intended to stay public-safe.

Versioned:

- source code;
- ROS2 packages;
- configs;
- scripts;
- tooling;
- this README.

Not versioned:

- private notes under `docs/`;
- local datasets;
- sample videos;
- generated frames;
- bags;
- model checkpoints;
- generated artifacts;
- generated reports.

## Setup

```bash
make setup
```

## Validate tooling

```bash
make check
```

## Inspect a local video

Default path:

```bash
data/samples/harbor_sample.mp4
```

Run:

```bash
make inspect-video
```

Or use a custom local path:

```bash
make inspect-video SAMPLE_VIDEO=/path/to/video.mp4
```

## Extract frames

```bash
make frames
```

## ROS2 build

```bash
cd ros2_ws
source /opt/ros/jazzy/setup.bash
colcon build --symlink-install
source install/setup.bash
cd ..
```

## Run video replay

Default sample path:

```bash
data/samples/harbor_sample.mp4
```

Run:

```bash
make run-replay
```

Or launch directly:

```bash
source /opt/ros/jazzy/setup.bash
source ros2_ws/install/setup.bash

ros2 launch maritime_bringup replay_pipeline.launch.py \
  video_path:=data/samples/harbor_sample.mp4 \
  loop:=true
```

Expected replay topics:

```text
/camera/image_raw
/debug/frame_info
```

## Inspect replay topics

In another terminal:

```bash
source /opt/ros/jazzy/setup.bash
source ros2_ws/install/setup.bash

ros2 topic list
ros2 topic hz /camera/image_raw
ros2 topic echo /debug/frame_info --once
```

## Record a sample bag

With replay running in another terminal:

```bash
make record-bag
```

The bag is written under:

```text
data/bags/
```

Bags are local-only and ignored by Git.

## Inspect a bag

```bash
make bag-info BAG=data/bags/<bag_name>
```

Or directly:

```bash
source /opt/ros/jazzy/setup.bash
ros2 bag info data/bags/<bag_name>
```

## Play a bag

```bash
make bag-play BAG=data/bags/<bag_name>
```

Or directly:

```bash
source /opt/ros/jazzy/setup.bash
ros2 bag play data/bags/<bag_name>
```

## Key ROS2 packages

```text
maritime_msgs      Custom ROS2 interfaces for replay, tracking and observability
replay_tools       Replay nodes and replay-related configuration
maritime_bringup   Launch files and top-level pipeline entry points
```

## Main topic contracts

```text
/camera/image_raw    sensor_msgs/msg/Image
/debug/frame_info    maritime_msgs/msg/FrameDebug
/detections          vision_msgs/msg/Detection2DArray
/tracks              maritime_msgs/msg/Track2DArray
/metrics/runtime     maritime_msgs/msg/RuntimeMetrics
```

## Key configs

```text
configs/datasets.yaml
configs/scenarios.yaml
configs/topic_schema.yaml
configs/replay.yaml
configs/qos_profiles.yaml
configs/rosbag_strategy.yaml
configs/timing_qos_policy.yaml
configs/artifact_layout.yaml
configs/artifact_strategy.yaml
configs/part1_acceptance.yaml
```

## Artifact layout

```text
data/bags/                 Local ROS2 replay logs
artifacts/metrics/         Runtime and evaluation metrics
artifacts/predictions/     Detector/tracker outputs and uncertain frames
artifacts/screenshots/     Demo and debugging screenshots
artifacts/models/          Checkpoints, ONNX and runtime exports
artifacts/manifests/       Dataset, bag and experiment metadata
reports/                   Local generated reports and acceptance notes
```

These outputs are intentionally ignored by Git, except for `.gitkeep` placeholders where needed.

## Project layout

```text
configs/      Runtime, dataset, scenario, topic, QoS and artifact configuration
scripts/      Utility scripts for ingest, preprocessing and rosbag recording
data/         Local-only datasets, samples, frames and bags
artifacts/    Local-only metrics, predictions, screenshots, models and manifests
reports/      Local-only generated reports
ros2_ws/      ROS2 workspace
```

## Part 1 acceptance

Part 1 establishes a reproducible ROS2 replay foundation.

Acceptance status:

- repo structure exists;
- ROS2 workspace builds;
- video replay publishes `/camera/image_raw`;
- frame debug metadata is published on `/debug/frame_info`;
- sample bags can be recorded;
- sample bags can be inspected with `ros2 bag info`;
- sample bags can be replayed with `ros2 bag play`;
- dataset/source decisions are configured;
- scenario design is configured;
- topic schema is configured;
- QoS and timing policy are configured;
- artifact layout is configured.

Part 1 prepares the project for Part 2: detection, tracking, metrics and evaluation workflows.

## Scope

This is not an operational maritime detection system. It is a reproducible engineering prototype for building and debugging a maritime perception replay workflow.


Current milestone: H15 — Detector/tracker perception core
