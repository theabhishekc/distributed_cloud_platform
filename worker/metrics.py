# worker/metrics.py
from prometheus_client import Gauge, Counter, Histogram, make_asgi_app

# ── Worker-local Metrics ──────────────────────────────────────────────────────

minicloud_worker_local_cpu_percent = Gauge(
    "minicloud_worker_local_cpu_percent", "Worker local CPU utilization percentage"
)

minicloud_worker_local_ram_percent = Gauge(
    "minicloud_worker_local_ram_percent", "Worker local RAM utilization percentage"
)

minicloud_worker_local_active_tasks = Gauge(
    "minicloud_worker_local_active_tasks", "Worker local active tasks currently running"
)

minicloud_worker_local_tasks_total = Counter(
    "minicloud_worker_local_tasks_total", "Worker local total tasks processed by status", ["status"]
)

minicloud_worker_local_tasks_duration_seconds = Histogram(
    "minicloud_worker_local_tasks_duration_seconds", "Worker local task execution duration in seconds"
)

minicloud_worker_local_chunks_total = Gauge(
    "minicloud_worker_local_chunks_total", "Worker local total number of chunks stored"
)

minicloud_worker_local_storage_bytes = Gauge(
    "minicloud_worker_local_storage_bytes", "Worker local total bytes stored across chunks"
)

minicloud_worker_local_lambda_total = Counter(
    "minicloud_worker_local_lambda_total", "Worker local total Lambda invocations", ["function_id"]
)

minicloud_worker_local_lambda_duration_ms = Histogram(
    "minicloud_worker_local_lambda_duration_ms", "Worker local Lambda execution duration in ms", ["function_id"]
)

# ASGI app to be mounted at /metrics in worker FastAPI app
worker_metrics_app = make_asgi_app()
