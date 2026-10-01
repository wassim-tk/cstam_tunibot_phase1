#!/usr/bin/env python3
from __future__ import annotations

import json
import time
import math
import threading
from collections import deque

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


# Predefined Waypoints matching restaurant.world layout (24 Dining Tables Service Points, Kitchen, Dock)
DEFAULT_WAYPOINTS = {
    "Dock": {"x": 7.06, "y": -12.00, "z": 0.0, "qx": 0.0, "qy": 0.0, "qz": 0.7071, "qw": 0.7071},
    "Kitchen/Pickup": {"x": -9.60, "y": -1.39, "z": 0.0, "qx": 0.0, "qy": 0.0, "qz": 1.0, "qw": 0.0},
    # Row 0 (North Terrace) Service Points in Aisle 0 (y = 0.50)
    "Table 0": {"x": -8.24, "y": 0.50, "z": 0.0, "qx": 0.0, "qy": 0.0, "qz": 0.7071, "qw": 0.7071},
    "Table 1": {"x": -5.64, "y": 0.50, "z": 0.0, "qx": 0.0, "qy": 0.0, "qz": 0.7071, "qw": 0.7071},
    "Table 2": {"x": -3.04, "y": 0.50, "z": 0.0, "qx": 0.0, "qy": 0.0, "qz": 0.7071, "qw": 0.7071},
    "Table 3": {"x": -0.44, "y": 0.50, "z": 0.0, "qx": 0.0, "qy": 0.0, "qz": 0.7071, "qw": 0.7071},
    "Table 4": {"x": 2.16, "y": 0.50, "z": 0.0, "qx": 0.0, "qy": 0.0, "qz": 0.7071, "qw": 0.7071},
    "Table 5": {"x": 4.76, "y": 0.50, "z": 0.0, "qx": 0.0, "qy": 0.0, "qz": 0.7071, "qw": 0.7071},
    # Row 1 (Mid Lounge) Service Points in Main Promenade (y = -3.10)
    "Table 6": {"x": -8.24, "y": -3.10, "z": 0.0, "qx": 0.0, "qy": 0.0, "qz": 0.7071, "qw": 0.7071},
    "Table 7": {"x": -5.64, "y": -3.10, "z": 0.0, "qx": 0.0, "qy": 0.0, "qz": 0.7071, "qw": 0.7071},
    "Table 8": {"x": -3.04, "y": -3.10, "z": 0.0, "qx": 0.0, "qy": 0.0, "qz": 0.7071, "qw": 0.7071},
    "Table 9": {"x": -0.44, "y": -3.10, "z": 0.0, "qx": 0.0, "qy": 0.0, "qz": 0.7071, "qw": 0.7071},
    "Table 10": {"x": 2.16, "y": -3.10, "z": 0.0, "qx": 0.0, "qy": 0.0, "qz": 0.7071, "qw": 0.7071},
    "Table 11": {"x": 4.76, "y": -3.10, "z": 0.0, "qx": 0.0, "qy": 0.0, "qz": 0.7071, "qw": 0.7071},
    # Row 2 (Central Dining Salon) Service Points in Main Promenade (y = -5.85)
    "Table 12": {"x": -8.24, "y": -5.85, "z": 0.0, "qx": 0.0, "qy": 0.0, "qz": -0.7071, "qw": 0.7071},
    "Table 13": {"x": -5.64, "y": -5.85, "z": 0.0, "qx": 0.0, "qy": 0.0, "qz": -0.7071, "qw": 0.7071},
    "Table 14": {"x": -3.04, "y": -5.85, "z": 0.0, "qx": 0.0, "qy": 0.0, "qz": -0.7071, "qw": 0.7071},
    "Table 15": {"x": -0.44, "y": -5.85, "z": 0.0, "qx": 0.0, "qy": 0.0, "qz": -0.7071, "qw": 0.7071},
    "Table 16": {"x": 2.16, "y": -5.85, "z": 0.0, "qx": 0.0, "qy": 0.0, "qz": -0.7071, "qw": 0.7071},
    "Table 17": {"x": 4.76, "y": -5.85, "z": 0.0, "qx": 0.0, "qy": 0.0, "qz": -0.7071, "qw": 0.7071},
    # Row 3 (South Wing) Service Points in Aisle 2 (y = -9.45)
    "Table 18": {"x": -8.24, "y": -9.45, "z": 0.0, "qx": 0.0, "qy": 0.0, "qz": -0.7071, "qw": 0.7071},
    "Table 19": {"x": -5.64, "y": -9.45, "z": 0.0, "qx": 0.0, "qy": 0.0, "qz": -0.7071, "qw": 0.7071},
    "Table 20": {"x": -3.04, "y": -9.45, "z": 0.0, "qx": 0.0, "qy": 0.0, "qz": -0.7071, "qw": 0.7071},
    "Table 21": {"x": -0.44, "y": -9.45, "z": 0.0, "qx": 0.0, "qy": 0.0, "qz": -0.7071, "qw": 0.7071},
    "Table 22": {"x": 2.16, "y": -9.45, "z": 0.0, "qx": 0.0, "qy": 0.0, "qz": -0.7071, "qw": 0.7071},
    "Table 23": {"x": 4.76, "y": -9.45, "z": 0.0, "qx": 0.0, "qy": 0.0, "qz": -0.7071, "qw": 0.7071},
}


