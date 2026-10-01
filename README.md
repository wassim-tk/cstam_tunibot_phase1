# Autonomous Waiter Service Robot for Indoor Delivery (CSTAM-TUNIBOT)

A complete ROS 2 autonomous navigation and delivery orchestration stack developed for indoor restaurant and hospitality environments.

The system integrates 3D Gazebo simulation, a BellaBot differential-drive robot model with LiDAR and wheel odometry, AMCL localization, Nav2 autonomous navigation, a dynamic delivery task queue manager, automatic return-to-dock behaviors, and a native Mission Control Simulator interface (GUI and CLI).

---

## 📌 System Architecture Overview

```
                      +-----------------------------------+
                      |   Mission Control Simulator UI    |
                      |   (delivery_simulator_ui.py)      |
                      +-----------------+-----------------+
                                        |  /delivery_request
                                        |  /delivery_task_action
                                        |  /dock_command
                                        v
+-----------------------+     +-------------------+     +-----------------------+
|  Auto-Docking Node    | --> | Delivery Task     | --> | Nav2 Navigation Stack |
| (docking_controller)  |     | Manager Node      |     | (Planner, Controller, |
+-----------------------+     | (TaskQueueManager)|     |  Recoveries, BT)      |
                              +---------+---------+     +-----------+-----------+
                                        |                           |
                                        v                           v
                                  /dock_state                   /cmd_vel
                                  /delivery_queue_status            |
                                  /robot_system_state               v
                                                        +-----------------------+
                                                        | Gazebo Simulation     |
                                                        | - BellaBot Robot Base |
                                                        | - 2D LiDAR (/scan)    |
                                                        | - AMCL Localization   |
                                                        +-----------------------+
```

---

## 🚀 Quick Start Guide

### 1. Prerequisites & Environment Setup

Ensure ROS 2 Jazzy and Gazebo Sim dependencies are installed and sourced:

```bash
source /opt/ros/jazzy/setup.bash
cd ~/cstan_tunibot
source ros2_ws/install/setup.bash
```

If you need to rebuild the workspace packages:

```bash
cd ros2_ws
colcon build --symlink-install
source install/setup.bash
cd ..
```

---

### 2. Running the System

#### Terminal 1: Launch the Autonomous Robot Simulation
Launch 3D Gazebo, the BellaBot mobile robot, AMCL localization, Nav2 path planning, and RViz2:

```bash
./run_autonomous_system.sh
```

> **Environment Selection:**  
> By default, the system launches the **Restaurant Lounge** (`restaurant.world`, 24 dining tables).  
> To launch **Dar Tunibot** (`resto_arbi.world`, 10 dining tables), pass the world argument:
> ```bash
> ./run_autonomous_system.sh world:=resto_arbi.world
> ```

#### Terminal 2: Launch the Mission Control Simulator Dashboard
Open the native operator interface to dispatch orders and monitor live status:

```bash
./run_delivery_simulator.sh
```

> **Headless / Remote SSH Mode:**  
> If running without a graphical display (e.g. over SSH without X11 forwarding), run in interactive CLI mode:
> ```bash
> ./run_delivery_simulator.sh --cli
> ```

---

### 3. Running Automated System Verification

Validate workspace files, waypoints, queue lifecycle, editing/deletion, and auto-docking state logic:

```bash
python3 test_system.py
```

---

### 4. SLAM Mapping Demonstration (Optional)

To inspect or generate an occupancy grid map of the restaurant using `slam_toolbox`:

```bash
./run_mapping_demo.sh
```

---

## 📖 How to Use the System

