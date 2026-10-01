#!/usr/bin/env python3
import time
import json

try:
    import rclpy
    from rclpy.node import Node
    from std_msgs.msg import String, Bool
    HAVE_ROS2 = True
except ImportError:
    HAVE_ROS2 = False


class AutoDockingController:
    """
    Auto-docking state controller.
    Manages return-to-dock sequence on idle timeout and manual triggers.
    """
    def __init__(self, idle_timeout=10.0):
        self.idle_timeout = float(idle_timeout)
        self.idle_since = None
        self.is_docked = False
        self.is_docking_in_progress = False

    def evaluate_dock_trigger(self, queue_empty: bool, is_navigating: bool, current_time: float) -> str:
        """
        Determines if docking procedure should be initiated.
        Returns: 'dock_idle', 'remain_docked', or 'none'
        """
        if self.is_docked:
            if not queue_empty:
                self.is_docked = False
                self.is_docking_in_progress = False
                return 'undock_ready'
            return 'remain_docked'

        if queue_empty and not is_navigating:
            if self.idle_since is None:
                self.idle_since = current_time
            elif current_time - self.idle_since >= self.idle_timeout:
                return 'dock_idle'
        else:
            self.idle_since = None
            if not is_navigating:
                self.is_docking_in_progress = False

        return 'none'


if HAVE_ROS2:
    class DockingControllerNode(Node):
        def __init__(self):
            super().__init__('docking_controller')

            self.declare_parameter('idle_timeout', 10.0)
            idle_t = self.get_parameter('idle_timeout').value

            self.controller = AutoDockingController(idle_t)

            self.command_pub = self.create_publisher(String, '/dock_command', 10)

            self.create_subscription(String, '/delivery_queue_status', self.queue_status_cb, 10)
            self.create_subscription(Bool, '/dock_state', self.dock_state_cb, 10)

            self.queue_empty = True
            self.is_navigating = False

            self.timer = self.create_timer(1.0, self.timer_callback)
            self.get_logger().info("Docking Controller Node operational.")

        def queue_status_cb(self, msg: String):
            try:
                data = json.loads(msg.data)
                q_len = data.get('queue_length', 0)
                has_curr = data.get('current_task') is not None
                self.queue_empty = (q_len == 0 and not has_curr)
                state = data.get('robot_state', 'idle')
                self.is_navigating = state in ['navigating', 'en_route', 'at_table', 'delivering', 'docking']
                
                # Preempt docking immediately if new task is queued
                if not self.queue_empty and state == 'docking':
                    self.get_logger().info("New order detected while docking. Cancelling docking sequence.")
                    stop_msg = String()
                    stop_msg.data = "STOP_DOCK"
                    self.command_pub.publish(stop_msg)
                    self.controller.is_docking_in_progress = False

                if not self.queue_empty or state in ['idle', 'docked']:
                    self.controller.is_docking_in_progress = False
            except Exception:
                pass

        def dock_state_cb(self, msg: Bool):
            self.controller.is_docked = msg.data
            if msg.data:
                self.controller.is_docking_in_progress = False

        def timer_callback(self):
            now = time.time()
            action = self.controller.evaluate_dock_trigger(self.queue_empty, self.is_navigating, now)

            if action == 'dock_idle' and not self.controller.is_docking_in_progress and not self.controller.is_docked:
                self.get_logger().info(f"Triggering auto-docking sequence. Reason: {action}")
                cmd = String()
                cmd.data = f"DOCK_NOW:{action}"
                self.command_pub.publish(cmd)
                self.controller.is_docking_in_progress = True


def main(args=None):
    if HAVE_ROS2:
        rclpy.init(args=args)
        node = DockingControllerNode()
        try:
            rclpy.spin(node)
        except KeyboardInterrupt:
            pass
        node.destroy_node()
        rclpy.shutdown()
    else:
        print("Running AutoDockingController standalone test mode:")
        ctrl = AutoDockingController(idle_timeout=5.0)
        res = ctrl.evaluate_dock_trigger(queue_empty=True, is_navigating=False, current_time=time.time())
        print(f"Trigger evaluation for idle timeout: {res}")


if __name__ == '__main__':
    main()
