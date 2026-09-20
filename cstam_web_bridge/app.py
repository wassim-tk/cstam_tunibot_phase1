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
import asyncio
from typing import Optional, List
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel

# Add ros2_ws/src/cstam_core to path for core task manager & battery simulator logic
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'ros2_ws', 'src', 'cstam_core')))

from cstam_core.delivery_task_manager import TaskQueueManager, DEFAULT_WAYPOINTS
from cstam_core.battery_simulator import BatterySimulator
from cstam_core.docking_controller import AutoDockingController

app = FastAPI(
    title="CSTAM 3D Waiter Service Robot API",
    version="2.0.0",
    description="Mission control & telemetry for autonomous multi-shelf restaurant waiter robot"
)

# Instantiate Core Managers & Physical Battery Simulator
task_manager = TaskQueueManager()
battery_sim = BatterySimulator(initial_percentage=100.0, time_scale=20.0)
dock_controller = AutoDockingController(idle_timeout=15.0, low_battery_threshold=20.0, full_charge_threshold=90.0)

# Simulated Waiter Robot State Variables
robot_pose = {"x": -4.0, "y": -4.0, "yaw": 0.0}
dynamic_obstacle_active = False
dynamic_obstacle_pose = {"x": 0.0, "y": -1.0}
current_route_waypoints = []
active_avoidance = False

# Waiter Robot 3-Tier Shelf Trays
shelves_state = {
    "shelf_1": {"name": "Lower Shelf (Heavy Dishes)", "item": None, "status": "empty"},
    "shelf_2": {"name": "Middle Shelf (Hot Entrees)", "item": None, "status": "empty"},
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


def plan_doorway_path(start_pos, goal_pos):
    """
    Plans collision-free path between rooms avoiding the partition wall at y=1.0.
    Crosses via the central doorway at (0.5, 1.0).
    """
    sx, sy = start_pos["x"], start_pos["y"]
    gx, gy = goal_pos["x"], goal_pos["y"]

    path = []
    crosses_partition = (sy < 0.9 and gy > 1.1) or (sy > 1.1 and gy < 0.9)

    if crosses_partition:
        if sy < 0.9:
            # Traveling South -> North: approach doorway from south, pass through, enter north
            path.append({"x": 0.5, "y": -0.2})
            path.append({"x": 0.5, "y": 1.0})
            path.append({"x": 0.5, "y": 2.2})
        else:
            # Traveling North -> South: approach doorway from north, pass through, enter south
            path.append({"x": 0.5, "y": 2.2})
            path.append({"x": 0.5, "y": 1.0})
            path.append({"x": 0.5, "y": -0.2})

    path.append({"x": gx, "y": gy})
    return path


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


# Background Telemetry & Navigation Loop
@app.on_event("startup")
async def start_background_sim():
    asyncio.create_task(simulation_telemetry_loop())


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

        # 1. Update Dynamic Obstacle (Walking Human crossing corridor at y = -1.0)
        if dynamic_obstacle_active:
            t = time.time()
            dynamic_obstacle_pose["x"] = round(2.2 * math.sin(t * 0.7), 2)
            dynamic_obstacle_pose["y"] = -1.0

        # 2. Update Physical Battery State
        is_moving = task_manager.robot_state in ["navigating", "en_route", "docking", "avoiding_obstacle"]
        battery_sim.is_moving = is_moving
        battery_sim.is_docked = (task_manager.robot_state == "docked")
        battery_sim.is_accelerating = active_avoidance
        curr_bat = battery_sim.update(dt=dt)
        task_manager.update_battery(curr_bat)

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
                    assign_shelf_for_delivery(next_t.get("item", "Dishes"))

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
                else:
                    # Waypoint reached, advance to next segment
                    current_route_waypoints.pop(0)

                    # Destination reached
                    if not current_route_waypoints:
                        robot_pose["x"] = target_wp["x"]
                        robot_pose["y"] = target_wp["y"]

                        if target_name == "Dock":
                            task_manager.robot_state = "docked"
                            clear_shelves()
                            if curr_bat >= dock_controller.full_charge_threshold:
                                task_manager.complete_current_task(success=True)
                                task_manager.robot_state = "idle"
                        else:
                            task_manager.complete_current_task(success=True)
                            clear_shelves()
                            task_manager.robot_state = "idle"
        else:
            if task_manager.robot_state not in ["docked", "charging"]:
                task_manager.robot_state = "idle"

        # 6. Broadcast Comprehensive Live Telemetry
        telemetry = {
            "timestamp": time.time(),
            "robot_pose": robot_pose,
            "robot_type": "Waiter Robot (3-Tier Shelves)",
            "battery_percentage": round(curr_bat, 1),
            "voltage": round(battery_sim.voltage, 2),
            "current_amps": round(abs(battery_sim.current), 2),
            "power_watts": round(battery_sim.power, 1),
            "temperature_c": round(battery_sim.temperature, 1),
            "robot_state": task_manager.robot_state,
            "avoidance_active": active_avoidance,
            "current_task": task_manager.current_task,
            "shelves": shelves_state,
            "planned_path": current_route_waypoints,
            "queue_length": len(task_manager.queue),
            "queue": list(task_manager.queue),
            "completed_tasks": task_manager.task_history[-5:],
            "waypoints": DEFAULT_WAYPOINTS,
            "dynamic_obstacle": {
                "active": dynamic_obstacle_active,
                "pose": dynamic_obstacle_pose
            }
        }

        await ws_manager.broadcast(telemetry)


# REST API Endpoints
@app.get("/api/health")
def get_health():
    return {"status": "ok", "service": "CSTAM Waiter Robot Web Bridge", "timestamp": time.time()}

@app.get("/api/status")
def get_status():
    return {
        "robot_pose": robot_pose,
        "battery_percentage": round(battery_sim.percentage, 1),
        "voltage": round(battery_sim.voltage, 2),
        "current_amps": round(abs(battery_sim.current), 2),
        "power_watts": round(battery_sim.power, 1),
        "robot_state": task_manager.robot_state,
        "current_task": task_manager.current_task,
        "shelves": shelves_state,
        "queue_length": len(task_manager.queue),
        "waypoints": list(DEFAULT_WAYPOINTS.keys())
    }

@app.get("/api/waypoints")
def get_waypoints():
    return DEFAULT_WAYPOINTS

@app.post("/api/delivery")
def submit_delivery(req: DeliveryRequest):
    res = task_manager.add_delivery_request(req.target, req.item)
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
