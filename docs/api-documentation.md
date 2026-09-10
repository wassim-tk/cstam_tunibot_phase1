# CSTAM-TUNIBOT Web Bridge API Documentation

The `cstam_web_bridge` module provides RESTful HTTP endpoints and a real-time WebSocket telemetry stream bridging user interfaces to the underlying ROS 2 graph.

---

## 1. REST API Specification

### Base URL: `http://localhost:8000/api`

### 1. System Health Check
- **Endpoint**: `GET /api/health`
- **Description**: Returns web bridge service availability and server timestamp.
- **Response `200 OK`**:
```json
{
  "status": "ok",
  "service": "CSTAM Web Bridge",
  "timestamp": 1725949200.0
}
```

---

### 2. Robot Status & Pose Telemetry
- **Endpoint**: `GET /api/status`
- **Description**: Returns live robot coordinates, battery level, active state, and current task.
- **Response `200 OK`**:
```json
{
  "robot_pose": {
    "x": -4.0,
    "y": -4.0,
    "yaw": 0.0
  },
  "battery_percentage": 98.5,
  "robot_state": "idle",
  "current_task": null,
  "queue_length": 0,
  "waypoints": ["Dock", "Kitchen/Pickup", "Table 1", "Table 2", "Table 3"]
}
```

---

### 3. Get Predefined Waypoints
- **Endpoint**: `GET /api/waypoints`
- **Description**: Returns map coordinates for all target delivery locations.
- **Response `200 OK`**:
```json
{
  "Dock": { "x": -4.0, "y": -4.0, "type": "dock" },
  "Kitchen/Pickup": { "x": -3.5, "y": 3.5, "type": "pickup" },
  "Table 1": { "x": 3.0, "y": 3.5, "type": "delivery" },
  "Table 2": { "x": 3.5, "y": -2.5, "type": "delivery" },
  "Table 3": { "x": 1.0, "y": -3.5, "type": "delivery" }
}
```

---

### 4. Submit Delivery Request
- **Endpoint**: `POST /api/delivery`
- **Description**: Submits a new delivery request into the task manager queue.
- **Request Body**:
```json
{
  "target": "Table 1",
  "item": "Espresso & Muffin"
}
```
- **Response `200 OK`**:
```json
{
  "success": true,
  "task": {
    "id": "TASK-0001",
    "target": "Table 1",
    "item": "Espresso & Muffin",
    "status": "queued",
    "created_at": 1725949210.0,
    "completed_at": null
  }
}
```
- **Response `400 Bad Request`**:
```json
{
  "detail": "Unknown target location 'Table 99'"
}
```

---

### 5. Get Delivery Task Queue
- **Endpoint**: `GET /api/queue`
- **Description**: Returns current active task, pending FIFO queue, and historical tasks.
- **Response `200 OK`**:
```json
{
  "current_task": {
    "id": "TASK-0001",
    "target": "Table 1",
    "item": "Espresso & Muffin",
    "status": "en_route"
  },
  "queue": [
    {
      "id": "TASK-0002",
      "target": "Table 2",
      "item": "Fresh Orange Juice",
      "status": "queued"
    }
  ],
  "task_history": []
}
```

---

### 6. Clear Task Queue
- **Endpoint**: `DELETE /api/queue`
- **Description**: Clears all pending delivery tasks from queue.
- **Response `200 OK`**:
```json
{
  "success": true,
  "message": "Delivery task queue cleared."
}
```

---

### 7. Trigger Manual Dock Command
- **Endpoint**: `POST /api/dock`
- **Description**: Queues immediate return to dock command.
- **Response `200 OK`**:
```json
{
  "success": true,
  "message": "Manual dock command queued."
}
```

---

### 8. Toggle Dynamic Obstacle Simulation
- **Endpoint**: `POST /api/obstacle/trigger`
- **Description**: Activates or deactivates dynamic walking human obstacle in Gazebo world.
- **Request Body**:
```json
{
  "active": true
}
```
- **Response `200 OK`**:
```json
{
  "success": true,
  "dynamic_obstacle_active": true
}
```

---

## 2. WebSocket Telemetry Stream

- **URL**: `ws://localhost:8000/ws/telemetry`
- **Description**: Real-time 2Hz state broadcast containing robot pose, battery voltage, active task, queue, and obstacle state.
- **Payload Schema**:
```json
{
  "timestamp": 1725949215.5,
  "robot_pose": { "x": 1.25, "y": 2.10, "yaw": 0.45 },
  "battery_percentage": 97.2,
  "voltage": 12.52,
  "robot_state": "navigating",
  "current_task": {
    "id": "TASK-0001",
    "target": "Table 1",
    "item": "Espresso & Muffin",
    "status": "en_route"
  },
  "queue_length": 1,
  "queue": [ ... ],
  "completed_tasks": [ ... ],
  "waypoints": { ... },
  "dynamic_obstacle": {
    "active": true,
    "pose": { "x": 0.5, "y": -1.0 }
  }
}
```
