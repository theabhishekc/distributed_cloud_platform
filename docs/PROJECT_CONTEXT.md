# Mini Distributed Cloud Platform — Project Context

## What This Project Is
A production-level distributed cloud platform built across 4 laptops that simulates core AWS functionality. It is NOT using Kubernetes or any existing orchestration — the orchestration logic is built from scratch. This is the entire point.

Two developers building it collaboratively in 4 weeks (3–4 hrs/day each), both at intermediate level (comfortable with Python, Docker, REST APIs).

---

## Hardware Setup
- 4 laptops connected over **WiFi (current setup)** — planned upgrade to wired Ethernet later
- All 4 machines must be on the **same WiFi network/router** (not different subnets)
- WiFi caveats to keep in mind:
  - Heartbeat interval kept at 5s (lenient enough for WiFi jitter)
  - Dead-node timeout set to 15s (3 missed beats) — increase to 20s if false positives occur on WiFi
  - Large file chunk uploads may be slower — chunk size kept at 1MB (not larger)
  - Stress tests may show higher latency variance than wired — this is expected
- **When shifting to wired:** plug into a switch, reassign static IPs if they change, re-run all tests — no code changes needed since IPs are in config, not hardcoded
- Static IPs assigned (set these as DHCP reservations in router, or configure manually):
  - Master node: 192.168.1.10
  - Worker 1:    192.168.1.11
  - Worker 2:    192.168.1.12
  - Worker 3:    192.168.1.13
- All machines run Ubuntu, Python 3.10+, Docker Engine, Git, Redis (master), PostgreSQL (master)

---

## Architecture

```
[ User / CLI ]
      ↓  HTTP
[ Master Node :8000 ]
  ├── API Gateway          (FastAPI)
  ├── Task Scheduler       (resource-aware, custom Python)
  ├── Node Registry        (in-memory dict + Redis backup)
  ├── Load Balancer        (part of scheduler)
  ├── Storage Manager      (chunk orchestration + replication)
  ├── Function Store       (Lambda code storage)
  └── PostgreSQL DB        (tasks, files, logs metadata)
      ↓  HTTP over LAN
[ Worker Nodes :8001 ]
  ├── Task Executor        (Docker SDK)
  ├── Task Queue           (asyncio.Queue, semaphore)
  ├── Local Storage        (/tmp/minicloud-storage/{node_id}/)
  ├── Function Runner      (Docker mount execution)
  └── Health Reporter      (psutil + heartbeat POST every 5s)
```

---

## Tech Stack (Final Decisions — Do Not Re-debate These)

| Layer | Technology | Reason |
|---|---|---|
| API framework | FastAPI (Python) | Async, auto-docs, both nodes |
| Containerization | Docker + docker-py SDK | Task and function isolation |
| Scheduling | Custom resource-aware | Laptops have unequal specs |
| Node registry | In-memory dict + Redis | Fast reads + restart recovery |
| Async queue | Redis Streams (Phase 6) | Durable, consumer groups |
| Storage | Custom replication engine | Learn why S3 works the way it does |
| Function exec | Docker (fresh container per call) | Isolation, no cold start reuse |
| Monitoring | Prometheus + Grafana | Industry standard |
| Logging | Structured JSON → PostgreSQL | Queryable by task_id, node |
| Master DB | PostgreSQL + SQLAlchemy async | Task state, file metadata |
| Inter-node comms | REST over HTTP | Readable, debuggable |
| Code sync | Git + SSH, GitHub | Feature branch per person per day |

---

## Repository Structure

