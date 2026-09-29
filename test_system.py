import sys
import os
import unittest
import json

# Insert path for cstam_core & cstam_web_bridge
sys.path.insert(0, os.path.abspath('ros2_ws/src/cstam_core'))
sys.path.insert(0, os.path.abspath('cstam_web_bridge'))

from cstam_core.battery_simulator import BatterySimulator
from cstam_core.delivery_task_manager import TaskQueueManager
from cstam_core.docking_controller import AutoDockingController
from fastapi.testclient import TestClient
from app import app


class MasterSystemVerificationTests(unittest.TestCase):

    def setUp(self):
        self.web_client = TestClient(app)

    def test_workspace_files_exist(self):
        required_paths = [
            "ros2_ws/src/cstam_gazebo/package.xml",
            "ros2_ws/src/cstam_gazebo/urdf/cstam_robot.urdf.xacro",
            "ros2_ws/src/cstam_gazebo/worlds/restaurant.world",
            "ros2_ws/src/cstam_gazebo/launch/spawn_cstam_robot.launch.py",
            "ros2_ws/src/cstam_navigation/package.xml",
            "ros2_ws/src/cstam_navigation/config/nav2_params.yaml",
            "ros2_ws/src/cstam_navigation/config/waypoints.yaml",
            "ros2_ws/src/cstam_navigation/maps/cstam_map.yaml",
            "ros2_ws/src/cstam_navigation/maps/cstam_map.pgm",
            "ros2_ws/src/cstam_core/package.xml",
            "ros2_ws/src/cstam_core/cstam_core/battery_simulator.py",
            "ros2_ws/src/cstam_core/cstam_core/delivery_task_manager.py",
            "ros2_ws/src/cstam_core/cstam_core/docking_controller.py",
            "ros2_ws/src/cstam_core/launch/cstam_system.launch.py",
            "cstam_web_bridge/app.py",
            "cstam_web_bridge/static/index.html",
            "cstam_web_bridge/static/styles.css",
            "cstam_web_bridge/static/dashboard.js",
            "run_demo.py"
        ]
        for rel_path in required_paths:
            full_p = os.path.normpath(os.path.join(os.getcwd(), rel_path))
            self.assertTrue(os.path.exists(full_p), f"Missing required deliverable: {rel_path} (Full path: {full_p})")

    def test_web_bridge_full_lifecycle(self):
        # 1. Health
        h = self.web_client.get("/api/health")
        self.assertEqual(h.status_code, 200)

        # 2. Submit 3 Deliveries
        d1 = self.web_client.post("/api/delivery", json={"target": "Table 1", "item": "Coffee"})
        d2 = self.web_client.post("/api/delivery", json={"target": "Table 2", "item": "Tea"})
        d3 = self.web_client.post("/api/delivery", json={"target": "Table 3", "item": "Water"})
        
        self.assertEqual(d1.status_code, 200)
        self.assertEqual(d2.status_code, 200)
        self.assertEqual(d3.status_code, 200)

        # 3. Check Queue
        q = self.web_client.get("/api/queue").json()
        self.assertGreaterEqual(len(q["queue"]) + (1 if q["current_task"] else 0), 3)

        # 4. Trigger Obstacle
        obs = self.web_client.post("/api/obstacle/trigger", json={"active": True})
        self.assertTrue(obs.json()["dynamic_obstacle_active"])

        # 5. Clear Queue
        cl = self.web_client.delete("/api/queue")
        self.assertTrue(cl.json()["success"])


if __name__ == '__main__':
    unittest.main()
