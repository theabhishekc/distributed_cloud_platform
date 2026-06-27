# tests/test_week2_integration.py
#
# Week 2 integration test suite for the Compute Engine.
#
# Tests:
#   1. Scheduler scoring — 3 nodes with different CPU/RAM; verify best node chosen.
#   2. NoHealthyNodeError — raised when all nodes are dead or none registered.
#   3. Task repository CRUD — using async SQLite in-memory (no PostgreSQL needed).
#   4. Docker runner — real alpine echo hello container (skipped if Docker unavailable).
#   5. Task queue semaphore — enqueue 6 tasks, verify active_tasks never exceeds 3.

import asyncio
import sys
import uuid
from datetime import datetime
from typing import AsyncGenerator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ── Pytest-anyio backend ──────────────────────────────────────────────────────

@pytest.fixture
def anyio_backend():
    return "asyncio"


# =============================================================================
# TEST 1 & 2: Scheduler scoring + NoHealthyNodeError
# =============================================================================

class TestScheduler:
    """Tests for master/scheduler/scheduler.py"""

    def _make_node(self, node_id: str, cpu: float, ram: float, active: int, status: str = "healthy"):
        """Helper to build a NodeInfo."""
        from shared.models import NodeInfo
        return NodeInfo(
            node_id       = node_id,
            ip            = "192.168.1.10",
            port          = 8001,
            cpu_percent   = cpu,
            ram_percent   = ram,
            active_tasks  = active,
            status        = status,
            last_heartbeat= datetime.utcnow(),
        )

    def _make_task(self) -> "TaskRequest":
        from shared.models import TaskRequest
        return TaskRequest(
            task_id      = str(uuid.uuid4()),
            image        = "alpine",
            command      = "echo test",
        )

    def test_select_worker_picks_highest_score(self):
        """
        Three nodes with clearly differentiated resources.
        The one with lowest CPU + RAM + tasks should win.
        score = (1-cpu/100)*0.5 + (1-ram/100)*0.3 + (1-tasks/10)*0.2
        """
        import master.registry.node_registry as nr
        from master.scheduler.scheduler import select_worker

        node_a = self._make_node("worker-a", cpu=80.0, ram=70.0, active=5)  # busy
        node_b = self._make_node("worker-b", cpu=20.0, ram=30.0, active=1)  # best
        node_c = self._make_node("worker-c", cpu=50.0, ram=50.0, active=3)  # mid

        original_nodes = dict(nr.nodes)
        try:
            nr.nodes.clear()
            nr.nodes["worker-a"] = node_a
            nr.nodes["worker-b"] = node_b
            nr.nodes["worker-c"] = node_c

            task   = self._make_task()
            result = select_worker(task)

            assert result.chosen_worker_id == "worker-b", (
                f"Expected worker-b (lowest load), got {result.chosen_worker_id}"
            )
            assert result.score > 0
            assert "cpu:" in result.reason
            assert "ram:" in result.reason
            assert "tasks:" in result.reason
        finally:
            nr.nodes.clear()
            nr.nodes.update(original_nodes)

    def test_scheduler_score_formula(self):
        """Verify the exact scoring formula values match the spec."""
        from master.scheduler.scheduler import _score
        from shared.models import NodeInfo

        node = NodeInfo(
            node_id       = "test",
            ip            = "1.2.3.4",
            port          = 8001,
            cpu_percent   = 50.0,
            ram_percent   = 40.0,
            active_tasks  = 5,
            status        = "healthy",
            last_heartbeat= datetime.utcnow(),
        )
        # score = (1-0.5)*0.5 + (1-0.4)*0.3 + (1-0.5)*0.2
        #       = 0.25 + 0.18 + 0.10 = 0.53
        expected = round(0.25 + 0.18 + 0.10, 4)
        assert _score(node) == expected

    def test_no_healthy_node_error_when_empty(self):
        """NoHealthyNodeError raised when no nodes are registered."""
        import master.registry.node_registry as nr
        from master.scheduler.scheduler import NoHealthyNodeError, select_worker

        original_nodes = dict(nr.nodes)
        try:
            nr.nodes.clear()
            with pytest.raises(NoHealthyNodeError):
                select_worker(self._make_task())
        finally:
            nr.nodes.clear()
            nr.nodes.update(original_nodes)

    def test_no_healthy_node_error_when_all_dead(self):
        """NoHealthyNodeError raised when all registered nodes are dead."""
        import master.registry.node_registry as nr
        from master.scheduler.scheduler import NoHealthyNodeError, select_worker

        dead_a = self._make_node("dead-a", cpu=10.0, ram=10.0, active=0, status="dead")
        dead_b = self._make_node("dead-b", cpu=20.0, ram=20.0, active=0, status="dead")

        original_nodes = dict(nr.nodes)
        try:
            nr.nodes.clear()
            nr.nodes["dead-a"] = dead_a
            nr.nodes["dead-b"] = dead_b

            with pytest.raises(NoHealthyNodeError):
                select_worker(self._make_task())
        finally:
            nr.nodes.clear()
            nr.nodes.update(original_nodes)


