# Maritime Perception Replay Bench

A ROS2-based replay and debugging bench for maritime perception workflows.

## Current status

The project is in the foundation stage.

Implemented so far:

- dataset/source configuration;
- video inspection utility;
- video-to-frames utility;
- scenario configuration for clean, hard and degraded replay cases;
- acoustic lane scoped as a future optional plugin;
- local-only data and artifact layout.

## Repository policy

This repository is intended to stay public-safe.

Versioned:

- source code;
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
- generated artifacts.

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

## Project layout

```text
configs/      Runtime and dataset/scenario configuration
scripts/      Utility scripts for ingest and preprocessing
data/         Local-only datasets, samples, frames and bags
artifacts/    Local-only metrics, predictions, screenshots and manifests
ros2_ws/      Future ROS2 workspace
```

## Scope

This is not an operational maritime detection system. It is a reproducible engineering prototype for building and debugging a maritime perception replay workflow.
