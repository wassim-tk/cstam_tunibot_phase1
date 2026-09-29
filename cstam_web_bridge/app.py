#!/usr/bin/env python3
"""
CSTAM Waiter Robot Web Command Center & Telemetry Bridge
- 3D Waiter Robot with 3 Serving Shelves
- Real-time Obstacle Avoidance & Doorway Path Planning
- Physically-Accurate 24V Li-ion Battery Model
- REST & WebSocket Live Dashboard APIs
"""

import sys
import os
import json
import time
import math
import random
import asyncio
from typing import Optional, List, Dict, Tuple, Any
from contextlib import asynccontextmanager
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel

# Add ros2_ws/src/cstam_core to path for core task manager & battery simulator logic
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'ros2_ws', 'src', 'cstam_core')))

from cstam_core.delivery_task_manager import TaskQueueManager, DEFAULT_WAYPOINTS
from cstam_core.battery_simulator import BatterySimulator
from cstam_core.docking_controller import AutoDockingController

# Instantiate Core Managers & Physical Battery Simulator
task_manager = TaskQueueManager()
battery_sim = BatterySimulator(initial_percentage=100.0, time_scale=20.0)
dock_controller = AutoDockingController(idle_timeout=15.0, low_battery_threshold=20.0, full_charge_threshold=90.0)

# Optional ROS 2 Real-Time Bridge to Gazebo Sim /cmd_vel
try:
    import rclpy
    from geometry_msgs.msg import Twist
    HAVE_ROS2 = True
except ImportError:
    HAVE_ROS2 = False

_ros_node = None
_cmd_vel_pub = None

def init_ros2_bridge():
    global _ros_node, _cmd_vel_pub
    if not HAVE_ROS2:
        return
    try:
        if not rclpy.ok():
            rclpy.init()
        _ros_node = rclpy.create_node('cstam_web_bridge_motion')
        _cmd_vel_pub = _ros_node.create_publisher(Twist, '/cmd_vel', 10)
        import threading
        ros_thread = threading.Thread(target=lambda: rclpy.spin(_ros_node), daemon=True)
        ros_thread.start()
        print("✔ Connected to ROS 2: /cmd_vel commands will drive 3D robot in Gazebo")
    except Exception as e:
        print(f"Notice: Running web bridge in standalone simulation mode ({e})")

def publish_cmd_vel(linear_x: float, angular_z: float):
    global _cmd_vel_pub
    if _cmd_vel_pub is not None:
        try:
            msg = Twist()
            msg.linear.x = float(linear_x)
            msg.angular.z = float(angular_z)
            _cmd_vel_pub.publish(msg)
        except Exception:
            pass

import heapq
try:
    import numpy as np
    HAVE_NUMPY = True
except ImportError:
    HAVE_NUMPY = False

# Map and Navigation Grid Setup
MAP_PGM_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'ros2_ws', 'src', 'cstam_navigation', 'maps', 'cstam_map.pgm'))
LAYOUT_JSON_PATH = os.path.abspath(os.path.join(os.path.dirname(__file__), 'static', 'restaurant_layout.json'))

_map_loaded = False
_inflated_grid = None
_map_res = 0.20  # 20cm grid resolution for fast planning
_map_origin_x = -17.0
_map_max_y = 6.0
_grid_h = 125
_grid_w = 130

def init_navigation_map():
    global _map_loaded, _inflated_grid, _grid_h, _grid_w
    if _map_loaded or not HAVE_NUMPY or not os.path.exists(MAP_PGM_PATH):
        return
    try:
        with open(MAP_PGM_PATH, 'rb') as f:
            f.readline()
            f.readline()
            f.readline()
            raw = np.frombuffer(f.read(), dtype=np.uint8).reshape((500, 520))
        scale = 4
        _grid_h, _grid_w = 500 // scale, 520 // scale
        grid = np.zeros((_grid_h, _grid_w), dtype=bool)
        for r in range(_grid_h):
            for c in range(_grid_w):
                block = raw[r*scale:(r+1)*scale, c*scale:(c+1)*scale]
                grid[r, c] = np.all(block == 254)
        _inflated_grid = grid.copy()
        for r in range(1, _grid_h - 1):
            for c in range(1, _grid_w - 1):
                if not grid[r, c]:
                    _inflated_grid[max(0, r-1):min(_grid_h, r+2), max(0, c-1):min(_grid_w, c+2)] = False
        _map_loaded = True
    except Exception as e:
        print(f"Notice: Navigation map loaded with fallback: {e}")

