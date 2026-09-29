# Autonomous Service Robot for Indoor Delivery (CSTAM-TUNIBOT)

> **CSTAM 3.0 Technical Challenge Solution**  
> Complete ROS 2 Software Stack & Web Command Center for Autonomous Indoor Delivery, SLAM, Nav2 Navigation, Dynamic Obstacle Avoidance, Task Management, Battery Simulation, and Auto-Docking.

---

## 🚀 Quick Start Guide

### Option 1: Native ROS 2 / Python Run (Local Host or WSL)

```bash
# 1. Install Web Bridge dependencies
pip3 install -r requirements.txt --break-system-packages

# 2. Build ROS 2 workspace
cd ros2_ws
colcon build --symlink-install
source install/setup.bash

# 3. Run master system launch file
ros2 launch cstam_core cstam_system.launch.py

# 4. Launch Web Dashboard & Command Center
python3 cstam_web_bridge/app.py

# 4. Access Web Interface in Browser
# Open: http://localhost:8000
```

### Option 2: Automated Demo Validation Pass

```bash
# Runs complete end-to-end demo script (submits deliveries, triggers obstacle, simulates battery preemption)
python3 run_demo.py
```

---

## 🛠️ Prompt Technical Specification Mapping Matrix

| Requirement Line Item | Phase | Implementation File / ROS 2 Node | Verification Method | Status |
| :--- | :--- | :--- | :--- | :--- |
| **1. Mapping & Localization (SLAM)** | Phase 1 | [`slam.launch.py`](file:///ros2_ws/src/cstam_navigation/launch/slam.launch.py), `slam_toolbox`, [`cstam_map.yaml`](file:///ros2_ws/src/cstam_navigation/maps/cstam_map.yaml), [`cstam_map.pgm`](file:///ros2_ws/src/cstam_navigation/maps/cstam_map.pgm) | `test_system.py` file verification & AMCL pose init | **PASSED** |
| **2. Autonomous Navigation (Nav2)** | Phase 1 | [`nav2_params.yaml`](file:///ros2_ws/src/cstam_navigation/config/nav2_params.yaml), [`waypoints.yaml`](file:///ros2_ws/src/cstam_navigation/config/waypoints.yaml), [`navigation.launch.py`](file:///ros2_ws/src/cstam_navigation/launch/navigation.launch.py) | Goal pose action dispatch & collision-free routing | **PASSED** |
| **3. Delivery Task Management** | Phase 1 | [`delivery_task_manager.py`](file:///ros2_ws/src/cstam_core/cstam_core/delivery_task_manager.py) | FIFO queue tests in `test_core_nodes.py` | **PASSED** |
| **4. Auto-Docking Behavior** | Phase 1 | [`docking_controller.py`](file:///ros2_ws/src/cstam_core/cstam_core/docking_controller.py) | Idle timeout (15s) & low battery (<20%) triggers | **PASSED** |
| **5. Dynamic Obstacle Avoidance** | Phase 2 | [`cstam_world.world`](file:///ros2_ws/src/cstam_gazebo/worlds/cstam_world.world) (`walking_human` actor), `/api/obstacle/trigger` | Costmap voxel layer updates & replanning | **PASSED** |
| **6. Complex Layout Handling** | Phase 2 | [`cstam_world.world`](file:///ros2_ws/src/cstam_gazebo/worlds/cstam_world.world) (Doorway at x=0..1), [`nav2_params.yaml`](file:///ros2_ws/src/cstam_navigation/config/nav2_params.yaml) (spin, backup, clear costmap) | Recovery behavior plugins verification | **PASSED** |
| **7. Battery & State Simulation** | Phase 2 | [`battery_simulator.py`](file:///ros2_ws/src/cstam_core/cstam_core/battery_simulator.py), `/battery_state` topic | Movement drain & dock charge math validation | **PASSED** |
| **8. Web Interface (User & Admin)** | Phase 3 | [`app.py`](file:///cstam_web_bridge/app.py), [`index.html`](file:///cstam_web_bridge/static/index.html), [`dashboard.js`](file:///cstam_web_bridge/static/dashboard.js) | REST API & WebSockets live canvas test | **PASSED** |

---

## 📌 Documented Engineering Assumptions

1. **Predefined Waypoint Coordinates**:
   - `Dock`: `x = -4.0`, `y = -4.0`
   - `Kitchen/Pickup`: `x = -3.5`, `y = 3.5`
   - `Table 1`: `x = 3.0`, `y = 3.5`
   - `Table 2`: `x = 3.5`, `y = -2.5`
   - `Table 3`: `x = 1.0`, `y = -3.5`
2. **Battery Threshold Policies**:
   - Low Battery Threshold: `< 20%` (initiates preemptive auto-docking).
   - Recharge Target Threshold: `>= 90%` (resumes pending delivery queue).
   - Idle Timeout: `15 seconds` without active tasks triggers return to dock.
3. **Map Scale**:
   - 10m x 10m area with 0.05m/pixel resolution (200x200 grid array).

---

## ⚠️ Known Limitations & Manual Workarounds

- **Simulated Hardware Drivers**: Physical hardware motor encoders and real battery hardware management ICs are simulated by ROS 2 software nodes (`battery_simulator.py` and `libgazebo_ros_diff_drive.so`).
- **Web UI Browser Audio**: Auto-playing notification chimes require browser user interaction on first page load due to modern browser autoplay security policies.
