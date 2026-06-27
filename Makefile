SHELL := /bin/bash

SAMPLE_VIDEO ?= data/samples/harbor_sample.mp4
SAMPLE_BAG ?= data/bags/sample_replay

.PHONY: help setup check inspect-video frames run-replay record-bag bag-info bag-play clean clean-python clean-ros

help:
	@echo "Available targets:"
	@echo "  setup          Create/update local Python environment"
	@echo "  check          Run basic Python checks"
	@echo "  inspect-video  Inspect SAMPLE_VIDEO=$(SAMPLE_VIDEO)"
	@echo "  frames         Extract a small frame sample from SAMPLE_VIDEO"\n	@echo "  run-replay     Launch the ROS2 video replay pipeline"\n	@echo "  record-bag     Record replay topics into data/bags"\n	@echo "  bag-info       Show rosbag info for BAG=/path/to/bag"\n	@echo "  bag-play       Play rosbag for BAG=/path/to/bag"
	@echo "  clean          Remove generated caches and ROS2 build outputs"
	@echo "  clean-python   Remove Python caches"
	@echo "  clean-ros      Remove ROS2 build/install/log folders"

setup:
	python3 -m venv .venv
	. .venv/bin/activate && python -m pip install --upgrade pip
	. .venv/bin/activate && pip install -r requirements.txt

check:
	. .venv/bin/activate && python -m py_compile scripts/inspect_video.py scripts/video_to_frames.py
	. .venv/bin/activate && python scripts/inspect_video.py --help >/dev/null
	. .venv/bin/activate && python scripts/video_to_frames.py --help >/dev/null

inspect-video:
	@if [ ! -f "$(SAMPLE_VIDEO)" ]; then \
		echo "Missing sample video: $(SAMPLE_VIDEO)"; \
		echo "Place a local video there or run: make inspect-video SAMPLE_VIDEO=/path/to/video.mp4"; \
		exit 1; \
	fi
	. .venv/bin/activate && python scripts/inspect_video.py "$(SAMPLE_VIDEO)"

frames:
	@if [ ! -f "$(SAMPLE_VIDEO)" ]; then \
		echo "Missing sample video: $(SAMPLE_VIDEO)"; \
		echo "Place a local video there or run: make frames SAMPLE_VIDEO=/path/to/video.mp4"; \
		exit 1; \
	fi
	. .venv/bin/activate && python scripts/video_to_frames.py "$(SAMPLE_VIDEO)" \
		--output-dir data/interim/frames \
		--stride 30 \
		--max-frames 20

clean: clean-python clean-ros
	rm -rf data/interim/frames

clean-python:
	find . -type d -name "__pycache__" -prune -exec rm -rf {} +
	rm -rf .pytest_cache .mypy_cache .ruff_cache

clean-ros:
	rm -rf ros2_ws/build ros2_ws/install ros2_ws/log


run-replay:
	@if [ ! -f "$(SAMPLE_VIDEO)" ]; then \
		echo "Missing sample video: $(SAMPLE_VIDEO)"; \
		echo "Place a local video there or run: make run-replay SAMPLE_VIDEO=/path/to/video.mp4"; \
		exit 1; \
	fi
	source /opt/ros/jazzy/setup.bash && \
	source ros2_ws/install/setup.bash && \
	ros2 launch maritime_bringup replay_pipeline.launch.py \
		video_path:="$(SAMPLE_VIDEO)" \
		loop:=true

record-bag:
	bash scripts/record_sample_bag.sh

bag-info:
	@if [ -z "$(BAG)" ]; then \
		echo "Usage: make bag-info BAG=data/bags/<bag_name>"; \
		exit 1; \
	fi
	source /opt/ros/jazzy/setup.bash && ros2 bag info "$(BAG)"

bag-play:
	@if [ -z "$(BAG)" ]; then \
		echo "Usage: make bag-play BAG=data/bags/<bag_name>"; \
		exit 1; \
	fi
	source /opt/ros/jazzy/setup.bash && ros2 bag play "$(BAG)"
.PHONY: benchmark-online benchmark-online-short

benchmark-online:
	python scripts/run_online_benchmark.py --scenario clean --output reports/benchmarks/clean_latest --overwrite