init_navigation_map()

# Simulated Waiter Robot State Variables (Spawned at Dock in West Service Hallway)
robot_pose = {"x": -14.0, "y": -2.0, "yaw": 0.0}
dynamic_obstacle_active = False
dynamic_obstacle_pose = {"x": -14.0, "y": 0.0}
dynamic_obstacle_target = {"x": -8.0, "y": -4.0}
current_route_waypoints = []
active_avoidance = False
auto_charge_at_dock = True  # Option: When robot is at the dock, it automatically starts charging

# BellaBot 3-Tier Shelf Trays
shelves_state: Dict[str, Dict[str, Any]] = {
    "shelf_1": {"name": "Lower Shelf (Heavy Dishes & Platters)", "item": None, "status": "empty"},
    "shelf_2": {"name": "Middle Shelf (Hot Entrees & Mains)", "item": None, "status": "empty"},
    "shelf_3": {"name": "Upper Shelf (Drinks & Desserts)", "item": None, "status": "empty"}
}


# Pydantic Schemas
class DeliveryRequest(BaseModel):
    target: str
    item: Optional[str] = "General Item"

class QueueCancelRequest(BaseModel):
    task_id: Optional[str] = None

class ObstacleToggleRequest(BaseModel):
    active: bool

class DockChargeOptionRequest(BaseModel):
    auto_charge: Optional[bool] = None


# WebSocket Connection Manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                pass

ws_manager = ConnectionManager()


def plan_restaurant_path(start_pos, goal_pos):
    """
    Computes collision-free A* route through restaurant.world corridors and aisles.
    """
    init_navigation_map()
    if _inflated_grid is None:
        return [{"x": goal_pos["x"], "y": goal_pos["y"]}]

    sx, sy = start_pos["x"], start_pos["y"]
    gx, gy = goal_pos["x"], goal_pos["y"]

    sr = int((_map_max_y - sy) / _map_res)
    sc = int((sx - _map_origin_x) / _map_res)
    gr = int((_map_max_y - gy) / _map_res)
    gc = int((gx - _map_origin_x) / _map_res)

    sr, sc = max(0, min(_grid_h - 1, sr)), max(0, min(_grid_w - 1, sc))
    gr, gc = max(0, min(_grid_h - 1, gr)), max(0, min(_grid_w - 1, gc))

    # Clamp to nearest free cell if starting or ending on boundary
    for r_var, c_var in [('sr', 'sc'), ('gr', 'gc')]:
        r_val, c_val = locals()[r_var], locals()[c_var]
        if not _inflated_grid[r_val, c_val]:
            found = False
            for rad in range(1, 15):
                for dr in range(-rad, rad + 1):
                    for dc in range(-rad, rad + 1):
                        nr, nc = r_val + dr, c_val + dc
                        if 0 <= nr < _grid_h and 0 <= nc < _grid_w and _inflated_grid[nr, nc]:
                            if r_var == 'sr': sr, sc = nr, nc
                            else: gr, gc = nr, nc
                            found = True
                            break
                    if found: break
                if found: break

    open_set: List[Tuple[float, int, int]] = [(0.0, sr, sc)]
    came_from: Dict[Tuple[int, int], Tuple[int, int]] = {}
    g_score: Dict[Tuple[int, int], float] = {(sr, sc): 0.0}

    while open_set:
        cost, r, c = heapq.heappop(open_set)
        if (r, c) == (gr, gc):
            raw_path = []
            curr = (r, c)
            while curr in came_from:
                px = _map_origin_x + (curr[1] + 0.5) * _map_res
                py = _map_max_y - (curr[0] + 0.5) * _map_res
                raw_path.append({"x": round(px, 2), "y": round(py, 2)})
                curr = came_from[curr]
            raw_path.reverse()
            # Prune waypoints for smooth navigation: every 3rd waypoint + goal
            pruned = [raw_path[i] for i in range(0, len(raw_path), 3)]
            pruned.append({"x": round(gx, 2), "y": round(gy, 2)})
            return pruned

        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (-1, 1), (1, -1), (1, 1)]:
            nr, nc = r + dr, c + dc
            if 0 <= nr < _grid_h and 0 <= nc < _grid_w and _inflated_grid[nr, nc]:
                move_cost = 1.414 if dr != 0 and dc != 0 else 1.0
                new_g = g_score[(r, c)] + move_cost
                if (nr, nc) not in g_score or new_g < g_score[(nr, nc)]:
                    g_score[(nr, nc)] = new_g
                    h_cost = math.hypot(nr - gr, nc - gc)
                    heapq.heappush(open_set, (new_g + h_cost, nr, nc))
                    came_from[(nr, nc)] = (r, c)

    return [{"x": gx, "y": gy}]

