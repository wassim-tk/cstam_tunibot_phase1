#!/usr/bin/env python3
import time
import math

try:
    import rclpy
    from rclpy.node import Node
    from sensor_msgs.msg import BatteryState
    from std_msgs.msg import String, Bool
    HAVE_ROS2 = True
except ImportError:
    HAVE_ROS2 = False


class BatterySimulator:
    """
    Core Battery Simulation Logic.
    Calculates battery drain based on state/distance and charge rate when docked.
    """
    def __init__(self, initial_percentage=100.0, drain_rate_idle=0.02, drain_rate_nav=0.15, charge_rate=2.0):
        self.percentage = float(initial_percentage)
        self.drain_rate_idle = float(drain_rate_idle)  # % per sec
        self.drain_rate_nav = float(drain_rate_nav)    # % per sec
        self.charge_rate = float(charge_rate)          # % per sec
        self.is_docked = False
        self.is_moving = False
        self.voltage = 12.0
        self.capacity = 10.0  # Ah

    def update(self, dt=1.0):
        if self.is_docked:
            self.percentage = min(100.0, self.percentage + self.charge_rate * dt)
        else:
            rate = self.drain_rate_nav if self.is_moving else self.drain_rate_idle
            self.percentage = max(0.0, self.percentage - rate * dt)

        self.voltage = 10.0 + (self.percentage / 100.0) * 2.6
        return self.percentage


if HAVE_ROS2:
    class BatterySimulatorNode(Node):
        def __init__(self):
            super().__init__('battery_simulator')
            
            self.declare_parameter('initial_battery', 100.0)
            self.declare_parameter('drain_rate_idle', 0.05)
            self.declare_parameter('drain_rate_nav', 0.20)
            self.declare_parameter('charge_rate', 2.5)

            init_bat = self.get_parameter('initial_battery').value
            d_idle = self.get_parameter('drain_rate_idle').value
            d_nav = self.get_parameter('drain_rate_nav').value
            chg = self.get_parameter('charge_rate').value

            self.sim = BatterySimulator(init_bat, d_idle, d_nav, chg)

            self.publisher_ = self.create_publisher(BatteryState, '/battery_state', 10)
            
            # Subscriptions
            self.create_subscription(String, '/robot_system_state', self.system_state_cb, 10)
            self.create_subscription(Bool, '/dock_state', self.dock_state_cb, 10)

            self.timer = self.create_timer(1.0, self.timer_callback)
            self.get_logger().info("Battery Simulator Node initialized successfully.")

        def system_state_cb(self, msg: String):
            state = msg.data.lower()
            self.sim.is_moving = 'navigating' in state or 'en_route' in state
            if 'docked' in state or 'charging' in state:
                self.sim.is_docked = True

        def dock_state_cb(self, msg: Bool):
            self.sim.is_docked = msg.data

        def timer_callback(self):
            current_pct = self.sim.update(dt=1.0)
            
            msg = BatteryState()
            msg.header.stamp = self.get_clock().now().to_msg()
            msg.header.frame_id = 'base_link'
            msg.percentage = current_pct / 100.0  # Normalized [0.0 - 1.0] in ROS 2 standard
            msg.voltage = self.sim.voltage
            msg.capacity = self.sim.capacity
            msg.design_capacity = 10.0

            if self.sim.is_docked:
                msg.power_supply_status = BatteryState.POWER_SUPPLY_STATUS_CHARGING
            elif current_pct < 20.0:
                msg.power_supply_status = BatteryState.POWER_SUPPLY_STATUS_DISCHARGING
            else:
                msg.power_supply_status = BatteryState.POWER_SUPPLY_STATUS_DISCHARGING

            msg.power_supply_health = BatteryState.POWER_SUPPLY_HEALTH_GOOD
            msg.power_supply_technology = BatteryState.POWER_SUPPLY_TECHNOLOGY_LION
            msg.present = True

            self.publisher_.publish(msg)
            self.get_logger().debug(f"Battery percentage: {current_pct:.1f}%, Docked: {self.sim.is_docked}")


def main(args=None):
    if HAVE_ROS2:
        rclpy.init(args=args)
        node = BatterySimulatorNode()
        try:
            rclpy.spin(node)
        except KeyboardInterrupt:
            pass
        node.destroy_node()
        rclpy.shutdown()
    else:
        print("Running BatterySimulator standalone test mode:")
        sim = BatterySimulator(initial_percentage=100.0, drain_rate_nav=2.0, charge_rate=5.0)
        sim.is_moving = True
        print(f"Initial: {sim.percentage:.1f}%")
        for i in range(5):
            sim.update(1.0)
            print(f"Step {i+1} (Navigating): {sim.percentage:.1f}%")
        sim.is_docked = True
        for i in range(5):
            sim.update(1.0)
            print(f"Step {i+6} (Charging): {sim.percentage:.1f}%")


if __name__ == '__main__':
    main()
