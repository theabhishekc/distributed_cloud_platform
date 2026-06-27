# Distributed Cloud Platform (MiniCloud) — Complete Architecture & Implementation Context

This document serves as the comprehensive architectural and implementation context for the **Distributed Cloud Platform (MiniCloud)**. It details the system design, directory structure, data models, communication protocols, and execution flows across all four phases of development.

---

## 🏗️ System Overview

MiniCloud is a lightweight, fault-tolerant, fully distributed cloud platform designed to run across a cluster of bare-metal machines or laptops (e.g., a 4-laptop LAN cluster). It mimics core AWS/GCP capabilities including:
1. **Cluster Management & Health (EC2/Control Plane)**: Worker registration, real-time heartbeats, and automated dead-node detection.
2. **Compute Engine & Scheduling (ECS/Batch)**: Asynchronous containerized task scheduling, resource scoring, Docker execution, and task reaping.
3. **Distributed Object Storage (S3)**: Chunked file upload/download, MD5 validation, 2x replication, and automatic fallback/re-replication.
4. **Serverless Engine (AWS Lambda)**: Dynamic function storage, runtime isolation, and distributed execution routing.
5. **Observability & Hardening (CloudWatch/Prometheus)**: Centralized asynchronous log aggregation, Prometheus metrics instrumentation, and Grafana monitoring.

---

## 📂 Directory Structure & Module Breakdown

```
distributed_cloud_platform/
├── master/                         # Master (Control Plane) Service
│   ├── api/                        # FastAPI REST Endpoints
│   │   ├── heartbeat_routes.py     # Worker heartbeat reception & metric tracking
│   │   ├── registry_routes.py      # Worker registration & cluster status API
│   │   ├── task_routes.py          # Task submission & status querying API
│   │   ├── storage_routes.py       # File upload/download & metadata API
│   │   ├── function_routes.py      # Lambda function creation, listing, & invocation API
│   │   ├── log_routes.py           # Ingestion (POST) and querying (GET) of cluster logs
│   │   └── metrics_routes.py       # Prometheus /metrics scrape endpoint
│   ├── db/                         # SQLite/PostgreSQL Async Repositories
│   │   ├── database.py             # SQLAlchemy async engine & session management
│   │   ├── models.py               # Declarative ORM models (Task, File, Chunk, Function, LogDB)
│   │   ├── task_repository.py      # CRUD operations for container tasks
│   │   ├── storage_repository.py   # CRUD operations for file metadata and chunks
│   │   ├── function_repository.py  # CRUD operations for Lambda function definitions
│   │   └── log_repository.py       # Ingestion and query logic for aggregated logs
│   ├── registry/                   # In-Memory & Redis Node Registry
│   │   ├── node_registry.py        # In-memory dictionary + Redis persistence for worker states
│   │   └── health_monitor.py       # Background asyncio task for dead-node detection
│   ├── scheduler/                  # Compute & Job Scheduling
│   │   ├── async_scheduler.py      # Resource scoring & worker selection algorithm
│   │   └── task_reaper.py          # Background cleanup of orphaned/stuck tasks
│   ├── storage/                    # Storage Orchestration
│   │   ├── upload_orchestrator.py  # 1MB chunking, checksumming, and replica selection
│   │   └── replication_monitor.py  # Background checking & healing of under-replicated chunks
│   ├── functions/                  # Serverless Management
│   │   └── function_store.py       # Function lifecycle management & DB wrapping
│   ├── main.py                     # Master FastAPI app initialization & lifecycle events
│   └── metrics.py                  # Master Prometheus Gauges, Counters, and Histograms
│
├── worker/                         # Worker (Data Plane) Service
│   ├── api/                        # Worker Local Endpoints
│   │   ├── task_routes.py          # Task enqueuing & local status check API
│   │   ├── storage_routes.py       # Chunk storage (POST) and retrieval (GET) API
│   │   ├── function_routes.py      # Lambda invocation execution API
│   │   └── metrics_routes.py       # Local Prometheus /metrics scrape endpoint
│   ├── health/                     # Health & Registration Management
│   │   ├── registrar.py            # Startup worker registration with master node
│   │   └── heartbeat.py            # Periodic heartbeat emitter (every 5s) with system stats
│   ├── executor/                   # Compute Engine Execution
│   │   ├── docker_executor.py      # Asynchronous Docker container management & logging
│   │   └── task_queue.py           # Bounded task queue with asyncio.Semaphore concurrency limits
│   ├── storage/                    # Local Storage Engine
│   │   └── chunk_store.py          # File system storage for 1MB binary chunks
│   ├── functions/                  # Local Serverless Engine
│   │   └── lambda_runner.py        # Python dynamic execution & isolated runtime wrapper
│   ├── main.py                     # Worker FastAPI app initialization & lifecycle events
│   └── metrics.py                  # Worker local Prometheus metrics definitions
│
├── shared/                         # Shared Code across Master & Worker
│   ├── models.py                   # Shared Pydantic schemas for REST communication
│   ├── logger.py                   # Structured JSON logger with standard attributes
│   └── log_aggregator.py           # Asynchronous worker-side log buffering and batch flusher to master
│
├── infra/                          # Infrastructure & Monitoring
│   ├── docker-compose.yml          # Prometheus & Grafana stack
│   ├── prometheus.yml              # Scrape configuration for master and workers
│   └── grafana/                    # Provisioned Datasources & Dashboards
│       ├── provisioning/           # Auto-loading configs for Prometheus datasource & dashboards
│       └── dashboards/             # minicloud_dashboard.json (Rich visual graphs)
│
└── tests/                          # Full Pytest Test Suite
    ├── test_week1.py               # Master registry, heartbeat, dead detection, Redis tests
    ├── test_week1_worker.py        # Worker registrar & heartbeat emitter tests
    ├── test_heartbeat.py           # Heartbeat serialization tests
    ├── test_logger.py              # Structured logging formatting tests
    ├── test_week2_integration.py   # Scheduler scoring, semaphore queue, reaper tests
    ├── test_storage.py             # File chunking, upload orchestration, replication fallback tests
    ├── test_lambda.py              # Function storage, dynamic execution, timeout tests
    └── test_stress.py              # High concurrency stress tests (tasks, uploads, lambdas, logs)
```

