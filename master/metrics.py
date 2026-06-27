# master/metrics.py
from prometheus_client import Gauge, Counter, Histogram, make_asgi_app
from typing import Dict
from shared.models import NodeInfo

# ── Master Metrics ────────────────────────────────────────────────────────────

minicloud_healthy_nodes = Gauge(
    "minicloud_healthy_nodes", "Current count of healthy worker nodes"
)

minicloud_worker_cpu_percent = Gauge(
    "minicloud_worker_cpu_percent", "CPU utilization percentage per worker", ["node_id"]
)

minicloud_worker_ram_percent = Gauge(
    "minicloud_worker_ram_percent", "RAM utilization percentage per worker", ["node_id"]
)

minicloud_worker_active_tasks = Gauge(
    "minicloud_worker_active_tasks", "Active tasks currently running per worker", ["node_id"]
)

minicloud_tasks_total = Counter(
    "minicloud_tasks_total", "Total tasks processed by status", ["status"]
)

minicloud_tasks_duration_seconds = Histogram(
    "minicloud_tasks_duration_seconds", "Task execution duration in seconds"
)

minicloud_files_total = Gauge(
    "minicloud_files_total", "Total number of files stored in the platform"
)

minicloud_storage_bytes_total = Gauge(
    "minicloud_storage_bytes_total", "Total bytes stored across all files"
)

minicloud_lambda_invocations_total = Counter(
    "minicloud_lambda_invocations_total", "Total Lambda function invocations", ["function_id"]
)

minicloud_lambda_duration_ms = Histogram(
    "minicloud_lambda_duration_ms", "Lambda function execution duration in milliseconds", ["function_id"]
)


def update_node_metrics(nodes: Dict[str, NodeInfo]) -> None:
    """
    Called by the health monitor after every heartbeat cycle to update node metrics.
    """
    healthy_count = 0
    for node_id, node in nodes.items():
        if node.status == "healthy":
            healthy_count += 1
        
        # Update gauges per worker node
        minicloud_worker_cpu_percent.labels(node_id=node_id).set(node.cpu_percent)
        minicloud_worker_ram_percent.labels(node_id=node_id).set(node.ram_percent)
        minicloud_worker_active_tasks.labels(node_id=node_id).set(node.active_tasks)

    minicloud_healthy_nodes.set(healthy_count)


# ASGI app to be mounted at /metrics in master FastAPI app
metrics_app = make_asgi_app()