# Alias for backwards compatibility
plan_doorway_path = plan_restaurant_path


def assign_shelf_for_delivery(item_name: str) -> str:
    """Assigns delivered items to one of the 3 waiter robot shelves."""
    item_lower = item_name.lower()
    if any(k in item_lower for k in ["espresso", "coffee", "tea", "water", "juice", "drink"]):
        chosen = "shelf_3"  # Upper shelf for drinks
    elif any(k in item_lower for k in ["bagel", "croissant", "sandwich", "dessert"]):
        chosen = "shelf_2"  # Middle shelf for light entrees
    else:
        chosen = "shelf_1"  # Lower shelf for main dishes / general trays

    if shelves_state[chosen]["status"] == "empty":
        shelves_state[chosen]["item"] = item_name
        shelves_state[chosen]["status"] = "loaded"
        return chosen

    # Fallback to any empty shelf
    for s_id in ["shelf_1", "shelf_2", "shelf_3"]:
        if shelves_state[s_id]["status"] == "empty":
            shelves_state[s_id]["item"] = item_name
            shelves_state[s_id]["status"] = "loaded"
            return s_id
    return "shelf_2"


def clear_shelves():
    for s_id in shelves_state:
        shelves_state[s_id]["item"] = None
        shelves_state[s_id]["status"] = "empty"





