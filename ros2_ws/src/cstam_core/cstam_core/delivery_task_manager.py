#!/usr/bin/env python3
from __future__ import annotations

import os
import json
import time
import math
import threading
from collections import deque

try:
    import yaml
    HAVE_YAML = True
except ImportError:
    HAVE_YAML = False

try:
    import rclpy
    from rclpy.node import Node
    from geometry_msgs.msg import PoseStamped, PoseWithCovarianceStamped, Twist
    from nav_msgs.msg import Odometry
    from std_msgs.msg import String, Bool
    import tf2_ros
    from tf2_ros import Buffer, TransformListener
    HAVE_ROS2 = True
except ImportError:
    HAVE_ROS2 = False
    class Node:  # type: ignore
        def __init__(self, *args, **kwargs):
            pass
    class String: pass  # type: ignore
    class PoseStamped: pass  # type: ignore
    class PoseWithCovarianceStamped: pass  # type: ignore
    class Odometry: pass  # type: ignore
    class Bool: pass  # type: ignore
    class Twist: pass  # type: ignore
    class Buffer: pass  # type: ignore
    class TransformListener: pass  # type: ignore

try:
    from rclpy.action import ActionClient
    from nav2_msgs.action import NavigateToPose  # type: ignore
    from action_msgs.msg import GoalStatus  # type: ignore
    HAVE_NAV2 = True
except ImportError:
    HAVE_NAV2 = False
    class GoalStatus:  # type: ignore
        STATUS_UNKNOWN = 0
        STATUS_ACCEPTED = 1
        STATUS_EXECUTING = 2
        STATUS_CANCELING = 3
        STATUS_SUCCEEDED = 4
        STATUS_CANCELED = 5
        STATUS_ABORTED = 6


