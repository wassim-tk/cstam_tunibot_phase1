# Autonomous Waiter Service Robot for Indoor Delivery (CSTAM-TUNIBOT)

> **CSTAM 3.0 Technical Challenge Solution — Phase 1 MVP (50 Points)**  
> Complete ROS 2 Software Stack & Delivery Process Simulator for Autonomous Indoor Restaurant Delivery: 3D Gazebo Simulation (`restaurant.world` with 24 Dining Tables), BellaBot 3D Robot Model, SLAM / AMCL Localization, Nav2 Autonomous Path Planning, Delivery Task Queue Management (Dynamic Editing & Deletion), and Auto-Docking (Manual Stop & Order Preemption).

---

## 🚀 Quick Start Guide

### Option 1: Complete Autonomous Delivery System (Recommended)

Run the autonomous system in two terminals:

```bash
# Terminal 1: Launch 3D Gazebo Sim, 24 Dining Tables, BellaBot, AMCL, Nav2 & RViz2
./run_autonomous_system.sh

# Terminal 2: Launch the Native Delivery Process Simulator Interface (GUI)
./run_delivery_simulator.sh
```

> **Note on Headless / Remote SSH:**  
> If running without an X11/Wayland display, run the simulator in interactive CLI mode:
> ```bash
> ./run_delivery_simulator.sh --cli
> ```

---

### Option 2: SLAM Mapping Demonstration

To inspect or regenerate the restaurant occupancy grid using `slam_toolbox`:

```bash
./run_mapping_demo.sh
```

---

### Option 3: Automated Verification Test Suite

Run the automated verification suite to validate workspace deliverables, waypoints, queue lifecycle, editing/deletion, and docking logic:

```bash
python3 test_system.py
```

---

## 🛠️ Prompt Technical Specification Mapping Matrix (Phase 1 MVP)