async def simulation_telemetry_loop():
    """
    Continuous background loop:
    1. Realistic physical battery modeling (OCV, load sag, CC-CV charge).
    2. Dynamic obstacle animation.
    3. Collision-avoiding doorway navigation.
    4. Dynamic pedestrian avoidance / yielding.
    5. Live WebSocket state broadcast.
    """
    global robot_pose, dynamic_obstacle_active, dynamic_obstacle_pose, current_route_waypoints, active_avoidance

    dt = 0.4
    target_cache = None

    while True:
        await asyncio.sleep(dt)

        # 1. Update Dynamic Obstacle (Walking Human roaming randomly all over the map)
        if dynamic_obstacle_active:
            dx_obs = dynamic_obstacle_target["x"] - dynamic_obstacle_pose["x"]
            dy_obs = dynamic_obstacle_target["y"] - dynamic_obstacle_pose["y"]
            dist_to_obs_target = math.hypot(dx_obs, dy_obs)

            if dist_to_obs_target < 0.4:
                # Arrived at waypoint, select a new random destination across the restaurant floor
                dynamic_obstacle_target["x"] = round(random.uniform(-15.5, 7.0), 2)
                dynamic_obstacle_target["y"] = round(random.uniform(-17.0, 4.5), 2)
            else:
                # Walk smoothly toward current random target (~0.18m/step)
                step_obs = min(0.18, dist_to_obs_target)
                angle_obs = math.atan2(dy_obs, dx_obs)
                dynamic_obstacle_pose["x"] = round(dynamic_obstacle_pose["x"] + step_obs * math.cos(angle_obs), 2)
                dynamic_obstacle_pose["y"] = round(dynamic_obstacle_pose["y"] + step_obs * math.sin(angle_obs), 2)

        # Check if robot is physically at or near the Dock station
        dock_wp = DEFAULT_WAYPOINTS["Dock"]
        dist_to_dock = math.hypot(robot_pose["x"] - dock_wp["x"], robot_pose["y"] - dock_wp["y"])
        is_at_dock = (dist_to_dock < 1.0) or (math.hypot(robot_pose["x"] - (-14.0), robot_pose["y"] - (-2.0)) < 1.0)

        # 2. Update Physical Battery State
        is_moving = task_manager.robot_state in ["navigating", "en_route", "docking", "avoiding_obstacle"]
        battery_sim.is_moving = is_moving

        # Option: When the robot is in the dock, start charging if auto_charge_at_dock is enabled
        if is_at_dock and not is_moving:
            if auto_charge_at_dock:
                battery_sim.is_docked = True
                if task_manager.robot_state not in ["charging", "docked"]:
                    task_manager.robot_state = "charging" if battery_sim.percentage < 99.9 else "docked"
            else:
                battery_sim.is_docked = (task_manager.robot_state in ["docked", "charging"])
        else:
            battery_sim.is_docked = False

        battery_sim.is_accelerating = active_avoidance
        curr_bat = battery_sim.update(dt=dt)
        task_manager.update_battery(curr_bat)

        # Update charging state when docked and auto_charge enabled
        if is_at_dock and not is_moving and auto_charge_at_dock:
            if curr_bat >= 100.0:
                task_manager.robot_state = "docked"
            elif task_manager.robot_state not in ["navigating", "docking"]:
                task_manager.robot_state = "charging"

        # 3. Check for Low Battery Auto-Dock Preemption (< 20%)
        if curr_bat < dock_controller.low_battery_threshold and task_manager.robot_state not in ["docked", "charging", "docking"]:
            task_manager.robot_state = "docking"
            if not task_manager.current_task or task_manager.current_task.get("target") != "Dock":
                dock_task = {
                    "id": "TASK-AUTO-DOCK",
                    "target": "Dock",
                    "item": "Low Battery Preemptive Docking",
                    "status": "en_route"
                }
                task_manager.current_task = dock_task
                current_route_waypoints = []
                target_cache = None

        # 4. Dispatch Next Task if Idle
        if not task_manager.current_task and task_manager.queue:
            if curr_bat >= dock_controller.low_battery_threshold:
                next_t = task_manager.get_next_task()
                if next_t:
                    task_manager.robot_state = "navigating"
                    current_route_waypoints = []
                    target_cache = None
                    assign_shelf_for_delivery(str(next_t.get("item") or "Dishes"))

        # 5. Collision-Free Path Planning & Movement
        active_avoidance = False

        if task_manager.current_task:
            target_name = task_manager.current_task["target"]
            target_wp = DEFAULT_WAYPOINTS.get(target_name, DEFAULT_WAYPOINTS["Dock"])

            # Compute route through doorway if starting a new target
            if target_cache != target_name or not current_route_waypoints:
                current_route_waypoints = plan_doorway_path(robot_pose, target_wp)
                target_cache = target_name

            if current_route_waypoints:
                next_pt = current_route_waypoints[0]
                dx = next_pt["x"] - robot_pose["x"]
                dy = next_pt["y"] - robot_pose["y"]
                dist_to_next = math.hypot(dx, dy)

                if dist_to_next > 0.15:
                    step = min(0.24, dist_to_next)
                    desired_angle = math.atan2(dy, dx)

                    # --- DYNAMIC OBSTACLE AVOIDANCE ENGINE ---
                    dist_to_obs = math.hypot(
                        robot_pose["x"] - dynamic_obstacle_pose["x"],
                        robot_pose["y"] - dynamic_obstacle_pose["y"]
                    )

                    if dynamic_obstacle_active and dist_to_obs < 1.35:
                        # Obstacle detected in vicinity!
                        active_avoidance = True

                        if dist_to_obs < 0.70:
                            # CRITICAL PROXIMITY: Safely yield / stop motion
                            task_manager.robot_state = "yielding"
                            step = 0.0
                        else:
                            # AVOIDANCE MANEUVER: Compute lateral evasive steering
                            task_manager.robot_state = "avoiding_obstacle"
                            # Steer perpendicular away from the obstacle
                            repulsive_x = robot_pose["x"] - dynamic_obstacle_pose["x"]
                            repulsive_y = robot_pose["y"] - dynamic_obstacle_pose["y"]
                            rep_mag = max(0.01, math.hypot(repulsive_x, repulsive_y))

                            # Blend desired path direction with repulsive force
                            avoid_vx = math.cos(desired_angle) + 0.8 * (repulsive_x / rep_mag)
                            avoid_vy = math.sin(desired_angle) + 0.8 * (repulsive_y / rep_mag)
                            avoid_angle = math.atan2(avoid_vy, avoid_vx)

                            desired_angle = avoid_angle
                            step = min(0.18, step)
                    else:
                        task_manager.robot_state = "docking" if target_name == "Dock" else "navigating"

                    # Execute motion step
                    if step > 0.0:
                        robot_pose["x"] += step * math.cos(desired_angle)
                        robot_pose["y"] += step * math.sin(desired_angle)
                        robot_pose["yaw"] = desired_angle

                        # Transmit motion velocity to Gazebo 3D simulation /cmd_vel
                        angle_diff = (desired_angle - robot_pose["yaw"] + math.pi) % (2 * math.pi) - math.pi
                        if abs(angle_diff) > 0.35:
                            publish_cmd_vel(0.08, max(-1.0, min(1.0, 2.0 * angle_diff)))
                        else:
                            publish_cmd_vel(min(0.5, step / dt), max(-1.0, min(1.0, 1.5 * angle_diff)))
                    else:
                        publish_cmd_vel(0.0, 0.0)
                else:
                    # Waypoint reached, advance to next segment
                    current_route_waypoints.pop(0)

                    # Destination reached
                    if not current_route_waypoints:
                        robot_pose["x"] = target_wp["x"]
                        robot_pose["y"] = target_wp["y"]
                        publish_cmd_vel(0.0, 0.0)

                        if target_name == "Dock":
                            clear_shelves()
                            if auto_charge_at_dock and curr_bat < 99.9:
                                task_manager.robot_state = "charging"
                            else:
                                task_manager.robot_state = "docked"

                            if curr_bat >= dock_controller.full_charge_threshold and task_manager.queue:
                                task_manager.complete_current_task(success=True)
                                task_manager.robot_state = "idle"
                            elif curr_bat >= 99.9:
                                task_manager.complete_current_task(success=True)
                        else:
                            task_manager.complete_current_task(success=True)
                            clear_shelves()
                            task_manager.robot_state = "idle"
        else:
            publish_cmd_vel(0.0, 0.0)
            if is_at_dock and not is_moving:
                if auto_charge_at_dock and curr_bat < 99.9:
                    task_manager.robot_state = "charging"
                else:
                    task_manager.robot_state = "docked"
            elif task_manager.robot_state not in ["docked", "charging"]:
                task_manager.robot_state = "idle"

        # 6. Broadcast Comprehensive Live Telemetry
        telemetry = {
            "timestamp": time.time(),
            "robot_pose": robot_pose,
            "robot_type": "BellaBot (3-Tier Autonomous Service Robot)",
            "battery_percentage": round(curr_bat, 1),
            "voltage": round(battery_sim.voltage, 2),
            "current_amps": round(abs(battery_sim.current), 2),
            "power_watts": round(battery_sim.power, 1),
            "temperature_c": round(battery_sim.temperature, 1),
            "robot_state": task_manager.robot_state,
            "is_docked": battery_sim.is_docked,
            "is_at_dock": is_at_dock,
            "auto_charge_at_dock": auto_charge_at_dock,
            "charging_active": battery_sim.is_docked and curr_bat < 100.0,
            "avoidance_active": active_avoidance,
            "current_task": task_manager.current_task,
            "shelves": shelves_state,
            "planned_path": current_route_waypoints,
            "queue_length": len(task_manager.queue),
            "queue": list(task_manager.queue),
            "completed_tasks": task_manager.task_history[-5:],
            "waypoints": DEFAULT_WAYPOINTS,
            "map_bounds": {"min_x": -17.0, "max_x": 9.0, "min_y": -19.0, "max_y": 6.0},
            "dynamic_obstacle": {
                "active": dynamic_obstacle_active,
                "pose": dynamic_obstacle_pose
            }
        }

        await ws_manager.broadcast(telemetry)