class TaskQueueManager:
    """
    Core Task Queue and State Controller logic for Phase 1 MVP.
    Decoupled from ROS 2 middleware for high testability and reliability.
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
        # Case-insensitive resolution
        lower = target_clean.lower()
        for wp in self.waypoints:
            if wp.lower() == lower:
                return wp
            if wp.lower() == f"table {lower}":
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
            return {
                "robot_state": self.robot_state,
                "current_task": self.current_task,
                "queue_length": len(self.queue),
                "pending_tasks": list(self.queue),
                "completed_count": len(self.task_history)
            }


class DeliveryTaskManagerNode(Node):
    def __init__(self):
        super().__init__('delivery_task_manager')

        self.manager = TaskQueueManager()
        
        # Position and goal tracking (spawn default at dock: x=7.06, y=-12.00)
        self.current_x = 7.06
        self.current_y = -12.00
        self.target_coords = None
        self.target_name = None
        self.dwell_start_time = None
        self.current_goal_handle = None

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

        # Control loop at 2Hz for prompt responsiveness
        self.timer = self.create_timer(0.5, self.control_loop)
        self.get_logger().info("Delivery Task Manager Node active (Phase 1 Autonomous Queue Dispatch).")

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
                
                # If currently docking, preempt docking immediately for the new delivery task!
                if self.manager.robot_state == "docking":
                    self.get_logger().info("New delivery order received while DOCKING! Preempting docking sequence.")
                    self.stop_docking()

                # Check for immediate dispatch if robot is ready (idle or docked)
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
                self.start_docking()

    def start_docking(self):
        dock_wp = self.manager.waypoints.get("Dock")
        if not dock_wp:
            self.get_logger().error("Dock waypoint not found in waypoints configuration!")
            return

        tx = float(dock_wp.get('x', 7.06))
        ty = float(dock_wp.get('y', -12.00))

        # If robot is already within 0.60m of the dock waypoint
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

        # Robot is away from dock -> route to dock
        self.get_logger().info(f"Routing robot to Docking Station ({tx:.2f}, {ty:.2f}).")
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
            dock_msg = Bool()
            dock_msg.data = False
            self.dock_pub.publish(dock_msg)
            self.publish_status()

    def cancel_active_navigation(self):
        if self.current_goal_handle:
            try:
                self.get_logger().info("Cancelling active Nav2 goal...")
                self.current_goal_handle.cancel_goal_async()
            except Exception as e:
                self.get_logger().warn(f"Exception cancelling goal: {e}")
            self.current_goal_handle = None

        # Issue zero Twist to immediately stop robot base
        stop_cmd = Twist()
        for _ in range(3):
            self.cmd_vel_pub.publish(stop_cmd)

    def _goal_response_cb(self, future):
        try:
            goal_handle = future.result()
            if not goal_handle.accepted:
                self.get_logger().warn(f"Nav2 Goal for '{self.target_name}' was rejected by server!")
                self._handle_navigation_failure("Goal rejected by Nav2 server")
                return
            self.current_goal_handle = goal_handle
            self.get_logger().info(f"Nav2 Goal for '{self.target_name}' accepted by server.")
            result_future = goal_handle.get_result_async()
            result_future.add_done_callback(self._goal_result_cb)
        except Exception as e:
            self.get_logger().warn(f"Goal response exception: {e}")

    def _goal_result_cb(self, future):
        try:
            res = future.result()
            status = res.status
            if status == GoalStatus.STATUS_SUCCEEDED:
                self.get_logger().info(f"Nav2 trajectory to '{self.target_name}' reported SUCCESS.")
            elif status in [GoalStatus.STATUS_ABORTED, GoalStatus.STATUS_CANCELED]:
                self.get_logger().warn(f"Nav2 goal for '{self.target_name}' aborted or cancelled (status {status}).")
                if self.manager.robot_state in ["navigating", "en_route"] and self.target_coords is not None:
                    self._handle_navigation_failure(f"Nav2 aborted/cancelled trajectory (status {status})")
        except Exception as e:
            self.get_logger().warn(f"Goal result callback exception: {e}")

    def _handle_navigation_failure(self, reason: str):
        self.get_logger().error(f"Navigation failure encountered: {reason}. Aborting current task.")
        failed_task = self.manager.complete_current_task(success=False)
        tid = failed_task['id'] if failed_task else 'TASK'
        self.get_logger().info(f"Task {tid} marked as failed. Transitioning robot to IDLE.")
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

        # Cancel any previous action goal if active
        if self.current_goal_handle:
            try:
                self.current_goal_handle.cancel_goal_async()
            except Exception:
                pass
            self.current_goal_handle = None

        # Send via Nav2 Action Client if available and ready, else fallback to /goal_pose
        if self.nav_action_client and self.nav_action_client.server_is_ready():
            action_goal = NavigateToPose.Goal()
            action_goal.pose = goal
            send_goal_future = self.nav_action_client.send_goal_async(action_goal)
            send_goal_future.add_done_callback(self._goal_response_cb)
        else:
            self.goal_pub.publish(goal)

        self.get_logger().info(f"Dispatched Nav2 Goal for '{target_name}' at ({x:.2f}, {y:.2f})")

    def check_and_dispatch_next_task(self):
        """Dispatches the next order from the queue if the robot is idle or docked."""
        if self.manager.robot_state in ["idle", "docked"]:
            if self.manager.queue:
                # If docked, notify undock
                if self.manager.robot_state == "docked":
                    dock_msg = Bool()
                    dock_msg.data = False
                    self.dock_pub.publish(dock_msg)

                task = self.manager.get_next_task()
                if task:
                    target = task["target"]
                    wp = self.manager.waypoints.get(target)
                    if wp:
                        self.manager.robot_state = "navigating"
                        self.dispatch_goal(target, wp)
                        self.get_logger().info(f"Popped {task['id']} from queue -> en route to {target}!")

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
            try:
                t = self.tf_buffer.lookup_transform(
                    'map', 'base_footprint',
                    rclpy.time.Time(),
                    timeout=rclpy.duration.Duration(seconds=0.04)
                )
                self.current_x = t.transform.translation.x
                self.current_y = t.transform.translation.y
            except Exception:
                pass

        # 1. Monitor active movement and arrival at table or dock
        if self.target_coords is not None and self.current_x is not None:
            tx, ty = self.target_coords
            dist = math.sqrt((self.current_x - tx) ** 2 + (self.current_y - ty) ** 2)

            if dist < 0.50:
                if self.manager.robot_state in ["navigating", "en_route", "at_table"]:
                    if self.dwell_start_time is None:
                        self.dwell_start_time = time.time()
                        self.manager.robot_state = "at_table"
                        self.get_logger().info(f"Reached destination '{self.target_name}' (distance: {dist:.2f}m). Handing over delivery...")
                    elif time.time() - self.dwell_start_time >= 3.0:
                        finished = self.manager.complete_current_task(success=True)
                        task_id = finished['id'] if finished else 'TASK'
                        self.get_logger().info(f"Delivery completed for {task_id} at {self.target_name}! Robot now IDLE.")
                        if self.current_goal_handle:
                            try:
                                self.current_goal_handle.cancel_goal_async()
                            except Exception:
                                pass
                        self.dwell_start_time = None
                        self.target_coords = None
                        self.target_name = None
                        self.current_goal_handle = None
                        self.manager.robot_state = "idle"
                        
                        # Immediately check if more tasks are queued
                        self.check_and_dispatch_next_task()

                elif self.manager.robot_state == "docking":
                    self.manager.robot_state = "docked"
                    self.target_coords = None
                    self.target_name = None
                    self.current_goal_handle = None
                    dock_msg = Bool()
                    dock_msg.data = True
                    self.dock_pub.publish(dock_msg)
                    self.get_logger().info("Robot safely docked at charging dock.")

        # 2. Check queue dispatch if robot is ready
        self.check_and_dispatch_next_task()

        # 3. Publish system status summaries
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