### 1. Placing Delivery Orders
1. In the **Order Dispatcher** panel on the left:
   - Select a destination table from the dropdown menu (e.g., `Table 1`, `Table 5`, or `Kitchen/Pickup`).
   - Enter a food/drink description or click one of the quick menu presets (e.g. *Espresso & Croissant*, *Chef's Pasta Carbonara*).
2. Click **🚀 Dispatch Order to Robot**.
3. If the robot is currently idle or docked, it immediately pops the order, switches state to `NAVIGATING`, and plans a collision-free route to the service point facing that table.
4. If orders are already in progress, the new request enters the **Pending Tasks** FIFO queue.

### 2. Managing the Live Delivery Queue
The **Live Delivery Queue & Monitoring** panel displays active and queued tasks:
- **Real-Time Modification**: Click any queued task in the pending listbox. The order details load into the inputs. Edit the target table or item description, then click **💾 Save Edit**. The task is dynamically updated in the manager without stopping the robot.
- **Task Deletion**: Select an order from the queue and click **🗑️ Delete Task** to remove it from the schedule.
- **Service Completion**: Upon arriving within range of the table, the robot enters `AT_TABLE` state, dwells for a handover period (simulating meal delivery), marks the task completed, and automatically pops the next delivery.

### 3. Auto-Docking and Resting Behavior
- **Autonomous Return-To-Dock**: When the delivery queue is empty and the robot has been idle for the timeout period (10 seconds), the auto-docking controller automatically commands the robot to navigate back to the resting dock station.
- **Manual Docking Control**: Click **⚓ Return-To-Dock** at any time to send the robot to the dock.
- **Emergency / Manual Stop**: Click **🛑 Stop Docking** to immediately halt the robot base and return the state to `IDLE`.
- **New Order Preemption**: If a delivery order is placed while the robot is en route to the dock (or resting at the dock), docking is **instantly cancelled**, the new order is dispatched, and the robot immediately pivots to deliver the meal.

---

## 🍽️ Restaurant Layout & Predefined Waypoints

### Grand Promenade (`restaurant.world`)
Features **24 Dining Tables**, a **Kitchen Pickup Counter**, and a Southeast **Resting Dock**:

| Service Zone | Waypoints | Description |
| :--- | :--- | :--- |
| **Resting Dock Station** | `Dock` | Southeast corner resting dock & staging zone `(7.06, -12.00)` |
| **Kitchen / Pickup** | `Kitchen/Pickup` | West central counter for food/drink pickup `(-9.60, -1.39)` |
| **North Terrace** | `Table 0` .. `Table 5` | Dining tables along northern service aisle ($y = 0.50$) |
| **Mid Lounge** | `Table 6` .. `Table 11` | Dining tables along main central promenade ($y = -3.10$) |
| **Central Salon** | `Table 12` .. `Table 17` | Dining tables facing southern walkway ($y = -5.85$) |
| **South Wing** | `Table 18` .. `Table 23` | Dining tables along southern service aisle ($y = -9.45$) |

All waypoint coordinates and orientations are configured in [`ros2_ws/src/cstam_navigation/config/waypoints.yaml`](file:///home/wass/cstan_tunibot/ros2_ws/src/cstam_navigation/config/waypoints.yaml).

### Dar Tunibot (`resto_arbi.world`)
Features **10 Dining Tables**, a **North Wing Kitchen**, and a West Wall **Resting Dock**:
- Configured in [`ros2_ws/src/cstam_navigation/config/resto_arbi_waypoints.yaml`](file:///home/wass/cstan_tunibot/ros2_ws/src/cstam_navigation/config/resto_arbi_waypoints.yaml).

---

## 📡 ROS 2 Communication Architecture

| Topic / Action Name | Type | Direction | Description |
| :--- | :--- | :--- | :--- |
| `/delivery_request` | `std_msgs/msg/String` (JSON) | Simulator $\rightarrow$ Task Manager | Submits new delivery orders (`{"target": "...", "item": "..."}`) |
| `/delivery_task_action` | `std_msgs/msg/String` (JSON) | Simulator $\rightarrow$ Task Manager | Queue operations (`{"action": "modify"\|"delete"\|"stop_dock", ...}`) |
| `/dock_command` | `std_msgs/msg/String` | Controller / UI $\rightarrow$ Task Manager | Commands return to dock (`"DOCK_NOW:..."`) or halt (`"STOP_DOCK"`) |
| `/dock_state` | `std_msgs/msg/Bool` | Task Manager $\rightarrow$ Simulator / Ctrl | Real-time dock status (`true` = docked, `false` = undocked) |
| `/delivery_queue_status` | `std_msgs/msg/String` (JSON) | Task Manager $\rightarrow$ Simulator / Ctrl | Live queue status, current task, pending orders, and completed count |
| `/robot_system_state` | `std_msgs/msg/String` | Task Manager $\rightarrow$ Simulator | Current state (`IDLE`, `NAVIGATING`, `AT_TABLE`, `DOCKING`, `DOCKED`) |
| `/navigate_to_pose` | `nav2_msgs/action/NavigateToPose` | Task Manager $\rightarrow$ Nav2 | Action interface dispatching target waypoints to Nav2 planner |
| `/cmd_vel` | `geometry_msgs/msg/Twist` | Nav2 / Task Manager $\rightarrow$ Diff-Drive | Mobile base velocity commands and braking |
| `/scan` | `sensor_msgs/msg/LaserScan` | LiDAR $\rightarrow$ Nav2 / AMCL | 2D LiDAR range data for obstacle avoidance and localization |

---

## 📁 Repository Structure

```
cstan_tunibot/
├── delivery_simulator_ui.py        # Native Mission Control Simulator (Tkinter GUI & CLI)
├── run_autonomous_system.sh        # Master launch script (Gazebo + Nav2 + AMCL + RViz2 + Core)
├── run_delivery_simulator.sh       # Launch script for Delivery Simulator Interface
├── run_mapping_demo.sh             # SLAM mapping demonstration launch script
├── save_map.sh                     # Utility script to export active SLAM map
├── test_system.py                  # Automated system verification test suite
├── docs/
│   ├── CSTAM-BOOK.pdf              # Technical manual and reference documentation
│   └── README.md                   # Documentation guide
└── ros2_ws/
    └── src/
        ├── cstam_core/             # Task Queue Manager, Docking Controller & Launchers
        ├── cstam_gazebo/           # 3D Gazebo worlds, BellaBot URDF model, and meshes
        └── cstam_navigation/       # Nav2 configuration, AMCL parameters, maps, and waypoints
```
