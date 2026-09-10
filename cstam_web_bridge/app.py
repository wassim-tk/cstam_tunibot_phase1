#!/usr/bin/env python3
import sys
import os
import json
import time
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
    title="CSTAM Autonomous Indoor Delivery Robot API",
    version="1.0.0",
    description="REST & WebSocket API for CSTAM TuniBot delivery task management and robot telemetry"
)

# Instantiate Core Managers & Simulators
task_manager = TaskQueueManager()
battery_sim = BatterySimulator(initial_percentage=100.0, drain_rate_idle=0.03, drain_rate_nav=0.25, charge_rate=3.0)
dock_controller = AutoDockingController(idle_timeout=15.0, low_battery_threshold=20.0, full_charge_threshold=90.0)

# Simulated Robot State Variables
robot_pose = {"x": -4.0, "y": -4.0, "yaw": 0.0}
dynamic_obstacle_active = False
dynamic_obstacle_pose = {"x": 0.0, "y": -1.0}


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


# Background Telemetry & Simulation Loop
@app.on_event("startup")
async def start_background_sim():
    asyncio.create_task(simulation_telemetry_loop())


async def simulation_telemetry_loop():
    """
    Continuous background loop updating robot pose, battery simulation,
    task queue progress, and broadcasting live state over WebSockets.
    """
    global robot_pose, dynamic_obstacle_active, dynamic_obstacle_pose

    while True:
        await asyncio.sleep(0.5)

        # 1. Update Battery Simulation
        is_moving = task_manager.robot_state in ["navigating", "en_route", "docking"]
        battery_sim.is_moving = is_moving
        battery_sim.is_docked = (task_manager.robot_state == "docked")
        curr_bat = battery_sim.update(dt=0.5)
        task_manager.update_battery(curr_bat)

        # 2. Update Dynamic Obstacle Pose
        if dynamic_obstacle_active:
            t = time.time()
            dynamic_obstacle_pose["x"] = 2.0 * math_sin(t * 0.8)
            dynamic_obstacle_pose["y"] = -1.0

        # 3. Check for Low Battery Auto-Dock Preemption
        if curr_bat < dock_controller.low_battery_threshold and task_manager.robot_state not in ["docked", "charging", "docking"]:
            task_manager.robot_state = "docking"
            if not task_manager.current_task or task_manager.current_task.get("target") != "Dock":
                dock_task = {
                    "id": "TASK-AUTO-DOCK",
                    "target": "Dock",
                    "item": "Low battery auto-docking",
                    "status": "en_route"
                }
                task_manager.current_task = dock_task

        # 4. Dispatch next task if idle
        if not task_manager.current_task and task_manager.queue:
            if curr_bat >= dock_controller.low_battery_threshold:
                next_t = task_manager.get_next_task()
                if next_t:
                    task_manager.robot_state = "navigating"

        # 5. Move Robot towards Current Target if active
        if task_manager.current_task:
            target_name = task_manager.current_task["target"]
            target_wp = DEFAULT_WAYPOINTS.get(target_name, DEFAULT_WAYPOINTS["Dock"])
            
            dx = target_wp["x"] - robot_pose["x"]
            dy = target_wp["y"] - robot_pose["y"]
            dist = (dx**2 + dy**2)**0.5

            if dist > 0.15:
                step = min(0.25, dist)
                angle = math_atan2(dy, dx)
                robot_pose["x"] += step * math_cos(angle)
                robot_pose["y"] += step * math_sin(angle)
                robot_pose["yaw"] = angle
                task_manager.robot_state = "docking" if target_name == "Dock" else "navigating"
            else:
                # Arrived at destination
                robot_pose["x"] = target_wp["x"]
                robot_pose["y"] = target_wp["y"]

                if target_name == "Dock":
                    task_manager.robot_state = "docked"
                    if curr_bat >= dock_controller.full_charge_threshold:
                        task_manager.complete_current_task(success=True)
                        task_manager.robot_state = "idle"
                else:
                    task_manager.complete_current_task(success=True)
                    task_manager.robot_state = "idle"
        else:
            if task_manager.robot_state not in ["docked", "charging"]:
                task_manager.robot_state = "idle"

        # 6. Broadcast Telemetry state
        telemetry = {
            "timestamp": time.time(),
            "robot_pose": robot_pose,
            "battery_percentage": round(curr_bat, 1),
            "voltage": round(battery_sim.voltage, 2),
            "robot_state": task_manager.robot_state,
            "current_task": task_manager.current_task,
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


def math_sin(val):
    import math
    return math.sin(val)

def math_cos(val):
    import math
    return math.cos(val)

def math_atan2(y, x):
    import math
    return math.atan2(y, x)


# REST API Endpoints
@app.get("/api/health")
def get_health():
    return {"status": "ok", "service": "CSTAM Web Bridge", "timestamp": time.time()}

@app.get("/api/status")
def get_status():
    return {
        "robot_pose": robot_pose,
        "battery_percentage": round(battery_sim.percentage, 1),
        "robot_state": task_manager.robot_state,
        "current_task": task_manager.current_task,
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
    return {"success": True, "message": "Delivery task queue cleared."}

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
            data = await websocket.receive_text()
            # Can receive client commands if needed
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
    return HTMLResponse("<h1>CSTAM TuniBot Web Bridge API Running</h1><p>Visit <a href='/docs'>/docs</a> for Swagger API UI.</p>")


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
