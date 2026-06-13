# tests/test_heartbeat.py

import unittest
from datetime import datetime
from worker.health.heartbeat import collect_metrics
from shared.models import HeartbeatPayload, NodeInfo


class TestWorkerHeartbeat(unittest.TestCase):
    def test_collect_metrics(self):
        """
        Verify that collect_metrics() returns valid float percentages for CPU and RAM.
        """
        cpu, ram = collect_metrics()
        
        self.assertIsInstance(cpu, float)
        self.assertIsInstance(ram, float)
        
        # CPU and RAM percentages should be within [0.0, 100.0] range
        self.assertTrue(0.0 <= cpu <= 100.0, f"CPU percent {cpu} is out of bounds [0.0, 100.0]")
        self.assertTrue(0.0 <= ram <= 100.0, f"RAM percent {ram} is out of bounds [0.0, 100.0]")

    def test_heartbeat_payload(self):
        """
        Verify that building a HeartbeatPayload with collected metrics succeeds
        and validates correctly against our shared Pydantic models.
        """
        cpu, ram = collect_metrics()
        
        node_info = NodeInfo(
            node_id="test-node-123",
            ip="192.168.1.11",
            port=8001,
            cpu_percent=cpu,
            ram_percent=ram,
            active_tasks=2,
            status="healthy",
            last_heartbeat=datetime.utcnow()
        )
        
        payload = HeartbeatPayload(
            node_id=node_info.node_id,
            ip=node_info.ip,
            cpu_percent=cpu,
            ram_percent=ram,
            active_tasks=node_info.active_tasks,
            timestamp=datetime.utcnow()
        )
        
        self.assertEqual(payload.node_id, "test-node-123")
        self.assertEqual(payload.ip, "192.168.1.11")
        self.assertEqual(payload.cpu_percent, cpu)
        self.assertEqual(payload.ram_percent, ram)
        self.assertEqual(payload.active_tasks, 2)
        self.assertIsInstance(payload.timestamp, datetime)
