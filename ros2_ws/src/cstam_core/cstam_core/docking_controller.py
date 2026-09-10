#!/usr/bin/env python3
import time
import json

try:
    import rclpy
    from rclpy.node import Node
    from sensor_msgs.msg import BatteryState
    from std_msgs.msg import String, Bool
    HAVE_ROS2 = True
except ImportError:
    HAVE_ROS2 = False


class AutoDockingController:
    """
    Auto-docking State Machine controller.
    """
    def __init__(self, idle_timeout=15.0, low_battery_threshold=20.0, full_charge_threshold=90.0):
        self.idle_timeout = float(idle_timeout)
        self.low_battery_threshold = float(low_battery_threshold)
        self.full_charge_threshold = float(full_charge_threshold)
        
        self.idle_since = None
        self.is_docked = False
        self.is_docking_in_progress = False
        self.battery_percentage = 100.0

    def evaluate_dock_trigger(self, queue_empty: bool, is_navigating: bool, current_time: float) -> str:
        """
        Determines if docking procedure should be initiated.
        Returns: 'dock_low_battery', 'dock_idle', 'remain_docked', or 'undock_ready'
        """
        if self.is_docked:
            if self.battery_percentage >= self.full_charge_threshold:
                return 'undock_ready'
            return 'remain_docked'

        if self.battery_percentage < self.low_battery_threshold:
            return 'dock_low_battery'

        if queue_empty and not is_navigating:
            if self.idle_since is None:
                self.idle_since = current_time
            elif current_time - self.idle_since >= self.idle_timeout:
                return 'dock_idle'
        else:
            self.idle_since = None

        return 'none'


if HAVE_ROS2:
    class DockingControllerNode(Node):
        def __init__(self):
            super().__init__('docking_controller')

            self.declare_parameter('idle_timeout', 15.0)
            self.declare_parameter('low_battery_threshold', 20.0)
            self.declare_parameter('full_charge_threshold', 90.0)

            idle_t = self.get_parameter('idle_timeout').value
            low_b = self.get_parameter('low_battery_threshold').value
            full_c = self.get_parameter('full_charge_threshold').value

            self.controller = AutoDockingController(idle_t, low_b, full_c)

            self.dock_pub = self.create_publisher(Bool, '/dock_state', 10)
            self.command_pub = self.create_publisher(String, '/dock_command', 10)

            self.create_subscription(BatteryState, '/battery_state', self.battery_cb, 10)
            self.create_subscription(String, '/delivery_queue_status', self.queue_status_cb, 10)

            self.queue_empty = True
            self.is_navigating = False

            self.timer = self.create_timer(1.0, self.timer_callback)
            self.get_logger().info("Docking Controller Node operational.")

        def battery_cb(self, msg: BatteryState):
            pct = msg.percentage * 100.0 if msg.percentage <= 1.0 else msg.percentage
            self.controller.battery_percentage = pct

        def queue_status_cb(self, msg: String):
            try:
                data = json.loads(msg.data)
                self.queue_empty = data.get('queue_length', 0) == 0
                self.is_navigating = data.get('robot_state') in ['navigating', 'en_route']
            except Exception as e:
                pass

        def timer_callback(self):
            now = time.time()
            action = self.controller.evaluate_dock_trigger(self.queue_empty, self.is_navigating, now)
            
            dock_msg = Bool()
            dock_msg.data = self.controller.is_docked
            self.dock_pub.publish(dock_msg)

            if action in ['dock_low_battery', 'dock_idle'] and not self.controller.is_docking_in_progress:
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
        ctrl = AutoDockingController(idle_timeout=5.0, low_battery_threshold=20.0)
        ctrl.battery_percentage = 15.0
        res = ctrl.evaluate_dock_trigger(queue_empty=True, is_navigating=False, current_time=time.time())
        print(f"Trigger evaluation for low battery (15%): {res}")


if __name__ == '__main__':
    main()