benchmark-online-short:
	python scripts/run_online_benchmark.py --scenario clean_short --output reports/benchmarks/clean_short_latest --overwrite
.PHONY: run-clean run-dropframes run-blur run-delay run-glare benchmark-robustness robustness-report

run-clean:
	ros2 launch maritime_bringup field_debugging.launch.py fault_profile:=none enable_metrics:=true

run-dropframes:
	ros2 launch maritime_bringup field_debugging.launch.py enable_faults:=true fault_profile:=frame_drop_15 enable_metrics:=true

run-blur:
	ros2 launch maritime_bringup field_debugging.launch.py enable_faults:=true fault_profile:=blur_medium enable_metrics:=true

run-delay:
	ros2 launch maritime_bringup field_debugging.launch.py enable_faults:=true fault_profile:=delay_100ms enable_metrics:=true

run-glare:
	ros2 launch maritime_bringup field_debugging.launch.py enable_faults:=true fault_profile:=glare_approx enable_metrics:=true

benchmark-robustness:
	python scripts/run_online_benchmark.py --scenario clean --output reports/robustness/clean --overwrite
	python scripts/run_online_benchmark.py --scenario frame_drop_15 --output reports/robustness/frame_drop_15 --overwrite
	python scripts/run_online_benchmark.py --scenario blur_medium --output reports/robustness/blur_medium --overwrite
	python scripts/run_online_benchmark.py --scenario delay_100ms --output reports/robustness/delay_100ms --overwrite
	python scripts/run_online_benchmark.py --scenario glare_approx --output reports/robustness/glare_approx --overwrite
	python scripts/build_robustness_report.py

robustness-report:
	python scripts/build_robustness_report.py

bench-onnx:
	python scripts/benchmark_onnx_runtime.py --model models/onnx/yolo11n_maritime_baseline.onnx --images data/sample_frames --output reports/edge/onnx_runtime_results.csv

bench-openvino:
	python scripts/benchmark_openvino.py --model models/onnx/yolo11n_maritime_baseline.onnx --images data/sample_frames --output reports/edge/openvino_results.csv

compare-runtimes:
	python scripts/compare_runtime_results.py --input reports/edge --output reports/edge/runtime_comparison.md

oak-live:
	cd ros2_ws && . /opt/ros/jazzy/setup.sh && . install/setup.sh && ros2 launch maritime_bringup oak_live_perception.launch.py

mine-uncertain:
	cd ros2_ws && . /opt/ros/jazzy/setup.sh && . install/setup.sh && ros2 launch annotation_miner uncertainty_mining.launch.py image_topic:=/oak/rgb/image_raw detections_topic:=/detections detections_type:=vision_msgs/msg/Detection2DArray max_confidence:=1.0 many_detections_count:=1 max_saved_frames:=20

mine-unstable:
	cd ros2_ws && . /opt/ros/jazzy/setup.sh && . install/setup.sh && ros2 launch annotation_miner unstable_track_mining.launch.py image_topic:=/oak/rgb/image_raw tracks_topic:=/tracks min_track_age_for_stability:=20 max_missed_frames:=1 max_saved_events:=20

export-annotation:
	mkdir -p reports/annotation/export_examples
	python scripts/export_mined_frames_to_coco.py --input reports/annotation/uncertain_frames --output reports/annotation/export_examples/uncertain_frames_coco.json
	python scripts/export_cvat_task_folder.py --input reports/annotation/unstable_tracks --output reports/annotation/export_examples/cvat_task_unstable_tracks

package-run:
	python scripts/create_run_artifact_bundle.py --run-name latest --config configs/artifact_registry.yaml --notes "Packaged via make package-run." --output artifacts/runs

minio-up:
	docker compose -f docker/minio-compose.yml up -d

minio-down:
	docker compose -f docker/minio-compose.yml down

minio-upload:
	RUN_DIR=$$(find artifacts/runs -mindepth 1 -maxdepth 1 -type d | sort | tail -1); python scripts/upload_artifacts_to_minio.py --run-dir "$$RUN_DIR" --bucket maritime-replay-bench --list-after
