#!/usr/bin/env python3
from __future__ import annotations

import json
import time
import threading
from collections import deque

try:
    import rclpy
    from rclpy.node import Node
    from geometry_msgs.msg import PoseStamped
    from sensor_msgs.msg import BatteryState
    from std_msgs.msg import String, Bool
    HAVE_ROS2 = True
except ImportError:
    HAVE_ROS2 = False
    class Node:  # type: ignore
        def __init__(self, *args, **kwargs):
            pass
    class String: pass  # type: ignore
    class BatteryState: pass  # type: ignore
    class PoseStamped: pass  # type: ignore
    class Bool: pass  # type: ignore

try:
    from rclpy.action import ActionClient
    from nav2_msgs.action import NavigateToPose  # type: ignore
    HAVE_NAV2 = True
except ImportError:
    HAVE_NAV2 = False


# Predefined Waypoints matching restaurant.world layout
DEFAULT_WAYPOINTS = {
    "Dock": {"x": -12.5, "y": -2.0, "z": 0.0, "qx": 0.0, "qy": 0.0, "qz": 0.0, "qw": 1.0},
    "Kitchen/Pickup": {"x": -12.5, "y": 2.0, "z": 0.0, "qx": 0.0, "qy": 0.0, "qz": 0.0, "qw": 1.0},
    "Table 1": {"x": 0.34, "y": -6.24, "z": 0.0, "qx": 0.0, "qy": 0.0, "qz": 0.0, "qw": 1.0},
    "Table 2": {"x": -10.67, "y": -12.84, "z": 0.0, "qx": 0.0, "qy": 0.0, "qz": 0.0, "qw": 1.0},
    "Table 3": {"x": -10.71, "y": -14.55, "z": 0.0, "qx": 0.0, "qy": 0.0, "qz": 0.0, "qw": 1.0},
    "Table 4": {"x": -10.63, "y": -16.17, "z": 0.0, "qx": 0.0, "qy": 0.0, "qz": 0.0, "qw": 1.0},
    "Table 6": {"x": -8.28, "y": -4.65, "z": 0.0, "qx": 0.0, "qy": 0.0, "qz": 0.0, "qw": 1.0},
    "Table 8": {"x": -8.23, "y": -9.45, "z": 0.0, "qx": 0.0, "qy": 0.0, "qz": 0.0, "qw": 1.0},
    "Table 10": {"x": -6.08, "y": -6.31, "z": 0.0, "qx": 0.0, "qy": 0.0, "qz": 0.0, "qw": 1.0},
    "Table 14": {"x": -8.02, "y": 0.36, "z": 0.0, "qx": 0.0, "qy": 0.0, "qz": 0.0, "qw": 1.0},
    "Table 18": {"x": -8.10, "y": -1.74, "z": 0.0, "qx": 0.0, "qy": 0.0, "qz": 0.0, "qw": 1.0},
    "Table 24": {"x": 0.72, "y": 1.45, "z": 0.0, "qx": 0.0, "qy": 0.0, "qz": 0.0, "qw": 1.0},
    "Table 34": {"x": 3.74, "y": 3.01, "z": 0.0, "qx": 0.0, "qy": 0.0, "qz": 0.0, "qw": 1.0},
}


class TaskQueueManager:
    """
    Core Task Queue and State Controller logic.
    Decoupled from ROS 2 middleware for high testability and reliability.
    """
    def __init__(self, waypoints=None, low_battery_threshold=20.0, charge_resume_threshold=90.0):
        self.waypoints = waypoints or DEFAULT_WAYPOINTS
        self.queue = deque()
        self.current_task = None
        self.task_history = []
        self.robot_state = "idle"  # idle, navigating, docked, charging, low_battery_rerouting
        self.battery_percentage = 100.0
        self.low_battery_threshold = float(low_battery_threshold)
        self.charge_resume_threshold = float(charge_resume_threshold)
        self.task_id_counter = 1
        self.lock = threading.Lock()

    def add_delivery_request(self, target_location: str, item_description: str = "") -> dict:
        with self.lock:
            if target_location not in self.waypoints and target_location.lower() != "dock":
                return {"success": False, "error": f"Unknown target location '{target_location}'"}
            
            task = {
                "id": f"TASK-{self.task_id_counter:04d}",
                "target": target_location,
                "item": item_description or "General Delivery",
                "status": "queued",
                "created_at": time.time(),
                "completed_at": None
            }
            self.task_id_counter += 1
            self.queue.append(task)
            return {"success": True, "task": task}

    def get_next_task(self):
        with self.lock:
            if not self.queue:
                return None
            
            # Check low battery condition before dispatching normal delivery
            if self.battery_percentage < self.low_battery_threshold:
                return {
                    "id": "TASK-DOCK-AUTO",
                    "target": "Dock",
                    "item": "Auto-docking due to low battery",
                    "status": "queued",
                    "is_dock_task": True
                }
            
            task = self.queue.popleft()
            task["status"] = "en_route"
            self.current_task = task
            return task

    def update_battery(self, percentage: float):
        with self.lock:
            self.battery_percentage = float(percentage)
            if self.battery_percentage < self.low_battery_threshold and self.robot_state not in ["docked", "charging", "low_battery_rerouting"]:
                self.robot_state = "low_battery_rerouting"

    def complete_current_task(self, success=True):
        with self.lock:
            if self.current_task:
                self.current_task["status"] = "completed" if success else "failed"
                self.current_task["completed_at"] = time.time()
                self.task_history.append(self.current_task)
                finished_task = self.current_task
                self.current_task = None
                return finished_task
            return None

    def get_status_summary(self):
        with self.lock:
            return {
                "robot_state": self.robot_state,
                "battery_percentage": round(self.battery_percentage, 1),
                "current_task": self.current_task,
                "queue_length": len(self.queue),
                "pending_tasks": list(self.queue),
                "completed_count": len(self.task_history)
            }


