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
        self.assertEqual(data["service"], "CSTAM Waiter Robot Web Bridge")

    def test_waypoints_endpoint(self):
        response = self.client.get("/api/waypoints")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("Table 0", data)
        self.assertIn("Table 1", data)
        self.assertIn("Table 23", data)
        self.assertIn("Dock", data)
        self.assertIn("Kitchen/Pickup", data)

    def test_map_layout_endpoint(self):
        response = self.client.get("/api/map/layout")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("walls", data)
        self.assertIn("tables", data)
        self.assertEqual(len(data["tables"]), 24)

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

    def test_trigger_low_battery(self):
        res = self.client.post("/api/battery/low")
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["success"])
        self.assertEqual(res.json()["battery_percentage"], 15.0)

    def test_dock_charge_option(self):
        # 1. Get dock charge option
        get_res = self.client.get("/api/dock/charge_option")
        self.assertEqual(get_res.status_code, 200)
        self.assertIn("auto_charge_at_dock", get_res.json())

        # 2. Toggle dock charge option
        post_res = self.client.post("/api/dock/charge_option", json={"auto_charge": True})
        self.assertEqual(post_res.status_code, 200)
        self.assertTrue(post_res.json()["auto_charge_at_dock"])

        # 3. Trigger start charge at dock
        charge_res = self.client.post("/api/dock/start_charge")
        self.assertEqual(charge_res.status_code, 200)
        self.assertTrue(charge_res.json()["success"])


if __name__ == '__main__':
    unittest.main()
