# tests/test_week1_worker.py

import asyncio
from datetime import datetime
import unittest
from unittest import IsolatedAsyncioTestCase
from unittest.mock import patch, AsyncMock, MagicMock

import httpx
from pydantic import ValidationError
from fastapi.testclient import TestClient

from shared.models import HeartbeatPayload, NodeInfo
from worker.health.heartbeat import collect_metrics, start_heartbeat
from worker.health.registrar import start_registration, build_node_info


# Custom exception to stop infinite loop in start_heartbeat
class StopHeartbeatLoop(Exception):
    pass


class TestWorkerWeek1(IsolatedAsyncioTestCase):

    # ── Test 1: Worker startup triggers registration POST to master ────────────
    @patch("worker.main.start_registration")
    @patch("worker.main.start_heartbeat")
    def test_app_lifespan_triggers_background_tasks(self, mock_hb, mock_reg):
        """
        Verify that when the FastAPI application starts up, the background tasks
        for registration and heartbeat are spawned.
        """
        from worker.main import app
        with TestClient(app):
            # TestClient startup triggers the FastAPI lifespan event
            pass
        mock_reg.assert_called_once()
        mock_hb.assert_called_once()

    @patch("httpx.AsyncClient.post", new_callable=AsyncMock)
    async def test_registration_post_request(self, mock_post):
        """
        Verify that start_registration makes a POST request to the correct master
        endpoint with the serialized NodeInfo payload.
        """
        node_info = NodeInfo(
            node_id="test-node-123",
            ip="192.168.1.11",
            port=8001,
            cpu_percent=0.0,
            ram_percent=0.0,
            active_tasks=0,
            status="healthy",
            last_heartbeat=datetime.utcnow(),
        )

        # Mock successful registration response
        mock_response = AsyncMock()
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        # Execute registrar
        await start_registration(node_info)

        # Verify POST request was made
        mock_post.assert_called_once()
        args, kwargs = mock_post.call_args
        
        # Verify endpoint URL
        self.assertTrue(args[0].endswith("/nodes/register"))
        
        # Verify payload content
        payload_data = kwargs["json"]
        self.assertEqual(payload_data["node_id"], "test-node-123")
        self.assertEqual(payload_data["ip"], "192.168.1.11")
        self.assertEqual(payload_data["port"], 8001)

    # ── Test 2: psutil returns valid CPU and RAM floats between 0-100 ─────────
    def test_psutil_metrics_range(self):
        """
        Verify that collect_metrics() retrieves CPU and RAM usage percentages
        as valid floats within the range [0.0, 100.0].
        """
        cpu, ram = collect_metrics()
        self.assertIsInstance(cpu, float)
        self.assertIsInstance(ram, float)
        self.assertTrue(0.0 <= cpu <= 100.0, f"CPU value {cpu} out of range [0-100]")
        self.assertTrue(0.0 <= ram <= 100.0, f"RAM value {ram} out of range [0-100]")

    @patch("psutil.cpu_percent")
    @patch("psutil.virtual_memory")
    def test_psutil_mocked_values(self, mock_vm, mock_cpu):
        """
        Verify that collect_metrics() correctly parses values returned by psutil.
        """
        mock_cpu.return_value = 42.5
        mock_mem = MagicMock()
        mock_mem.percent = 84.1
        mock_vm.return_value = mock_mem

        cpu, ram = collect_metrics()
        self.assertEqual(cpu, 42.5)
        self.assertEqual(ram, 84.1)

    # ── Test 3: Heartbeat payload matches HeartbeatPayload Pydantic model ─────
    def test_heartbeat_payload_exact_match(self):
        """
        Verify that HeartbeatPayload enforces all required fields and matches
        our shared Pydantic schema model exactly.
        """
        now = datetime.utcnow()
        payload = HeartbeatPayload(
            node_id="worker-node-abc",
            ip="192.168.1.12",
            cpu_percent=15.6,
            ram_percent=72.4,
            active_tasks=2,
            timestamp=now
        )

        self.assertEqual(payload.node_id, "worker-node-abc")
        self.assertEqual(payload.ip, "192.168.1.12")
        self.assertEqual(payload.cpu_percent, 15.6)
        self.assertEqual(payload.ram_percent, 72.4)
        self.assertEqual(payload.active_tasks, 2)
        self.assertEqual(payload.timestamp, now)

        # Check serialization behavior
        serialized = payload.model_dump()
        self.assertEqual(set(serialized.keys()), {
            "node_id", "ip", "cpu_percent", "ram_percent", "active_tasks", "timestamp"
        })

        # Check ValidationError for missing required fields
        with self.assertRaises(ValidationError):
            HeartbeatPayload(node_id="incomplete-node")

    # ── Test 4: Worker handles master being unreachable ──────────────────────
    @patch("worker.health.registrar._try_register", new_callable=AsyncMock)
    @patch("asyncio.sleep", new_callable=AsyncMock)
    async def test_registrar_retry_loop(self, mock_sleep, mock_try_register):
        """
        Verify that start_registration handles registration failures, logs warnings,
        calls sleep to retry, and continues until registration succeeds.
        """
        node_info = NodeInfo(
            node_id="retry-node",
            ip="192.168.1.11",
            port=8001,
            cpu_percent=0.0,
            ram_percent=0.0,
            active_tasks=0,
            status="healthy",
            last_heartbeat=datetime.utcnow(),
        )

        # Fail twice, then succeed
        mock_try_register.side_effect = [False, False, True]

        await start_registration(node_info)

        # Total registration attempts should be 3
        self.assertEqual(mock_try_register.call_count, 3)
        # Should have slept twice to retry
        self.assertEqual(mock_sleep.call_count, 2)

    @patch("httpx.AsyncClient.post", new_callable=AsyncMock)
    @patch("asyncio.sleep", new_callable=AsyncMock)
    async def test_heartbeat_unreachable_exception_handling(self, mock_sleep, mock_post):
        """
        Verify that start_heartbeat handles master connection errors, logs the event,
        does not crash, and moves on to the next heartbeat cycle.
        """
        node_info = NodeInfo(
            node_id="hb-error-node",
            ip="192.168.1.11",
            port=8001,
            cpu_percent=10.0,
            ram_percent=20.0,
            active_tasks=0,
            status="healthy",
            last_heartbeat=datetime.utcnow(),
        )

        # 1. Test ConnectError handling
        mock_post.side_effect = httpx.ConnectError("Connection refused")
        mock_sleep.side_effect = StopHeartbeatLoop("stop")

        with self.assertRaises(StopHeartbeatLoop):
            await start_heartbeat(node_info)

        mock_post.assert_called_once()
        mock_sleep.assert_called_once_with(5)

        # Reset mocks for next test scenario
        mock_post.reset_mock()
        mock_sleep.reset_mock()

        # 2. Test TimeoutException handling
        mock_post.side_effect = httpx.TimeoutException("Request timed out")
        mock_sleep.side_effect = StopHeartbeatLoop("stop")

        with self.assertRaises(StopHeartbeatLoop):
            await start_heartbeat(node_info)

        mock_post.assert_called_once()
        mock_sleep.assert_called_once_with(5)

        # Reset mocks for next test scenario
        mock_post.reset_mock()
        mock_sleep.reset_mock()

        # 3. Test generic unexpected exceptions
        mock_post.side_effect = RuntimeError("Unexpected internal system error")
        mock_sleep.side_effect = StopHeartbeatLoop("stop")

        with self.assertRaises(StopHeartbeatLoop):
            await start_heartbeat(node_info)

        mock_post.assert_called_once()
        mock_sleep.assert_called_once_with(5)