```
mini-cloud/
  master/
    api/              ← FastAPI route handlers
    scheduler/        ← Scheduling + task reaper
    registry/         ← Node registry + health monitor
    db/               ← SQLAlchemy models + repositories
    storage/          ← Upload orchestrator + replication monitor
    functions/        ← Function store
  worker/
    api/              ← FastAPI route handlers
    executor/         ← Docker runner + task queue
    storage/          ← Local chunk handler
    functions/        ← Lambda runner
    health/           ← Registrar + heartbeat sender
  shared/
    models.py         ← All Pydantic models (source of truth)
    logger.py         ← Structured JSON logger
  infra/
    docker-compose.yml
    prometheus.yml
    grafana/          ← Dashboard JSON exports
  tests/
    test_models.py
    test_scheduler.py
    test_task_repo.py
    test_week1.py
    test_week2_integration.py
    test_storage.py
    test_lambda.py
    test_stress.py
  docs/
    ARCHITECTURE.md   ← Decision records (why, not just what)
  README.md
```

---

## Shared Pydantic Models (shared/models.py) — Source of Truth

```python
# Node models
class NodeInfo:
    node_id: str          # uuid4
    ip: str               # LAN IP (not 127.0.0.1)
    port: int
    cpu_percent: float    # 0–100
    ram_percent: float    # 0–100
    active_tasks: int
    status: str           # 'healthy' | 'degraded' | 'dead'
    last_heartbeat: datetime

class HeartbeatPayload:
    node_id: str
    ip: str
    cpu_percent: float
    ram_percent: float
    active_tasks: int
    timestamp: datetime

# Task models
class TaskStatus(Enum):
    PENDING | SCHEDULED | RUNNING | COMPLETED | FAILED | CANCELLED

class TaskRequest:
    task_id: str          # auto uuid
    image: str            # Docker image name
    command: str          # command to run inside container
    cpu_limit: float      # default 0.5 cores
    ram_limit_mb: int     # default 256
    priority: int         # default 1
    retry_count: int      # default 0
    max_retries: int      # default 3

class TaskResult:
    task_id: str
    worker_id: str
    status: TaskStatus
    output: str
    error: str
    started_at: datetime
    completed_at: datetime
    duration_seconds: float

class SchedulerDecision:
    task_id: str
    chosen_worker_id: str
    reason: str           # e.g. "cpu:45%,ram:30%,tasks:1"
    score: float

# Storage models
class FileChunk:
    chunk_id: str
    file_id: str
    chunk_index: int
    size_bytes: int
    checksum: str         # MD5
    worker_id: str

class FileMetadata:
    file_id: str
    filename: str
    total_size: int
    chunk_count: int
    replication_factor: int   # default 2
    created_at: datetime
    status: str           # 'available' | 'degraded' | 'lost'

# Function (Lambda) models
class FunctionDef:
    function_id: str
    name: str
    code: str             # Python source as string
    runtime: str          # default 'python3.11'
    created_at: datetime

class InvokeRequest:
    function_id: str
    payload: dict
    timeout_seconds: int  # default 30

class InvokeResult:
    function_id: str
    output: str
    error: str
    duration_ms: int
    worker_id: str
```

---

## Key Algorithms

### Scheduler Scoring Formula
```
score(node) = (1 - cpu_percent/100)  * 0.5
            + (1 - ram_percent/100)   * 0.3
            + (1 - active_tasks/MAX)  * 0.2

Higher score = better candidate. Pick the highest.
Raise NoHealthyNodeError if all nodes are dead.
```

### Heartbeat Dead Detection
```
Interval:  worker POSTs every 5 seconds
Timeout:   3 missed beats (15 seconds) → status = 'dead'
Recovery:  node re-registers → status = 'healthy'
```

### File Replication
```
Replication factor: 2 (each chunk stored on 2 different workers)
On upload:   chunk → worker_A + worker_B, verify MD5 checksum on both
On failure:  replication_monitor runs every 60s, detects under-replicated
             chunks, re-replicates from surviving replica to a new worker
On download: try primary worker first, fall back to replica
```

### Lambda Execution
```
1. Write user code to /tmp/fn_{id}.py
2. Inject PAYLOAD = {json.dumps(payload)} at top of file
3. docker run --rm -v /tmp/fn_{id}.py:/app/handler.py
              --memory=128m --cpus=0.25 --network=none
              python:3.11-slim python /app/handler.py
4. Capture stdout as output, stderr as error
5. Delete temp file
```

