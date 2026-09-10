# CSTAM-TUNIBOT Master Dockerfile
# Base Image: ROS 2 Humble Desktop with Gazebo Classic 11
FROM osrf/ros:humble-desktop-full

# Set Non-interactive Installation
ENV DEBIAN_FRONTEND=noninteractive
ENV PYTHONUNBUFFERED=1

# Install System Dependencies & ROS 2 Navigation Stack
RUN apt-get update && apt-get install -y \
    ros-humble-nav2-bringup \
    ros-humble-navigation2 \
    ros-humble-slam-toolbox \
    ros-humble-gazebo-ros-pkgs \
    ros-humble-gazebo-plugins \
    ros-humble-rosbridge-suite \
    ros-humble-xacro \
    ros-humble-robot-state-publisher \
    python3-pip \
    python3-colcon-common-extensions \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install Python Requirements
RUN pip3 install --no-cache-dir \
    fastapi \
    uvicorn \
    pydantic \
    httpx \
    websockets \
    pytest

# Create Workspace Directory
WORKDIR /workspace/cstam

# Copy Workspace Code
COPY . /workspace/cstam/

# Build ROS 2 Workspace
RUN . /opt/ros/humble/setup.sh && \
    cd ros2_ws && \
    colcon build --symlink-install

# Expose Web Interface Port
EXPOSE 8000

# Entrypoint setup
COPY ./docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["python3", "run_demo.py"]
