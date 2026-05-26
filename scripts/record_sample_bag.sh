#!/usr/bin/env bash
set -eo pipefail

BAG_STORAGE="${BAG_STORAGE:-mcap}"
BAG_STORAGE_PRESET="${BAG_STORAGE_PRESET:-zstd_fast}"
BAG_PREFIX="${BAG_PREFIX:-sample_replay}"
BAG_ROOT="${BAG_ROOT:-data/bags}"
RECORD_SECONDS="${RECORD_SECONDS:-8}"
RECORD_IMAGE="${RECORD_IMAGE:-1}"

BAG_DIR="${BAG_ROOT}/${BAG_PREFIX}_$(date +%Y%m%d_%H%M%S)"

mkdir -p "${BAG_ROOT}"

source /opt/ros/jazzy/setup.bash

if [ -f "ros2_ws/install/setup.bash" ]; then
  source ros2_ws/install/setup.bash
fi

TOPICS=()

if [ "${RECORD_IMAGE}" = "1" ]; then
  TOPICS+=("/camera/image_raw")
fi

TOPICS+=("/debug/frame_info")

if ros2 topic list | grep -qx "/clock"; then
  TOPICS+=("/clock")
fi

RECORD_ARGS=(
  --storage "${BAG_STORAGE}"
  -o "${BAG_DIR}"
)

if ros2 bag record --help | grep -q -- "--storage-preset-profile"; then
  RECORD_ARGS+=(--storage-preset-profile "${BAG_STORAGE_PRESET}")
fi

echo "Recording bag:"
echo "  output:          ${BAG_DIR}"
echo "  storage:         ${BAG_STORAGE}"
echo "  storage preset:  ${BAG_STORAGE_PRESET}"
echo "  seconds:         ${RECORD_SECONDS}"
echo "  record image:    ${RECORD_IMAGE}"
echo "  topics:"
printf "    %s\n" "${TOPICS[@]}"

set +e
timeout --signal=SIGINT --kill-after=5s "${RECORD_SECONDS}s" \
  ros2 bag record "${RECORD_ARGS[@]}" "${TOPICS[@]}"
status=$?
set -e

if [ "${status}" -ne 0 ] && [ "${status}" -ne 124 ] && [ "${status}" -ne 130 ]; then
  echo "ros2 bag record failed with status ${status}"
  exit "${status}"
fi

echo "Recorded bag at: ${BAG_DIR}"
