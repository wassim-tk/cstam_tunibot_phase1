#!/bin/bash
set -e

# Source ROS 2 Humble environment
source /opt/ros/humble/setup.bash

if [ -f "/workspace/cstam/ros2_ws/install/setup.bash" ]; then
    source /workspace/cstam/ros2_ws/install/setup.bash
fi

exec "$@"