---

## 🚀 Architectural Deep-Dive by Phase

### Phase 1: Control Plane, Heartbeats, & Registry (Week 1)
- **Registration (`worker/health/registrar.py`)**: On startup, workers send a `POST /registry/register` to the master with their `node_id`, `ip`, `port`, and hardware metrics.
- **Heartbeat Emitter (`worker/health/heartbeat.py`)**: Every 5 seconds, workers measure local CPU/RAM utilization using `psutil` and POST to `http://<master_ip>:8000/heartbeat`.
- **Node Registry (`master/registry/node_registry.py`)**: The master maintains an in-memory dictionary of all registered nodes (`nr.nodes`). It also persists state to Redis (`node:<node_id>`) as a JSON string to ensure master crash recovery.
- **Health Monitor (`master/registry/health_monitor.py`)**: A background asyncio loop runs on the master. If a worker hasn't sent a heartbeat in `15 seconds` (dead timeout), it is marked as `dead` in both memory and Redis, triggering metric updates.

### Phase 2: Compute Engine & Docker Execution (Week 2)
- **Task Submission (`master/api/task_routes.py`)**: Clients submit task specs (`image`, `command`, `ram_limit_mb`) to `POST /tasks`. The master persists the task in the database with status `SCHEDULED`.
- **Asynchronous Scheduler (`master/scheduler/async_scheduler.py`)**: The master queries healthy nodes from the registry and calculates a score for each:
  $$\text{Score} = w_1(100 - \text{CPU}) + w_2(100 - \text{RAM}) - w_3(\text{Active Tasks})$$
  The task is dispatched via HTTP POST to the highest-scoring worker's `/tasks` endpoint.
- **Worker Task Queue (`worker/executor/task_queue.py`)**: The worker places the incoming task into an internal `asyncio.Queue`. A worker loop processes tasks using an `asyncio.Semaphore` (e.g., max 5 concurrent tasks) to prevent resource exhaustion.
- **Docker Executor (`worker/executor/docker_executor.py`)**: The worker runs the task asynchronously using `asyncio.create_subprocess_exec` to invoke `docker run --memory <ram> <image> <command>`. It captures `stdout`/`stderr` and updates the master via `PATCH /tasks/<task_id>`.
- **Task Reaper (`master/scheduler/task_reaper.py`)**: A background loop on the master scans the database for tasks stuck in `RUNNING` or `SCHEDULED` on nodes that have been marked `dead`, updating their state to `FAILED` with an error message.