DEFAULT_WAYPOINTS = {
    "Dock": {"x": 7.06, "y": -12.00, "z": 0.0, "qx": 0.0, "qy": 0.0, "qz": 0.7071, "qw": 0.7071},
    "Kitchen/Pickup": {"x": -9.60, "y": -1.39, "z": 0.0, "qx": 0.0, "qy": 0.0, "qz": 1.0, "qw": 0.0},
    "Table 0": {"x": -8.24, "y": 0.50, "z": 0.0, "qx": 0.0, "qy": 0.0, "qz": 0.7071, "qw": 0.7071},
    "Table 1": {"x": -5.64, "y": 0.50, "z": 0.0, "qx": 0.0, "qy": 0.0, "qz": 0.7071, "qw": 0.7071},
    "Table 2": {"x": -3.04, "y": 0.50, "z": 0.0, "qx": 0.0, "qy": 0.0, "qz": 0.7071, "qw": 0.7071},
    "Table 3": {"x": -0.44, "y": 0.50, "z": 0.0, "qx": 0.0, "qy": 0.0, "qz": 0.7071, "qw": 0.7071},
    "Table 4": {"x": 2.16, "y": 0.50, "z": 0.0, "qx": 0.0, "qy": 0.0, "qz": 0.7071, "qw": 0.7071},
    "Table 5": {"x": 4.76, "y": 0.50, "z": 0.0, "qx": 0.0, "qy": 0.0, "qz": 0.7071, "qw": 0.7071},
    "Table 6": {"x": -8.24, "y": -3.10, "z": 0.0, "qx": 0.0, "qy": 0.0, "qz": 0.7071, "qw": 0.7071},
    "Table 7": {"x": -5.64, "y": -3.10, "z": 0.0, "qx": 0.0, "qy": 0.0, "qz": 0.7071, "qw": 0.7071},
    "Table 8": {"x": -3.04, "y": -3.10, "z": 0.0, "qx": 0.0, "qy": 0.0, "qz": 0.7071, "qw": 0.7071},
    "Table 9": {"x": -0.44, "y": -3.10, "z": 0.0, "qx": 0.0, "qy": 0.0, "qz": 0.7071, "qw": 0.7071},
    "Table 10": {"x": 2.16, "y": -3.10, "z": 0.0, "qx": 0.0, "qy": 0.0, "qz": 0.7071, "qw": 0.7071},
    "Table 11": {"x": 4.76, "y": -3.10, "z": 0.0, "qx": 0.0, "qy": 0.0, "qz": 0.7071, "qw": 0.7071},
    "Table 12": {"x": -8.24, "y": -5.85, "z": 0.0, "qx": 0.0, "qy": 0.0, "qz": -0.7071, "qw": 0.7071},
    "Table 13": {"x": -5.64, "y": -5.85, "z": 0.0, "qx": 0.0, "qy": 0.0, "qz": -0.7071, "qw": 0.7071},
    "Table 14": {"x": -3.04, "y": -5.85, "z": 0.0, "qx": 0.0, "qy": 0.0, "qz": -0.7071, "qw": 0.7071},
    "Table 15": {"x": -0.44, "y": -5.85, "z": 0.0, "qx": 0.0, "qy": 0.0, "qz": -0.7071, "qw": 0.7071},
    "Table 16": {"x": 2.16, "y": -5.85, "z": 0.0, "qx": 0.0, "qy": 0.0, "qz": -0.7071, "qw": 0.7071},
    "Table 17": {"x": 4.76, "y": -5.85, "z": 0.0, "qx": 0.0, "qy": 0.0, "qz": -0.7071, "qw": 0.7071},
    "Table 18": {"x": -8.24, "y": -9.45, "z": 0.0, "qx": 0.0, "qy": 0.0, "qz": -0.7071, "qw": 0.7071},
    "Table 19": {"x": -5.64, "y": -9.45, "z": 0.0, "qx": 0.0, "qy": 0.0, "qz": -0.7071, "qw": 0.7071},
    "Table 20": {"x": -3.04, "y": -9.45, "z": 0.0, "qx": 0.0, "qy": 0.0, "qz": -0.7071, "qw": 0.7071},
    "Table 21": {"x": -0.44, "y": -9.45, "z": 0.0, "qx": 0.0, "qy": 0.0, "qz": -0.7071, "qw": 0.7071},
    "Table 22": {"x": 2.16, "y": -9.45, "z": 0.0, "qx": 0.0, "qy": 0.0, "qz": -0.7071, "qw": 0.7071},
    "Table 23": {"x": 4.76, "y": -9.45, "z": 0.0, "qx": 0.0, "qy": 0.0, "qz": -0.7071, "qw": 0.7071},
}