# Lifespan Context Manager
@asynccontextmanager
async def lifespan(app_instance: FastAPI):
    init_ros2_bridge()
    sim_task = asyncio.create_task(simulation_telemetry_loop())
    yield
    publish_cmd_vel(0.0, 0.0)
    sim_task.cancel()

app = FastAPI(
    title="CSTAM 3D Waiter Service Robot API",
    version="2.0.0",
    description="Mission control & telemetry for autonomous multi-shelf restaurant waiter robot",
    lifespan=lifespan
)

# REST API Endpoints
@app.get("/api/health")
def get_health():
    return {"status": "ok", "service": "CSTAM Waiter Robot Web Bridge", "timestamp": time.time()}

@app.get("/api/status")
def get_status():
    dock_wp = DEFAULT_WAYPOINTS["Dock"]
    dist_to_dock = math.hypot(robot_pose["x"] - dock_wp["x"], robot_pose["y"] - dock_wp["y"])
    is_at_dock = (dist_to_dock < 1.0) or (math.hypot(robot_pose["x"] - (-14.0), robot_pose["y"] - (-2.0)) < 1.0)
    return {
        "robot_pose": robot_pose,
        "battery_percentage": round(battery_sim.percentage, 1),
        "voltage": round(battery_sim.voltage, 2),
        "current_amps": round(abs(battery_sim.current), 2),
        "power_watts": round(battery_sim.power, 1),
        "robot_state": task_manager.robot_state,
        "is_docked": battery_sim.is_docked,
        "is_at_dock": is_at_dock,
        "auto_charge_at_dock": auto_charge_at_dock,
        "charging_active": battery_sim.is_docked and battery_sim.percentage < 100.0,
        "current_task": task_manager.current_task,
        "shelves": shelves_state,
        "queue_length": len(task_manager.queue),
        "waypoints": list(DEFAULT_WAYPOINTS.keys())
    }