| Requirement Line Item | Component / ROS 2 Implementation | Key Deliverable Files | Verification Method | Status |
| :--- | :--- | :--- | :--- | :--- |
| **1. Mapping & Localization** | SLAM Toolbox & AMCL with 2D LiDAR and Odometry | [`cstam_map.yaml`](file:///ros2_ws/src/cstam_navigation/maps/cstam_map.yaml), [`cstam_map.pgm`](file:///ros2_ws/src/cstam_navigation/maps/cstam_map.pgm), [`slam.launch.py`](file:///ros2_ws/src/cstam_navigation/launch/slam.launch.py) | SLAM demo generation & AMCL map-frame auto-initialization at Dock `(7.06, -12.00)` | **PASSED** |
| **2. Autonomous Navigation** | Nav2 Navigation Stack (DWB Local Planner, Navfn Planner, Recovery Behaviors) | [`nav2_params.yaml`](file:///ros2_ws/src/cstam_navigation/config/nav2_params.yaml), [`navigation.launch.py`](file:///ros2_ws/src/cstam_navigation/launch/navigation.launch.py), [`cstam_nav2.rviz`](file:///ros2_ws/src/cstam_navigation/config/cstam_nav2.rviz) | Collision-free obstacle avoidance, costmap inflation, goal dispatch in 3D Gazebo world | **PASSED** |
| **3. Delivery Task Management** | State Machine & Task Queue Manager with Edit & Delete capabilities | [`delivery_task_manager.py`](file:///ros2_ws/src/cstam_core/cstam_core/delivery_task_manager.py) | FIFO queue tests, dynamic table/item modification, task deletion, and goal dispatch | **PASSED** |
| **4. Auto-Docking Behavior** | Autonomous Return-to-Dock with Manual Stop & New Order Preemption | [`docking_controller.py`](file:///ros2_ws/src/cstam_core/cstam_core/docking_controller.py), [`delivery_task_manager.py`](file:///ros2_ws/src/cstam_core/cstam_core/delivery_task_manager.py) | 15s idle trigger, physical driving to dock, manual stop/cancel halt, and preemption on new deliveries | **PASSED** |
| **5. Delivery Process Simulator** | High-contrast GUI & interactive CLI interface | [`delivery_simulator_ui.py`](file:///delivery_simulator_ui.py), [`run_delivery_simulator.sh`](file:///run_delivery_simulator.sh) | Order placement, queue selection, editing/deletion, auto-docking controls, and live status | **PASSED** |

> **Phase 1 Scope Boundary Note:**  
> Per challenge instructions, Phase 1 strictly targets the 50-point core MVP deliverables. Advanced Phase 2/3 features (battery simulation and web bridge) are quarantined in `archive_non_phase1/` and omitted from the active workspace build.

---

## 🍽️ Predefined Waypoints & Restaurant Layout

The restaurant world (`restaurant.world`) features **24 Dining Tables**, an **Order Pickup Counter (Kitchen)**, and a **Charging Dock** located with generous service aisle clearance:

| Service Zone | Waypoints | Map Coordinates $(x, y)$ | Description |
| :--- | :--- | :--- | :--- |
| **Charging Station** | `Dock` | $(7.06, -12.00)$ | Southeast corner docking station & staging zone |
| **Kitchen / Pickup** | `Kitchen/Pickup` | $(-9.60, -1.39)$ | West central counter for food/drink pickup |
| **North Terrace** | `Table 0` .. `Table 5` | $x \in [-8.24, 4.76]$, $y = 0.50$ | Row 0 dining tables along northern service aisle |
| **Mid Lounge** | `Table 6` .. `Table 11` | $x \in [-8.24, 4.76]$, $y = -3.10$ | Row 1 dining tables along main central promenade |
| **Central Salon** | `Table 12` .. `Table 17` | $x \in [-8.24, 4.76]$, $y = -5.85$ | Row 2 dining tables facing southern walkway |
| **South Wing** | `Table 18` .. `Table 23` | $x \in [-8.24, 4.76]$, $y = -9.45$ | Row 3 dining tables along southern service aisle |

All waypoint coordinates and orientations are defined in [`waypoints.yaml`](file:///ros2_ws/src/cstam_navigation/config/waypoints.yaml) and referenced by [`delivery_task_manager.py`](file:///ros2_ws/src/cstam_core/cstam_core/delivery_task_manager.py).

---

## 📋 Interactive Delivery Simulator Interface Features

The native Delivery Process Simulator ([`delivery_simulator_ui.py`](file:///delivery_simulator_ui.py)) provides full operational control over the robot:

1. **Order Dispatcher:**
   - Dropdown selection of all 24 dining tables or Kitchen.
   - Food/beverage entry field with quick-preset buttons (Espresso, Burger, Pasta, Salad, Lemonade, Tiramisu).
   - High-contrast slate theme (`#2b2d42`) with bright white input text.

2. **Live Task Queue & Modification:**
   - Click any queued order in the **Pending Queue Orders** listbox to select it.
   - The selected task automatically loads into the input fields.
   - **`✏️ Save Edit to Task`**: Modifies the selected task's table number or item description in real time.
   - **`🗑️ Delete Task`**: Removes the selected task from the queue.
   - **`✖ Cancel`**: Clears selection.
   - Background update polling preserves user selection without flickering or deselecting.

3. **Auto-Docking Controls:**
   - **`⚓ Return-To-Dock`**: Commands the robot to physically navigate back to the Southeast Docking Station (`7.06, -12.00`). If already at the dock ($<0.60\,\text{m}$), status immediately registers as `DOCKED ⚡`.
   - **`🛑 Stop Docking`**: Immediately cancels the active Nav2 docking goal, publishes zero velocity to `/cmd_vel` to brake the robot base to a halt, and returns the robot state to `IDLE`.
   - **New Order Preemption**: If a delivery order is placed while the robot is en route to the dock, docking is **instantly cancelled**, the new order is popped, and the robot immediately pivots to deliver the meal.

---

## 📡 ROS 2 Communication Architecture

| Topic / Action Name | Type | Direction | Purpose |
| :--- | :--- | :--- | :--- |
| `/delivery_request` | `std_msgs/msg/String` (JSON) | Simulator $\rightarrow$ Task Manager | Submits new delivery orders (`{"target": "...", "item": "..."}`) |
| `/delivery_task_action` | `std_msgs/msg/String` (JSON) | Simulator $\rightarrow$ Task Manager | Commands queue actions (`{"action": "modify"\|"delete"\|"stop_dock", ...}`) |
| `/dock_command` | `std_msgs/msg/String` | Simulator / Controller $\rightarrow$ Task Manager | Triggers dock sequence (`"DOCK_NOW:..."`) or manual cancellation (`"STOP_DOCK"`) |
| `/dock_state` | `std_msgs/msg/Bool` | Task Manager $\rightarrow$ Simulator | Publishes real-time docked status (`true` = docked, `false` = undocked) |
| `/delivery_queue_status` | `std_msgs/msg/String` (JSON) | Task Manager $\rightarrow$ Simulator | Broadcasts active task, pending queue list, and completed count |
| `/robot_system_state` | `std_msgs/msg/String` | Task Manager $\rightarrow$ Simulator | Broadcasts system state (`IDLE`, `NAVIGATING`, `AT_TABLE`, `DOCKING`, `DOCKED`) |
| `/navigate_to_pose` | `nav2_msgs/action/NavigateToPose` | Task Manager $\rightarrow$ Nav2 | Dispatches navigation goals to Nav2 behavior tree |
| `/cmd_vel` | `geometry_msgs/msg/Twist` | Nav2 / Task Manager $\rightarrow$ Diff-Drive | Commands wheel velocities and emergency braking |
| `/scan` | `sensor_msgs/msg/LaserScan` | Robot LiDAR $\rightarrow$ Nav2 / AMCL | 270° FOV obstacle perception and localized costmap updates |