### Phase 3: Distributed Storage & Serverless Engine (Week 3)
- **Upload Orchestrator (`master/storage/upload_orchestrator.py`)**: When a file is uploaded (`POST /storage/upload`), the master splits it into `1MB` binary chunks. For each chunk, it calculates an MD5 checksum and selects 2 distinct healthy workers (`replication_factor=2`) using the scheduler. It uploads the chunk binary via `POST /storage/chunks` (multipart/form) to both workers.
- **Chunk Store (`worker/storage/chunk_store.py`)**: Workers persist chunk binaries directly to disk in a dedicated directory (`/tmp/minicloud_storage/chunks/<chunk_id>`).
- **Replication Monitor (`master/storage/replication_monitor.py`)**: A background task on the master periodically inspects chunk metadata in the database. If a chunk's storage node becomes `dead` or unreachable, the master reads the chunk from the surviving replica and POSTs it to a new healthy worker to restore 2x replication.
- **Serverless Functions (`master/api/function_routes.py`, `master/db/function_repository.py` & `worker/functions/lambda_runner.py`)**: Clients store Python code strings via `POST /functions`, which are persisted to the database via `function_repository.py`. When invoked (`POST /functions/<id>/invoke`), the master dispatches the code and event payload to a selected worker. The worker writes the code to a temporary file and executes it in an isolated Python subprocess with an enforced execution timeout.

### Phase 4: Observability, Logging, & Hardening (Week 4)
- **Prometheus Metrics (`master/metrics.py`, `worker/metrics.py`)**: Both master and worker expose `GET /metrics`. Master tracks healthy node counts, CPU/RAM per worker, task lifecycles (`SCHEDULED`, `COMPLETED`, `FAILED`), task durations (Histograms), storage file totals, and Lambda invocation counts/latencies.
- **Centralized Log Aggregator (`shared/log_aggregator.py`)**: A non-blocking worker-side batch flusher to master. It hooks into the structured JSON logger (`shared/logger.py`), buffers log events in memory, and flushes them to the master (`POST /logs`) in batches every 5 seconds or upon reaching 100 entries.
- **Log Repository (`master/db/log_repository.py`)**: Master persists aggregated logs into the `LogDB` table (SQLite/PostgreSQL) with structured indexes, allowing rich queries via `GET /logs?node_id=...&level=ERROR&limit=100`.
- **Stress Testing (`tests/test_stress.py`)**: High-concurrency stress test suite utilizing `respx` and `httpx.AsyncClient` against a shared in-memory SQLite engine to validate concurrent task scheduling (50 tasks), file uploads (10 uploads), Lambda invocations (20 invocations), and thread-safe DB transaction handling.

---

## 💻 API Contracts & Endpoints Summary

### Master Endpoints (`http://<master_ip>:8000`)
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/registry/register` | Register a new worker node |
| `POST` | `/heartbeat` | Receive periodic worker health metrics |
| `GET` | `/registry/nodes` | List all registered nodes and their statuses |
| `POST` | `/tasks` | Submit a new containerized compute task |
| `GET` | `/tasks/{task_id}` | Check the execution status and logs of a task |
| `POST` | `/storage/upload` | Upload a file for chunking and 2x replication |
| `GET` | `/storage/download/{file_id}` | Download and reassemble a file from worker chunks |
| `POST` | `/functions` | Store a new Lambda function definition |
| `POST` | `/functions/{id}/invoke` | Invoke a stored Lambda function on a worker |
| `POST` | `/logs` | Ingest a batch of log entries from a worker |
| `GET` | `/logs` | Query aggregated cluster logs with filtering |
| `GET` | `/metrics` | Prometheus metrics scraping endpoint |

### Worker Endpoints (`http://<worker_ip>:8001`)
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/tasks` | Enqueue a task for local Docker execution |
| `POST` | `/storage/chunks` | Store a 1MB binary chunk to disk |
| `GET` | `/storage/chunks/{chunk_id}` | Retrieve a stored binary chunk |
| `POST` | `/functions/invoke` | Execute a Lambda function in an isolated subprocess |
| `GET` | `/metrics` | Local Prometheus metrics scraping endpoint |

---

## 🛠️ Execution & Development Commands
- **Start Master**: `uvicorn master.main:app --port 8000 --reload`
- **Start Worker**: `uvicorn worker.main:app --port 8001 --reload`
- **Launch Monitoring Stack**: `docker-compose -f infra/docker-compose.yml up -d`
- **Run Full Test Suite**: `pytest`
