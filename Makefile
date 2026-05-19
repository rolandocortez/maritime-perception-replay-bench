SHELL := /bin/bash

SAMPLE_VIDEO ?= data/samples/harbor_sample.mp4
SAMPLE_BAG ?= data/bags/sample_replay

.PHONY: help setup check inspect-video frames clean clean-python clean-ros

help:
	@echo "Available targets:"
	@echo "  setup          Create/update local Python environment"
	@echo "  check          Run basic Python checks"
	@echo "  inspect-video  Inspect SAMPLE_VIDEO=$(SAMPLE_VIDEO)"
	@echo "  frames         Extract a small frame sample from SAMPLE_VIDEO"
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