---

## GitHub Branch Strategy

```
main        ← always working, merge weekly after full test
  └── dev   ← integration branch, merge daily after EOD sync
        ├── feat/A-{feature}   ← Person A daily branch
        └── feat/B-{feature}   ← Person B daily branch
```

Daily flow:
1. `git pull origin dev` → create `feat/A-today-feature`
2. Work all day on that branch
3. EOD: open PR into dev, review friend's PR, merge both
4. Weekly: `dev` → `main` after all tests pass

---

## Build Phases (Do Not Skip or Reorder)

| Phase | Week | What Gets Built |
|---|---|---|
| 1 | Week 1 | Node registration, heartbeat, dead detection, Redis registry, structured logging |
| 2 | Week 2 | Task DB/ORM, scheduler, Docker execution, concurrency, task reaper, retry |
| 3 | Week 3 | Chunked file storage, 2x replication, re-replication monitor, Lambda runner |
| 4 | Week 4 | Prometheus metrics, Grafana dashboards, log aggregation, stress tests, Redis Streams |

---

## Ports Reference

| Service | Port | Machine |
|---|---|---|
| Master FastAPI | 8000 | 192.168.1.10 |
| Worker FastAPI | 8001 | .11, .12, .13 |
| PostgreSQL | 5432 | 192.168.1.10 |
| Redis | 6379 | 192.168.1.10 |
| Prometheus | 9090 | 192.168.1.10 |
| Grafana | 3000 | 192.168.1.10 |

---

## Design Decisions Already Made (Do Not Re-debate)

- **No Kubernetes** — we are simulating orchestration, not using it
- **No Kafka** — Redis Streams is sufficient for 4 laptops
- **No gRPC** — REST is more debuggable for learning purposes
- **No erasure coding** — replication factor 2 is sufficient
- **No MinIO** — building custom replication teaches the fundamentals
- **No Docker Desktop** — Docker Engine only on all machines
- **Eventual consistency** for storage — AP system (not CP)
- **Async SQLAlchemy** — FastAPI is async, sync DB calls block the event loop
- **Resource-aware scheduling** over round-robin — laptops have unequal specs
- **Separate Pydantic models from ORM models** — validation layer stays clean

---

## Current Status
> Update this section as the project progresses.

- [ ] Week 1 — Foundation
- [ ] Week 2 — Compute Engine
- [ ] Week 3 — Storage + Lambda
- [ ] Week 4 — Monitoring + Hardening

---

## Common Commands

```bash
# Start master
cd mini-cloud && uvicorn master.main:app --host 0.0.0.0 --port 8000 --reload

# Start worker (run on each worker laptop)
cd mini-cloud && uvicorn worker.main:app --host 0.0.0.0 --port 8001 --reload

# Check node registry
curl http://192.168.1.10:8000/nodes

# Submit a task
curl -X POST http://192.168.1.10:8000/tasks \
  -H 'Content-Type: application/json' \
  -d '{"image": "alpine", "command": "echo hello world"}'

# Check task result
curl http://192.168.1.10:8000/tasks/{task_id}

# Check worker health
curl http://192.168.1.11:8001/health

# Redis CLI (check node registry)
redis-cli HGETALL nodes

# Run all tests
cd mini-cloud && python -m pytest tests/ -v

# Prometheus query (in browser)
# http://192.168.1.10:9090
# Query: minicloud_healthy_nodes
# Query: minicloud_worker_cpu_percent
```

---

## How to Use This File With an AI Assistant

Paste the entire contents of this file at the start of any new conversation, then describe your specific question or task. Example:

> "Here is my project context: [paste file]. I am currently on Week 2 Day 10 building the Docker executor on the worker node. I need help with..."

This gives the assistant full context without you having to re-explain the architecture, tech choices, or constraints each time.
