#!/usr/bin/env python3
"""
CSTAM Phase 1: Core Functionalities MVP Verification Suite
Tests:
1. Workspace & Phase 1 Deliverables Integrity
2. Mapping & Waypoints Data Integrity
3. Delivery Task Management Queue Lifecycle
4. Auto-Docking State Machine Idle Triggers
"""

import sys
import os
import unittest
import json

# Insert path for cstam_core
sys.path.insert(0, os.path.abspath('ros2_ws/src/cstam_core'))

from cstam_core.delivery_task_manager import TaskQueueManager, DEFAULT_WAYPOINTS
from cstam_core.docking_controller import AutoDockingController


class Phase1SystemVerificationTests(unittest.TestCase):

    def test_phase1_files_exist(self):
        required_paths = [
            "ros2_ws/src/cstam_gazebo/package.xml",
            "ros2_ws/src/cstam_gazebo/urdf/cstam_robot.urdf.xacro",
            "ros2_ws/src/cstam_gazebo/worlds/restaurant.world",
            "ros2_ws/src/cstam_gazebo/launch/spawn_cstam_robot.launch.py",
            "ros2_ws/src/cstam_navigation/package.xml",
            "ros2_ws/src/cstam_navigation/config/nav2_params.yaml",
            "ros2_ws/src/cstam_navigation/config/waypoints.yaml",
            "ros2_ws/src/cstam_navigation/config/cstam_nav2.rviz",
            "ros2_ws/src/cstam_navigation/maps/cstam_map.yaml",
            "ros2_ws/src/cstam_navigation/maps/cstam_map.pgm",
            "ros2_ws/src/cstam_core/package.xml",
            "ros2_ws/src/cstam_core/cstam_core/delivery_task_manager.py",
            "ros2_ws/src/cstam_core/cstam_core/docking_controller.py",
            "ros2_ws/src/cstam_core/launch/cstam_system.launch.py",
            "delivery_simulator_ui.py",
            "run_delivery_simulator.sh",
            "run_autonomous_system.sh",
            "run_mapping_demo.sh"
        ]
        for rel_path in required_paths:
            full_p = os.path.normpath(os.path.join(os.getcwd(), rel_path))
            self.assertTrue(os.path.exists(full_p), f"Missing required Phase 1 deliverable: {rel_path}")

    def test_predefined_waypoints(self):
        # 24 tables + Kitchen + Dock
        self.assertIn("Dock", DEFAULT_WAYPOINTS)
        self.assertIn("Kitchen/Pickup", DEFAULT_WAYPOINTS)
        for i in range(24):
            self.assertIn(f"Table {i}", DEFAULT_WAYPOINTS)
            wp = DEFAULT_WAYPOINTS[f"Table {i}"]
            self.assertIn("x", wp)
            self.assertIn("y", wp)

    def test_delivery_queue_lifecycle(self):
        mgr = TaskQueueManager()
        
        # 1. Add deliveries
        r1 = mgr.add_delivery_request("Table 1", "Espresso & Croissant")
        r2 = mgr.add_delivery_request("Table 2", "Burger & Fries")
        r3 = mgr.add_delivery_request("Kitchen/Pickup", "Order Pick Up")

        self.assertTrue(r1["success"])
        self.assertTrue(r2["success"])
        self.assertTrue(r3["success"])
        self.assertEqual(mgr.get_status_summary()["queue_length"], 3)

        # 2. Dispatch Task 1
        t1 = mgr.get_next_task()
        self.assertIsNotNone(t1)
        self.assertEqual(t1["target"], "Table 1")
        self.assertEqual(t1["status"], "en_route")

        # 3. Complete Task 1
        done1 = mgr.complete_current_task(success=True)
        self.assertEqual(done1["status"], "completed")
        self.assertEqual(mgr.get_status_summary()["completed_count"], 1)
        self.assertEqual(mgr.get_status_summary()["queue_length"], 2)

    def test_auto_docking_idle_triggers(self):
        ctrl = AutoDockingController(idle_timeout=15.0)
        now = 1000.0

        # Normal operation
        self.assertEqual(ctrl.evaluate_dock_trigger(queue_empty=False, is_navigating=True, current_time=now), 'none')

        # Idle trigger after 15 seconds
        ctrl.evaluate_dock_trigger(queue_empty=True, is_navigating=False, current_time=now)
        trigger_idle = ctrl.evaluate_dock_trigger(queue_empty=True, is_navigating=False, current_time=now + 16.0)
        self.assertEqual(trigger_idle, 'dock_idle')

    def test_task_queue_modify_and_delete(self):
        mgr = TaskQueueManager()
        r1 = mgr.add_delivery_request("Table 3", "Espresso")
        r2 = mgr.add_delivery_request("Table 5", "Salad")
        self.assertEqual(mgr.get_status_summary()["queue_length"], 2)

        task_id_1 = r1["task"]["id"]
        task_id_2 = r2["task"]["id"]

        # Modify Table and Item of Task 1
        mod_ok = mgr.modify_task(task_id_1, new_target="Table 10", new_item="Cappuccino & Muffin")
        self.assertTrue(mod_ok)
        pending = mgr.get_status_summary()["pending_tasks"]
        self.assertEqual(pending[0]["target"], "Table 10")
        self.assertEqual(pending[0]["item"], "Cappuccino & Muffin")

        # Delete Task 2
        del_ok = mgr.delete_task(task_id_2)
        self.assertTrue(del_ok)
        self.assertEqual(mgr.get_status_summary()["queue_length"], 1)

        # Invalid task ID operations return False
        self.assertFalse(mgr.modify_task("INVALID_ID", "Table 1"))
        self.assertFalse(mgr.delete_task("INVALID_ID"))


if __name__ == '__main__':
    unittest.main()