# =============================================================================
# TEST 3: Task repository CRUD with async SQLite
# =============================================================================

@pytest.fixture
async def async_db_session() -> AsyncGenerator:
    """
    Provide a fresh async SQLite in-memory session for each test.
    This avoids needing a real PostgreSQL instance in CI or dev machines.

    SQLite does not support the PostgreSQL ENUM type, so we use
    native_enum=False to store enum values as strings.
    """
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
    from sqlalchemy import event
    from master.db.models import Base, TaskStatusDB
    import sqlalchemy as sa

    # Use in-memory SQLite
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )

    # SQLite needs this for FK constraints
    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragma(dbapi_conn, _):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    # Create tables — enum stored as VARCHAR for SQLite compatibility
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with factory() as session:
        yield session

    await engine.dispose()


@pytest.mark.anyio
async def test_task_repository_create_and_get(async_db_session):
    """Create a task, retrieve it, verify fields match."""
    from master.db import task_repository as repo
    from shared.models import TaskRequest, TaskStatus

    task = TaskRequest(
        task_id      = str(uuid.uuid4()),
        image        = "alpine",
        command      = "echo hello",
        cpu_limit    = 0.5,
        ram_limit_mb = 256,
        priority     = 1,
        retry_count  = 0,
        max_retries  = 3,
    )

    created = await repo.create_task(async_db_session, task)
    assert created.task_id  == task.task_id
    assert created.image    == "alpine"
    assert created.status.value == TaskStatus.PENDING.value

    fetched = await repo.get_task(async_db_session, task.task_id)
    assert fetched is not None
    assert fetched.task_id == task.task_id


@pytest.mark.anyio
async def test_task_repository_update_status(async_db_session):
    """Update task status and verify the change persists."""
    from master.db import task_repository as repo
    from shared.models import TaskRequest, TaskStatus

    task = TaskRequest(
        task_id      = str(uuid.uuid4()),
        image        = "alpine",
        command      = "sleep 1",
    )
    await repo.create_task(async_db_session, task)

    updated = await repo.update_task_status(
        async_db_session,
        task.task_id,
        status             = TaskStatus.SCHEDULED,
        assigned_worker_id = "worker-abc",
    )
    assert updated is not None
    assert updated.status.value        == TaskStatus.SCHEDULED.value
    assert updated.assigned_worker_id  == "worker-abc"


@pytest.mark.anyio
async def test_task_repository_list_and_filter(async_db_session):
    """Create tasks with different statuses, verify list filter works."""
    from master.db import task_repository as repo
    from shared.models import TaskRequest, TaskStatus

    ids = [str(uuid.uuid4()) for _ in range(3)]
    for i, tid in enumerate(ids):
        t = TaskRequest(task_id=tid, image="alpine", command=f"echo {i}")
        await repo.create_task(async_db_session, t)

    # Mark one as SCHEDULED
    await repo.update_task_status(async_db_session, ids[0], status=TaskStatus.SCHEDULED)

    all_tasks = await repo.list_tasks(async_db_session)
    assert len(all_tasks) == 3

    pending = await repo.list_tasks(async_db_session, status=TaskStatus.PENDING)
    assert len(pending) == 2

    scheduled = await repo.list_tasks(async_db_session, status=TaskStatus.SCHEDULED)
    assert len(scheduled) == 1


@pytest.mark.anyio
async def test_task_repository_cancel(async_db_session):
    """Cancel a task and verify it transitions to CANCELLED."""
    from master.db import task_repository as repo
    from shared.models import TaskRequest, TaskStatus

    task = TaskRequest(task_id=str(uuid.uuid4()), image="alpine", command="sleep 60")
    await repo.create_task(async_db_session, task)

    cancelled = await repo.cancel_task(async_db_session, task.task_id)
    assert cancelled is not None
    assert cancelled.status.value == TaskStatus.CANCELLED.value