class DeliveryTaskManagerNode(Node):
    def __init__(self):
        super().__init__('delivery_task_manager')

        self.declare_parameter('low_battery_threshold', 20.0)
        self.declare_parameter('charge_resume_threshold', 90.0)
        self.declare_parameter('idle_dock_timeout', 15.0)

        low_bat = self.get_parameter('low_battery_threshold').value
        chg_res = self.get_parameter('charge_resume_threshold').value
        
        self.manager = TaskQueueManager(low_battery_threshold=low_bat, charge_resume_threshold=chg_res)
        
        # Action Client for Nav2 (optional if nav2_msgs is present)
        if HAVE_NAV2:
            self.nav_action_client = ActionClient(self, NavigateToPose, 'navigate_to_pose')
        else:
            self.nav_action_client = None

        # Publishers & Subscribers
        self.status_pub = self.create_publisher(String, '/delivery_queue_status', 10)
        self.state_pub = self.create_publisher(String, '/robot_system_state', 10)
        
        self.create_subscription(String, '/delivery_request', self.delivery_request_cb, 10)
        self.create_subscription(BatteryState, '/battery_state', self.battery_cb, 10)

        self.timer = self.create_timer(1.0, self.control_loop)
        self.get_logger().info("Delivery Task Manager Node active.")

    def delivery_request_cb(self, msg: String):
        try:
            data = json.loads(msg.data)
            target = data.get('target', '')
            item = data.get('item', '')
            res = self.manager.add_delivery_request(target, item)
            if res['success']:
                self.get_logger().info(f"Accepted new delivery: {res['task']['id']} -> {target}")
            else:
                self.get_logger().warn(f"Rejected delivery request: {res['error']}")
        except Exception as e:
            self.get_logger().error(f"Error parsing delivery request payload: {e}")

    def battery_cb(self, msg: BatteryState):
        # Convert 0.0-1.0 range to percentage
        pct = msg.percentage * 100.0 if msg.percentage <= 1.0 else msg.percentage
        self.manager.update_battery(pct)

    def control_loop(self):
        summary = self.manager.get_status_summary()
        
        # Publish system status
        state_msg = String()
        state_msg.data = json.dumps(summary)
        self.status_pub.publish(state_msg)

        sys_state_msg = String()
        sys_state_msg.data = summary['robot_state']
        self.state_pub.publish(sys_state_msg)


def main(args=None):
    if HAVE_ROS2:
        rclpy.init(args=args)
        node = DeliveryTaskManagerNode()
        try:
            rclpy.spin(node)
        except KeyboardInterrupt:
            pass
        node.destroy_node()
        rclpy.shutdown()
    else:
        print("Running TaskQueueManager standalone test mode:")
        mgr = TaskQueueManager()
        req1 = mgr.add_delivery_request("Table 1", "Burger & Fries")
        req2 = mgr.add_delivery_request("Table 2", "Coffee")
        print("Queue length:", mgr.get_status_summary()["queue_length"])
        task = mgr.get_next_task()
        if task:
            print("Dispatched task:", task["id"], "to", task["target"])
        mgr.complete_current_task()
        print("Remaining in queue:", mgr.get_status_summary()["queue_length"])


if __name__ == '__main__':
    main()