@app.get("/api/dock/charge_option")
def get_dock_charge_option():
    dock_wp = DEFAULT_WAYPOINTS["Dock"]
    dist_to_dock = math.hypot(robot_pose["x"] - dock_wp["x"], robot_pose["y"] - dock_wp["y"])
    is_at_dock = (dist_to_dock < 1.0) or (math.hypot(robot_pose["x"] - (-14.0), robot_pose["y"] - (-2.0)) < 1.0)
    return {
        "auto_charge_at_dock": auto_charge_at_dock,
        "is_docked": battery_sim.is_docked,
        "is_at_dock": is_at_dock,
        "robot_state": task_manager.robot_state,
        "battery_percentage": round(battery_sim.percentage, 1)
    }

@app.post("/api/dock/charge_option")
def set_dock_charge_option(req: Optional[DockChargeOptionRequest] = None):
    global auto_charge_at_dock
    if req and req.auto_charge is not None:
        auto_charge_at_dock = req.auto_charge
    else:
        auto_charge_at_dock = not auto_charge_at_dock

    dock_wp = DEFAULT_WAYPOINTS["Dock"]
    dist_to_dock = math.hypot(robot_pose["x"] - dock_wp["x"], robot_pose["y"] - dock_wp["y"])
    is_at_dock = (dist_to_dock < 1.0) or (math.hypot(robot_pose["x"] - (-14.0), robot_pose["y"] - (-2.0)) < 1.0)

    if is_at_dock:
        battery_sim.is_docked = auto_charge_at_dock
        if auto_charge_at_dock and battery_sim.percentage < 99.9:
            task_manager.robot_state = "charging"
        elif task_manager.robot_state == "charging":
            task_manager.robot_state = "docked"

    return {
        "success": True,
        "auto_charge_at_dock": auto_charge_at_dock,
        "is_docked": battery_sim.is_docked,
        "is_at_dock": is_at_dock,
        "robot_state": task_manager.robot_state,
        "battery_percentage": round(battery_sim.percentage, 1)
    }