class TaskQueueManager:
    """
    Core Task Queue and State Controller logic.
    Manages pending orders, dynamic modification, and task lifecycle.
    """
    def __init__(self, waypoints=None):
        self.waypoints = waypoints or DEFAULT_WAYPOINTS
        self.queue = deque()
        self.current_task = None
        self.task_history = []
        self.robot_state = "idle"  # idle, navigating, at_table, docked, docking
        self.task_id_counter = 1
        self.lock = threading.Lock()

    def _resolve_target(self, target_input: str) -> str | None:
        target_clean = target_input.strip()
        if target_clean in self.waypoints:
            return target_clean
        lower = target_clean.lower()
        for wp in self.waypoints:
            if wp.lower() == lower or wp.lower() == f"table {lower}":
                return wp
        return None

    def add_delivery_request(self, target_location: str, item_description: str = "") -> dict:
        with self.lock:
            resolved = self._resolve_target(target_location)
            if not resolved:
                return {"success": False, "error": f"Unknown target location '{target_location}'"}
            
            task = {
                "id": f"TASK-{self.task_id_counter:04d}",
                "target": resolved,
                "item": item_description or "Food & Beverage Order",
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
            task = self.queue.popleft()
            task["status"] = "en_route"
            self.current_task = task
            return task

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

    def delete_task(self, task_id: str) -> bool:
        with self.lock:
            for i, task in enumerate(self.queue):
                if task["id"] == task_id:
                    del self.queue[i]
                    task["status"] = "cancelled"
                    task["completed_at"] = time.time()
                    self.task_history.append(task)
                    return True
            return False

    def modify_task(self, task_id: str, new_target: str = None, new_item: str = None) -> bool:
        with self.lock:
            for task in self.queue:
                if task["id"] == task_id:
                    if new_target:
                        resolved = self._resolve_target(new_target)
                        if not resolved:
                            return False
                        task["target"] = resolved
                    if new_item is not None:
                        item_clean = new_item.strip()
                        if item_clean:
                            task["item"] = item_clean
                    return True
            return False

    def get_status_summary(self):
        with self.lock:
            completed_success = sum(1 for t in self.task_history if t.get("status") == "completed")
            return {
                "robot_state": self.robot_state,
                "current_task": self.current_task,
                "queue_length": len(self.queue),
                "pending_tasks": list(self.queue),
                "completed_count": completed_success
            }


class DeliveryTaskManagerNode(Node):
    def _load_waypoints(self, wp_file: str = '') -> dict:
        if not HAVE_YAML:
            return DEFAULT_WAYPOINTS
        
        target_path = wp_file.strip() if wp_file else ''
        if not target_path or not os.path.exists(target_path):
            try:
                from ament_index_python.packages import get_package_share_directory
                pkg_nav = get_package_share_directory('cstam_navigation')
                env_world = os.environ.get('CSTAM_WORLD', '').lower()
                if 'resto' in env_world or 'arbi' in env_world:
                    candidate = os.path.join(pkg_nav, 'config', 'resto_arbi_waypoints.yaml')
                else:
                    candidate = os.path.join(pkg_nav, 'config', 'waypoints.yaml')
                if os.path.exists(candidate):
                    target_path = candidate
            except Exception:
                pass
        
        if target_path and os.path.exists(target_path):
            try:
                with open(target_path, 'r') as f:
                    data = yaml.safe_load(f)
                    wps = data.get('waypoints', {})
                    if wps and isinstance(wps, dict):
                        self.get_logger().info(f"Loaded {len(wps)} waypoints from '{target_path}'.")
                        return wps
            except Exception as e:
                self.get_logger().warn(f"Failed to load waypoints from '{target_path}': {e}. Using defaults.")

        return DEFAULT_WAYPOINTS

    def __init__(self):
        super().__init__('delivery_task_manager')

        self.declare_parameter('waypoints_file', '')
        wp_param = self.get_parameter('waypoints_file').value if HAVE_ROS2 else ''
        loaded_wps = self._load_waypoints(wp_param)
        self.manager = TaskQueueManager(waypoints=loaded_wps)
        
        # Position tracking and goal management
        dock_wp = self.manager.waypoints.get("Dock", {})
        self.current_x = float(dock_wp.get("x", 7.06))
        self.current_y = float(dock_wp.get("y", -12.00))
        self.target_coords = None
        self.target_name = None
        self.dwell_start_time = None
        self.current_goal_handle = None
        self.nav_goal_succeeded = False
        self.dock_retry_count = 0
        self.delivery_retry_count = 0
        self.queue_empty_since = None
        self.active_goal_id = 0

        # TF Buffer and Listener for accurate map-frame robot position
        if HAVE_ROS2:
            self.tf_buffer = Buffer()
            self.tf_listener = TransformListener(self.tf_buffer, self)
        else:
            self.tf_buffer = None
            self.tf_listener = None

        # Action Client for Nav2
        if HAVE_NAV2:
            self.nav_action_client = ActionClient(self, NavigateToPose, 'navigate_to_pose')
        else:
            self.nav_action_client = None

        # Publishers
        self.goal_pub = self.create_publisher(PoseStamped, '/goal_pose', 10)
        self.cmd_vel_pub = self.create_publisher(Twist, '/cmd_vel', 10)
        self.dock_pub = self.create_publisher(Bool, '/dock_state', 10)
        self.status_pub = self.create_publisher(String, '/delivery_queue_status', 10)
        self.state_pub = self.create_publisher(String, '/robot_system_state', 10)
        
        # Subscribers
        self.create_subscription(String, '/delivery_request', self.delivery_request_cb, 10)
        self.create_subscription(String, '/delivery_task_action', self.task_action_cb, 10)
        self.create_subscription(String, '/dock_command', self.dock_command_cb, 10)
        self.create_subscription(PoseWithCovarianceStamped, '/amcl_pose', self.amcl_cb, 10)

        # Control loop at 2Hz for responsive execution
        self.timer = self.create_timer(0.5, self.control_loop)
        self.get_logger().info("Delivery Task Manager Node active.")

    def amcl_cb(self, msg: PoseWithCovarianceStamped):
        self.current_x = msg.pose.pose.position.x
        self.current_y = msg.pose.pose.position.y

    def task_action_cb(self, msg: String):
        try:
            data = json.loads(msg.data)
            action = data.get("action", "")
            if action == "delete":
                task_id = data.get("task_id", "")
                if self.manager.delete_task(task_id):
                    self.get_logger().info(f"Deleted task {task_id} from pending queue.")
                    self.publish_status()
                else:
                    self.get_logger().warn(f"Could not delete task {task_id}: not found.")
            elif action == "modify":
                task_id = data.get("task_id", "")
                target = data.get("target")
                item = data.get("item")
                if self.manager.modify_task(task_id, target, item):
                    self.get_logger().info(f"Modified task {task_id}: target={target}, item={item}")
                    self.publish_status()
                else:
                    self.get_logger().warn(f"Could not modify task {task_id}: not found or target invalid.")
            elif action in ["stop_dock", "cancel_dock"]:
                self.stop_docking()
        except Exception as e:
            self.get_logger().error(f"Error handling task action: {e}")

    def delivery_request_cb(self, msg: String):
        try:
            data = json.loads(msg.data)
            target = data.get('target', '')
            item = data.get('item', '')
            res = self.manager.add_delivery_request(target, item)
            if res['success']:
                task_id = res['task']['id']
                resolved_target = res['task']['target']
                self.get_logger().info(f"Accepted new delivery: {task_id} -> {resolved_target} ({item})")
                
                # Reset 10s auto-dock timer since queue is no longer empty
                self.queue_empty_since = None

                # If currently docking, preempt docking immediately for the new order
                if self.manager.robot_state == "docking":
                    self.get_logger().info("New delivery order received while docking! Preempting docking sequence.")
                    self.stop_docking()

                # Dispatch next task if robot is ready
                self.check_and_dispatch_next_task()
                self.publish_status()
            else:
                self.get_logger().warn(f"Rejected delivery request: {res['error']}")
        except Exception as e:
            self.get_logger().error(f"Error parsing delivery request payload: {e}")

    def dock_command_cb(self, msg: String):
        cmd = msg.data.strip().upper()
        if "STOP" in cmd or "CANCEL" in cmd:
            self.stop_docking()
        elif "DOCK_NOW" in cmd:
            if self.manager.robot_state != "docking":
                self.dock_retry_count = 0
                self.start_docking()

    def start_docking(self):
        dock_wp = self.manager.waypoints.get("Dock")
        if not dock_wp:
            self.get_logger().error("Dock waypoint not found in configuration.")
            return

        tx = float(dock_wp.get('x', 7.06))
        ty = float(dock_wp.get('y', -12.00))

        # Check if robot is already at dock (<0.60m)
        if self.current_x is not None and self.current_y is not None:
            dist = math.sqrt((self.current_x - tx) ** 2 + (self.current_y - ty) ** 2)
            if dist < 0.60:
                self.get_logger().info(f"Robot is already at Dock (distance: {dist:.2f}m). Setting state to DOCKED.")
                self.manager.robot_state = "docked"
                self.target_coords = None
                self.target_name = None
                dock_msg = Bool()
                dock_msg.data = True
                self.dock_pub.publish(dock_msg)
                self.publish_status()
                return

        # Navigate to resting dock
        self.get_logger().info(f"Routing robot to Resting Dock Station ({tx:.2f}, {ty:.2f}).")
        self.manager.robot_state = "docking"
        self.dispatch_goal("Dock", dock_wp)
        self.publish_status()

    def stop_docking(self):
        if self.manager.robot_state == "docking":
            self.get_logger().info("Stopping/Cancelling docking procedure...")
            self.cancel_active_navigation()
            self.manager.robot_state = "idle"
            self.target_coords = None
            self.target_name = None
            self.queue_empty_since = None
            dock_msg = Bool()
            dock_msg.data = False
            self.dock_pub.publish(dock_msg)
            self.publish_status()

    def cancel_active_navigation(self):
        self.active_goal_id += 1
        if self.current_goal_handle:
            try:
                self.current_goal_handle.cancel_goal_async()
            except Exception as e:
                self.get_logger().warn(f"Exception cancelling goal: {e}")
            self.current_goal_handle = None

        # Stop robot base
        stop_cmd = Twist()
        for _ in range(3):
            self.cmd_vel_pub.publish(stop_cmd)

    def _goal_response_cb(self, future, goal_id: int, target_name: str):
        if goal_id != self.active_goal_id:
            try:
                gh = future.result()
                if gh and gh.accepted:
                    gh.cancel_goal_async()
            except Exception:
                pass
            return

        try:
            goal_handle = future.result()
            if not goal_handle.accepted:
                self.get_logger().warn(f"Nav2 Goal #{goal_id} for '{target_name}' was rejected by server.")
                if self.manager.robot_state == "docking":
                    self._handle_docking_failure()
                else:
                    self._handle_delivery_failure()
                return
            self.current_goal_handle = goal_handle
            self.get_logger().info(f"Nav2 Goal #{goal_id} for '{target_name}' accepted by server.")
            result_future = goal_handle.get_result_async()
            result_future.add_done_callback(
                lambda fut, gid=goal_id, tgt=target_name: self._goal_result_cb(fut, gid, tgt)
            )
        except Exception as e:
            self.get_logger().warn(f"Goal response exception: {e}")

    def trigger_arrival(self):
        """Called when robot reaches destination (via Nav2 success or arrival tolerance)."""
        if self.manager.robot_state in ["navigating", "en_route", "at_table"]:
            if self.dwell_start_time is None:
                self.delivery_retry_count = 0
                self.dwell_start_time = time.time()
                self.manager.robot_state = "at_table"
                self.get_logger().info(f"Reached destination '{self.target_name}'. Handing over delivery...")
                self.publish_status()
        elif self.manager.robot_state == "docking":
            self.manager.robot_state = "docked"
            self.dock_retry_count = 0
            self.target_coords = None
            self.target_name = None
            self.current_goal_handle = None

            # Brake robot base cleanly at dock
            stop_cmd = Twist()
            for _ in range(3):
                self.cmd_vel_pub.publish(stop_cmd)

            dock_msg = Bool()
            dock_msg.data = True
            self.dock_pub.publish(dock_msg)
            self.get_logger().info("Robot safely parked at resting dock.")
            self.publish_status()

    def _goal_result_cb(self, future, goal_id: int, target_name: str):
        if goal_id != self.active_goal_id:
            self.get_logger().info(f"Ignoring stale Nav2 result for goal #{goal_id} ('{target_name}'). Active goal is #{self.active_goal_id}.")
            return

        try:
            res = future.result()
            status = res.status
            if status == GoalStatus.STATUS_SUCCEEDED:
                self.get_logger().info(f"Nav2 trajectory for goal #{goal_id} ('{target_name}') reported SUCCESS.")
                self.nav_goal_succeeded = True
                self.trigger_arrival()
            elif status in [GoalStatus.STATUS_ABORTED, GoalStatus.STATUS_CANCELED]:
                self.get_logger().warn(f"Nav2 goal #{goal_id} for '{target_name}' aborted or cancelled (status {status}).")
                if self.manager.robot_state == "docking":
                    self._handle_docking_failure()
                elif self.manager.robot_state in ["navigating", "en_route"] and self.target_coords is not None:
                    self._handle_delivery_failure()
        except Exception as e:
            self.get_logger().warn(f"Goal result callback exception: {e}")

    def _handle_docking_failure(self):
        self.dock_retry_count += 1
        if self.dock_retry_count <= 2:
            self.get_logger().warn(f"Docking goal aborted by Nav2. Retrying docking attempt {self.dock_retry_count}/2...")
            dock_wp = self.manager.waypoints.get("Dock")
            if dock_wp:
                self.current_goal_handle = None
                self.dispatch_goal("Dock", dock_wp)
                return

        self.get_logger().warn("Docking procedure failed after retries. Resetting robot state to IDLE.")
        self.dock_retry_count = 0
        self.target_coords = None
        self.target_name = None
        self.current_goal_handle = None
        self.manager.robot_state = "idle"
        dock_msg = Bool()
        dock_msg.data = False
        self.dock_pub.publish(dock_msg)
        self.publish_status()

    def _handle_delivery_failure(self):
        self.delivery_retry_count += 1
        if self.delivery_retry_count <= 2:
            self.get_logger().warn(f"Delivery goal for '{self.target_name}' aborted by Nav2. Retrying attempt {self.delivery_retry_count}/2...")
            target = self.target_name
            wp = self.manager.waypoints.get(target) if target else None
            if wp:
                self.current_goal_handle = None
                self.dispatch_goal(target, wp)
                return

        # If retries exhausted, keep task in queue so it is never dropped or skipped
        self.get_logger().warn(f"Delivery to '{self.target_name}' postponed after retries. Keeping order in queue.")
        self.delivery_retry_count = 0
        if self.manager.current_task:
            with self.manager.lock:
                task = self.manager.current_task
                task["status"] = "queued"
                self.manager.queue.append(task)
                self.manager.current_task = None

        self.dwell_start_time = None
        self.target_coords = None
        self.target_name = None
        self.current_goal_handle = None
        self.manager.robot_state = "idle"
        self.check_and_dispatch_next_task()
        self.publish_status()

    def dispatch_goal(self, target_name: str, wp: dict):
        x = float(wp.get('x', 0.0))
        y = float(wp.get('y', 0.0))
        qz = float(wp.get('qz', 0.0))
        qw = float(wp.get('qw', 1.0))

        goal = PoseStamped()
        goal.header.frame_id = 'map'
        goal.header.stamp = self.get_clock().now().to_msg()
        goal.pose.position.x = x
        goal.pose.position.y = y
        goal.pose.position.z = 0.0
        goal.pose.orientation.x = 0.0
        goal.pose.orientation.y = 0.0
        goal.pose.orientation.z = qz
        goal.pose.orientation.w = qw

        self.target_coords = (x, y)
        self.target_name = target_name
        self.dwell_start_time = None
        self.nav_goal_succeeded = False

        self.active_goal_id += 1
        goal_id = self.active_goal_id

        if self.current_goal_handle:
            try:
                self.current_goal_handle.cancel_goal_async()
            except Exception:
                pass
            self.current_goal_handle = None

        if self.nav_action_client and (self.nav_action_client.server_is_ready() or self.nav_action_client.wait_for_server(timeout_sec=0.2)):
            action_goal = NavigateToPose.Goal()
            action_goal.pose = goal
            send_goal_future = self.nav_action_client.send_goal_async(action_goal)
            send_goal_future.add_done_callback(
                lambda fut, gid=goal_id, tgt=target_name: self._goal_response_cb(fut, gid, tgt)
            )
        else:
            self.goal_pub.publish(goal)

        self.get_logger().info(f"Dispatched Nav2 Goal #{goal_id} for '{target_name}' at ({x:.2f}, {y:.2f})")

    def check_and_dispatch_next_task(self):
        """Dispatches the next order from the queue if the robot is idle or docked."""
        if self.manager.robot_state in ["idle", "docked"]:
            if self.manager.queue:
                self.queue_empty_since = None
                if self.manager.robot_state == "docked":
                    dock_msg = Bool()
                    dock_msg.data = False
                    self.dock_pub.publish(dock_msg)

                task = self.manager.get_next_task()
                if task:
                    target = task["target"]
                    wp = self.manager.waypoints.get(target)
                    if wp:
                        tx = float(wp.get('x', 0.0))
                        ty = float(wp.get('y', 0.0))

                        # Check if robot is already at this table (<0.35m)
                        if self.current_x is not None and self.current_y is not None:
                            d = math.sqrt((self.current_x - tx) ** 2 + (self.current_y - ty) ** 2)
                            if d < 0.35 and target != "Dock":
                                self.get_logger().info(f"Robot is already at {target} (dist: {d:.2f}m). Serving delivery {task['id']} directly.")
                                self.target_coords = (tx, ty)
                                self.target_name = target
                                self.manager.robot_state = "at_table"
                                self.dwell_start_time = time.time()
                                self.publish_status()
                                return

                        self.manager.robot_state = "navigating"
                        self.dispatch_goal(target, wp)
                        self.get_logger().info(f"Popped {task['id']} from queue -> en route to {target}!")
                        self.publish_status()

    def publish_status(self):
        summary = self.manager.get_status_summary()
        state_msg = String()
        state_msg.data = json.dumps(summary)
        self.status_pub.publish(state_msg)

        sys_state_msg = String()
        sys_state_msg.data = summary['robot_state']
        self.state_pub.publish(sys_state_msg)

    def control_loop(self):
        # 0. Query TF for exact robot pose in map frame
        if self.tf_buffer:
            for frame in ['base_footprint', 'base_link']:
                try:
                    t = self.tf_buffer.lookup_transform(
                        'map', frame,
                        rclpy.time.Time(),
                        timeout=rclpy.duration.Duration(seconds=0.04)
                    )
                    self.current_x = t.transform.translation.x
                    self.current_y = t.transform.translation.y
                    break
                except Exception:
                    pass

        # 1. Monitor active movement and arrival at table or dock
        if self.target_coords is not None and self.current_x is not None:
            tx, ty = self.target_coords
            dist = math.sqrt((self.current_x - tx) ** 2 + (self.current_y - ty) ** 2)

            # Trigger arrival if within tight tolerance or Nav2 reported success
            if dist < 0.35 or self.nav_goal_succeeded:
                self.trigger_arrival()

        # 2. Check dwell completion at table
        if self.manager.robot_state == "at_table" and self.dwell_start_time is not None:
            if time.time() - self.dwell_start_time >= 2.5:
                finished = self.manager.complete_current_task(success=True)
                task_id = finished['id'] if finished else 'TASK'
                self.get_logger().info(f"Delivery completed for {task_id} at {self.target_name}! Robot now IDLE.")
                
                # Stop robot cleanly
                stop_cmd = Twist()
                for _ in range(2):
                    self.cmd_vel_pub.publish(stop_cmd)

                self.dwell_start_time = None
                self.target_coords = None
                self.target_name = None
                self.current_goal_handle = None
                self.nav_goal_succeeded = False
                self.manager.robot_state = "idle"
                self.publish_status()
                
                # Check next task in queue
                self.check_and_dispatch_next_task()

        # 3. Check queue dispatch if robot is ready
        self.check_and_dispatch_next_task()

        # 4. Auto-docking countdown: exactly 10s from the second queue is empty and robot is idle
        if self.manager.robot_state == "idle" and len(self.manager.queue) == 0 and self.manager.current_task is None:
            if self.queue_empty_since is None:
                self.queue_empty_since = time.time()
                self.get_logger().info("Queue is empty and robot is idle. 10-second auto-dock countdown started.")
            elif time.time() - self.queue_empty_since >= 10.0:
                self.get_logger().info("10 seconds elapsed since queue became empty. Triggering auto-docking.")
                self.queue_empty_since = None
                self.start_docking()
        else:
            self.queue_empty_since = None

        # 5. Publish system status summaries
        self.publish_status()


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
