import unittest
from fastapi.testclient import TestClient
from app import app

class TestCstamWebBridge(unittest.TestCase):

    def setUp(self):
        self.client = TestClient(app)

    def test_health_endpoint(self):
        response = self.client.get("/api/health")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["status"], "ok")
        self.assertEqual(data["service"], "CSTAM Web Bridge")

    def test_waypoints_endpoint(self):
        response = self.client.get("/api/waypoints")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("Table 1", data)
        self.assertIn("Dock", data)

    def test_delivery_request_and_queue(self):
        # 1. Submit Delivery
        payload = {"target": "Table 1", "item": "Espresso & Muffin"}
        res = self.client.post("/api/delivery", json=payload)
        self.assertEqual(res.status_code, 200)
        res_data = res.json()
        self.assertTrue(res_data["success"])
        self.assertEqual(res_data["task"]["target"], "Table 1")

        # 2. Check Queue
        q_res = self.client.get("/api/queue")
        self.assertEqual(q_res.status_code, 200)
        q_data = q_res.json()
        self.assertGreaterEqual(len(q_data["queue"]) + (1 if q_data["current_task"] else 0), 1)

    def test_manual_dock_command(self):
        res = self.client.post("/api/dock")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["success"])

    def test_toggle_obstacle(self):
        res = self.client.post("/api/obstacle/trigger", json={"active": True})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["dynamic_obstacle_active"])


if __name__ == '__main__':
    unittest.main()