@app.post("/api/dock/start_charge")
def start_dock_charge():
    dock_wp = DEFAULT_WAYPOINTS["Dock"]
    dist_to_dock = math.hypot(robot_pose["x"] - dock_wp["x"], robot_pose["y"] - dock_wp["y"])
    is_at_dock = (dist_to_dock < 1.0) or (math.hypot(robot_pose["x"] - (-14.0), robot_pose["y"] - (-2.0)) < 1.0)

    if not is_at_dock:
        # If not at dock, trigger return to dock
        task_manager.add_delivery_request("Dock", "Admin: Return to Dock to Charge")
        return {"success": True, "message": "Robot is not in the dock. Returning to Dock to start charging.", "robot_state": "docking"}

    battery_sim.is_docked = True
    task_manager.robot_state = "charging"
    return {"success": True, "message": "Charging initiated at dock.", "robot_state": "charging", "battery_percentage": round(battery_sim.percentage, 1)}

@app.get("/api/waypoints")
def get_waypoints():
    return DEFAULT_WAYPOINTS

@app.get("/api/map/layout")
def get_map_layout():
    if os.path.exists(LAYOUT_JSON_PATH):
        with open(LAYOUT_JSON_PATH, "r") as f:
            return json.load(f)
    return {"walls": [], "tables": []}

@app.post("/api/delivery")
def submit_delivery(req: DeliveryRequest):
    res = task_manager.add_delivery_request(req.target, req.item or "General Item")
    if not res["success"]:
        raise HTTPException(status_code=400, detail=res["error"])
    return res

@app.get("/api/queue")
def get_queue():
    return {
        "current_task": task_manager.current_task,
        "queue": list(task_manager.queue),
        "task_history": task_manager.task_history
    }

@app.delete("/api/queue")
def clear_queue():
    task_manager.queue.clear()
    clear_shelves()
    return {"success": True, "message": "Delivery task queue and shelves cleared."}

@app.post("/api/dock")
def trigger_dock():
    dock_task = task_manager.add_delivery_request("Dock", "Manual Admin Command: Return to Dock")
    return {"success": True, "message": "Manual dock command queued.", "task": dock_task}

@app.post("/api/obstacle/trigger")
def toggle_obstacle(req: ObstacleToggleRequest):
    global dynamic_obstacle_active
    dynamic_obstacle_active = req.active
    return {"success": True, "dynamic_obstacle_active": dynamic_obstacle_active}

@app.post("/api/battery/low")
def trigger_low_battery():
    battery_sim.percentage = 15.0
    battery_sim.soc = 0.15
    battery_sim._calculate_ocv()
    battery_sim.voltage = battery_sim.ocv
    task_manager.update_battery(15.0)
    return {
        "success": True,
        "message": "Low battery state (15%) manually triggered. Autonomous docking initiated.",
        "battery_percentage": 15.0
    }


# WebSocket Endpoint
@app.websocket("/ws/telemetry")
async def websocket_endpoint(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)


# Mount Static Files & Serve HTML Dashboard
static_dir = os.path.join(os.path.dirname(__file__), 'static')
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/", response_class=HTMLResponse)
def index_page():
    index_file = os.path.join(static_dir, 'index.html')
    if os.path.exists(index_file):
        return FileResponse(index_file)
    return HTMLResponse("<h1>CSTAM Waiter Robot Bridge Running</h1>")


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
