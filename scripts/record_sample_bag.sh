#!/usr/bin/env bash
set -eo pipefail

BAG_STORAGE="${BAG_STORAGE:-mcap}"
BAG_PREFIX="${BAG_PREFIX:-sample_replay}"
BAG_ROOT="${BAG_ROOT:-data/bags}"
BAG_DIR="${BAG_ROOT}/${BAG_PREFIX}_$(date +%Y%m%d_%H%M%S)"

mkdir -p "${BAG_ROOT}"

source /opt/ros/jazzy/setup.bash

if [ -f "ros2_ws/install/setup.bash" ]; then
  source ros2_ws/install/setup.bash
fi

TOPICS=(
  "/camera/image_raw"
  "/debug/frame_info"
)

if ros2 topic list | grep -qx "/clock"; then
  TOPICS+=("/clock")
fi

echo "Recording bag:"
echo "  output:  ${BAG_DIR}"
echo "  storage: ${BAG_STORAGE}"
echo "  topics:"
printf "    %s\n" "${TOPICS[@]}"

ros2 bag record \
  --storage "${BAG_STORAGE}" \
  -o "${BAG_DIR}" \
  "${TOPICS[@]}"

echo "Recorded bag at: ${BAG_DIR}"
