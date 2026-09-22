import unittest
import time
from cstam_core.battery_simulator import BatterySimulator
from cstam_core.delivery_task_manager import TaskQueueManager, DEFAULT_WAYPOINTS
from cstam_core.docking_controller import AutoDockingController

class TestCstamCoreNodes(unittest.TestCase):

    def test_battery_simulator_drain_and_charge(self):
        sim = BatterySimulator(initial_percentage=100.0, drain_rate_idle=1.0, drain_rate_nav=5.0, charge_rate=10.0)
        self.assertEqual(sim.percentage, 100.0)

        # Test idle drain
        sim.is_moving = False
        sim.is_docked = False
        sim.update(dt=2.0)
        self.assertEqual(sim.percentage, 98.0)

        # Test navigation drain
        sim.is_moving = True
        sim.update(dt=2.0)
        self.assertEqual(sim.percentage, 88.0)

        # Test charge when docked
        sim.is_docked = True
        sim.update(dt=2.0)
        self.assertEqual(sim.percentage, 108.0 > 100.0 and 100.0)

    def test_battery_simulator_physical_mode(self):
        sim = BatterySimulator(initial_percentage=100.0, time_scale=1.0)
        self.assertEqual(sim.mode, "physical")
        self.assertEqual(sim.percentage, 100.0)
        self.assertGreater(sim.voltage, 28.0)

        # Idle discharge
        sim.is_moving = False
        sim.is_docked = False
        sim.update(dt=10.0)
        self.assertLessEqual(sim.percentage, 100.0)
        self.assertGreater(sim.current, 0.0)

        # Cruise discharge
        sim.is_moving = True
        sim.update(dt=10.0)
        self.assertGreater(sim.power, 100.0)

    def test_task_queue_manager(self):
        mgr = TaskQueueManager(low_battery_threshold=20.0)
        
        # Test request addition
        res = mgr.add_delivery_request("Table 1", "Soup & Water")
        self.assertTrue(res["success"])
        self.assertEqual(len(mgr.queue), 1)

        # Test unknown location error
        res_err = mgr.add_delivery_request("Table 99", "Coffee")
        self.assertFalse(res_err["success"])

        # Test task retrieval
        task = mgr.get_next_task()
        self.assertIsNotNone(task)
        self.assertEqual(task["target"], "Table 1")
        self.assertEqual(task["status"], "en_route")

        # Test task completion
        completed = mgr.complete_current_task(success=True)
        self.assertEqual(completed["status"], "completed")

    def test_low_battery_preemption(self):
        mgr = TaskQueueManager(low_battery_threshold=20.0)
        mgr.add_delivery_request("Table 2", "Pizza")
        
        # Simulate battery dropping below threshold
        mgr.update_battery(15.0)
        task = mgr.get_next_task()
        
        self.assertEqual(task["target"], "Dock")
        self.assertTrue(task.get("is_dock_task", False))

    def test_auto_docking_controller(self):
        ctrl = AutoDockingController(idle_timeout=5.0, low_battery_threshold=20.0, full_charge_threshold=90.0)
        
        # Normal state
        res = ctrl.evaluate_dock_trigger(queue_empty=False, is_navigating=True, current_time=100.0)
        self.assertEqual(res, 'none')

        # Low battery trigger
        ctrl.battery_percentage = 18.0
        res_low = ctrl.evaluate_dock_trigger(queue_empty=False, is_navigating=True, current_time=100.0)
        self.assertEqual(res_low, 'dock_low_battery')

        # Idle timeout trigger
        ctrl.battery_percentage = 80.0
        res_idle_1 = ctrl.evaluate_dock_trigger(queue_empty=True, is_navigating=False, current_time=100.0)
        self.assertEqual(res_idle_1, 'none')
        res_idle_2 = ctrl.evaluate_dock_trigger(queue_empty=True, is_navigating=False, current_time=106.0)
        self.assertEqual(res_idle_2, 'dock_idle')


if __name__ == '__main__':
    unittest.main()
