# tests/test_week1.py

import asyncio
from datetime import datetime, timedelta
import json
import pytest
import httpx

# Mock Redis class to intercept Redis calls and run tests without a real Redis server
class MockRedis:
    def __init__(self):
        self.store = {}

    def hgetall(self, name):
        return self.store.get(name, {})

    def hset(self, name, key, value):
        if name not in self.store:
            self.store[name] = {}
        self.store[name][key] = str(value)
        return 1

    def hdel(self, name, *keys):
        count = 0
        if name in self.store:
            for key in keys:
                if key in self.store[name]:
                    del self.store[name][key]
                    count += 1
        return count

# Inject MockRedis before importing the app so that health monitor and routes use it
import master.registry.node_registry as nr
mock_redis = MockRedis()
nr.redis_client = mock_redis

from master.main import app
from shared.models import NodeInfo, HeartbeatPayload
from master.registry.node_registry import nodes

@pytest.fixture
def anyio_backend():
    return "asyncio"

@pytest.fixture(autouse=True)
def clean_registry():
    """
    Ensure the registry and Redis mock store are clean before and after each test.
    """
    nodes.clear()
    mock_redis.store.clear()
    yield
    nodes.clear()
    mock_redis.store.clear()


@pytest.mark.anyio
async def test_register_and_get_nodes():
    """
    Test 1: Start master, register 2 workers, verify GET /nodes returns both.
    """
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
            node_1 = NodeInfo(
                node_id="worker-1",
                ip="192.168.1.11",
                port=8001,
                cpu_percent=10.0,
                ram_percent=20.0,
                active_tasks=0,
                status="healthy"
            )
            node_2 = NodeInfo(
                node_id="worker-2",
                ip="192.168.1.12",
                port=8001,
                cpu_percent=15.0,
                ram_percent=25.0,
                active_tasks=0,
                status="healthy"
            )

            # Register worker 1
            resp1 = await client.post("/nodes/register", json=json.loads(node_1.model_dump_json()))
            assert resp1.status_code == 200
            assert resp1.json()["node_id"] == "worker-1"

            # Register worker 2
            resp2 = await client.post("/nodes/register", json=json.loads(node_2.model_dump_json()))
            assert resp2.status_code == 200
            assert resp2.json()["node_id"] == "worker-2"

            # Verify GET /nodes returns both workers
            resp_get = await client.get("/nodes")
            assert resp_get.status_code == 200
            data = resp_get.json()
            assert len(data) == 2
            
            node_ids = {n["node_id"] for n in data}
            assert "worker-1" in node_ids
            assert "worker-2" in node_ids


@pytest.mark.anyio
async def test_worker_heartbeats_update_metrics():
    """
    Test 2: Send 5 heartbeats from a worker, verify cpu/ram updated on master.
    """
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
            # Register a worker first
            node_1 = NodeInfo(
                node_id="worker-1",
                ip="192.168.1.11",
                port=8001,
                cpu_percent=10.0,
                ram_percent=20.0,
                active_tasks=0,
                status="healthy"
            )
            resp = await client.post("/nodes/register", json=json.loads(node_1.model_dump_json()))
            assert resp.status_code == 200

            # Send 5 heartbeats from the worker with varying CPU, RAM, and active tasks values
            for i in range(1, 6):
                payload = HeartbeatPayload(
                    node_id="worker-1",
                    ip="192.168.1.11",
                    cpu_percent=10.0 + i,
                    ram_percent=20.0 + i,
                    active_tasks=i,
                    timestamp=datetime.utcnow()
                )
                resp_hb = await client.post("/heartbeat", json=json.loads(payload.model_dump_json()))
                assert resp_hb.status_code == 200

            # Verify that CPU/RAM and active tasks are updated on the master to the final heartbeat values
            resp_get = await client.get("/nodes/worker-1")
            assert resp_get.status_code == 200
            data = resp_get.json()
            assert data["cpu_percent"] == 15.0
            assert data["ram_percent"] == 25.0
            assert data["active_tasks"] == 5


@pytest.mark.anyio
async def test_dead_node_detection():
    """
    Test 3: Stop sending heartbeats, wait 20s (simulated by modifying timestamp), verify node status = 'dead'.
    """
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
            # Register a node
            node = NodeInfo(
                node_id="worker-dead",
                ip="192.168.1.11",
                port=8001,
                cpu_percent=10.0,
                ram_percent=20.0,
                active_tasks=0,
                status="healthy"
            )
            resp = await client.post("/nodes/register", json=json.loads(node.model_dump_json()))
            assert resp.status_code == 200

            # Stop sending heartbeats and simulate wait of 20 seconds by modifying node's last_heartbeat timestamp in-memory
            nodes["worker-dead"].last_heartbeat = datetime.utcnow() - timedelta(seconds=20)

            # Wait up to 6 seconds to allow the background health monitor task to complete its next check cycle (runs every 5s)
            await asyncio.sleep(6)

            # Verify the node status has transitioned to 'dead'
            resp_get = await client.get("/nodes/worker-dead")
            assert resp_get.status_code == 200
            assert resp_get.json()["status"] == "dead"


@pytest.mark.anyio
async def test_kill_and_restart_master_restores_registry():
    """
    Test 4: Kill master, restart, verify Redis restores node list.
    """
    # 1. Register a node in a running master instance
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
            node = NodeInfo(
                node_id="worker-persist",
                ip="192.168.1.13",
                port=8001,
                cpu_percent=5.0,
                ram_percent=15.0,
                active_tasks=0,
                status="healthy"
            )
            resp = await client.post("/nodes/register", json=json.loads(node.model_dump_json()))
            assert resp.status_code == 200

            # Confirm the node is saved to the Redis mock store
            assert "worker-persist" in mock_redis.store.get("nodes", {})

    # 2. Simulate "killing" master by clearing in-memory registry
    nodes.clear()
    assert len(nodes) == 0

    # 3. Simulate "restarting" master (which loads nodes from Redis during lifespan startup)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
            # Verify GET /nodes returns the restored list
            resp_get = await client.get("/nodes")
            assert resp_get.status_code == 200
            data = resp_get.json()
            assert len(data) == 1
            assert data[0]["node_id"] == "worker-persist"
            assert data[0]["ip"] == "192.168.1.13"
            assert data[0]["status"] == "healthy"