# =============================================================================
# TEST 4: Docker runner — real alpine container
# =============================================================================

def _docker_available() -> bool:
    """Return True if Docker daemon is reachable on this machine."""
    try:
        import docker
        docker.from_env().ping()
        return True
    except Exception:
        return False


@pytest.mark.anyio
@pytest.mark.skipif(not _docker_available(), reason="Docker daemon not available on this machine")
async def test_docker_runner_alpine_echo():
    """
    Run `alpine echo hello world` for real.
    Verifies: TaskResult.status == COMPLETED, output contains 'hello'.
    """
    from worker.executor.docker_runner import run_task
    from shared.models import TaskRequest, TaskStatus

    task = TaskRequest(
        task_id      = str(uuid.uuid4()),
        image        = "alpine",
        command      = "echo hello world",
        cpu_limit    = 0.5,
        ram_limit_mb = 128,
    )

    result = await run_task(task, worker_id="test-runner")

    assert result.task_id         == task.task_id
    assert result.status          == TaskStatus.COMPLETED
    assert result.output is not None
    assert "hello" in result.output
    assert result.duration_seconds >= 0


@pytest.mark.anyio
@pytest.mark.skipif(not _docker_available(), reason="Docker daemon not available on this machine")
async def test_docker_runner_returns_failed_on_bad_command():
    """
    Run a command that exits non-zero.
    Verifies TaskResult.status == FAILED and error is populated.
    """
    from worker.executor.docker_runner import run_task
    from shared.models import TaskRequest, TaskStatus

    task = TaskRequest(
        task_id      = str(uuid.uuid4()),
        image        = "alpine",
        command      = "sh -c 'exit 1'",
        cpu_limit    = 0.25,
        ram_limit_mb = 64,
    )

    result = await run_task(task, worker_id="test-runner")

    assert result.task_id == task.task_id
    assert result.status  == TaskStatus.FAILED


# =============================================================================
# TEST 5: Task queue semaphore limits concurrency to MAX_CONCURRENT_TASKS
# =============================================================================

@pytest.mark.anyio
async def test_task_queue_semaphore_limits_concurrency():
    """
    Enqueue 6 tasks with a mocked docker_runner that counts peak concurrency.
    The semaphore must keep active_tasks ≤ MAX_CONCURRENT_TASKS (3) at all times.
    """
    import worker.executor.task_queue as tq
    from shared.models import TaskRequest, TaskStatus

    # Reset queue module state for this test
    tq._queue     = asyncio.Queue()
    tq._semaphore = asyncio.Semaphore(3)       # cap = 3
    tq.RESULT_STORE.clear()
    tq._active_tasks = 0

    peak_active: list[int] = []

    async def fake_run_task(task: TaskRequest, worker_id: str):
        """Simulates a slow container — records peak active count."""
        from shared.models import TaskResult, TaskStatus as TS
        peak_active.append(tq._active_tasks)
        await asyncio.sleep(0.05)              # simulate container runtime
        return TaskResult(
            task_id          = task.task_id,
            worker_id        = worker_id,
            status           = TS.COMPLETED,
            output           = "done",
            error            = None,
            started_at       = datetime.utcnow(),
            completed_at     = datetime.utcnow(),
            duration_seconds = 0.05,
        )

    with patch("worker.executor.task_queue.run_task", side_effect=fake_run_task):
        # Enqueue 6 tasks
        tasks = [
            TaskRequest(
                task_id  = str(uuid.uuid4()),
                image    = "alpine",
                command  = f"echo {i}",
            )
            for i in range(6)
        ]
        for t in tasks:
            await tq.enqueue_task(t)

        # Start the worker loop
        loop_task = asyncio.create_task(tq.start_worker_loop(worker_id="test-worker"))

        # Give time for all 6 tasks to complete
        await asyncio.sleep(1.0)
        loop_task.cancel()

    # Verify all 6 task results stored (placeholder overwritten by final result)
    assert len(tq.RESULT_STORE) == 6, (
        f"Expected 6 results in RESULT_STORE, got {len(tq.RESULT_STORE)}"
    )

    # Verify peak concurrency never exceeded 3
    assert all(p <= 3 for p in peak_active), (
        f"Semaphore breach! Peak active counts: {peak_active}"
    )
