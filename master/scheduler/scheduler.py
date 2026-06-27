# master/scheduler/scheduler.py
#
# Resource-aware scheduler.
#
# Algorithm (from PROJECT_CONTEXT.md — do not change):
#   score(node) = (1 - cpu_percent/100) * 0.5
#               + (1 - ram_percent/100) * 0.3
#               + (1 - active_tasks/MAX_TASKS) * 0.2
#
# Higher score = better candidate.  Ties broken by arbitrary dict order.
# Raises NoHealthyNodeError if all registered nodes are dead or if the
# registry is empty.

from shared.logger import get_logger
from shared.models import NodeInfo, SchedulerDecision, TaskRequest
from master.registry.node_registry import get_healthy_nodes

logger = get_logger("scheduler", node_id="master")

# Maximum concurrent tasks per node used in the active_tasks score component.
# Matches worker/executor/task_queue.py MAX_CONCURRENT (3 by default) * some
# headroom so we don't over-penalise a moderately busy node.
MAX_TASKS: int = 10


# ── Custom exception ──────────────────────────────────────────────────────────

class NoHealthyNodeError(Exception):
    """
    Raised when select_worker cannot find any healthy node to assign a task.
    The master route layer converts this to HTTP 503 Service Unavailable.
    """
    pass


# ── Scoring ───────────────────────────────────────────────────────────────────

def _score(node: NodeInfo) -> float:
    """
    Compute the scheduling score for a single node.

    All three components are in [0, 1].  Weights sum to 1.0.
    A node under zero load would score 1.0; a saturated node scores 0.0.
    """
    cpu_score   = (1 - node.cpu_percent  / 100) * 0.5
    ram_score   = (1 - node.ram_percent  / 100) * 0.3
    tasks_score = (1 - node.active_tasks / MAX_TASKS) * 0.2
    return round(cpu_score + ram_score + tasks_score, 4)


# ── Public API ────────────────────────────────────────────────────────────────

def select_worker(task: TaskRequest) -> SchedulerDecision:
    """
    Choose the best healthy worker node for the given task.

    Steps:
      1. Get all healthy nodes from the in-memory registry.
      2. Raise NoHealthyNodeError if none available.
      3. Score each node and pick the maximum.
      4. Build a SchedulerDecision with the reason string.
      5. Log and return the decision.

    This function is synchronous (pure computation on in-memory data).
    It is safe to call from async route handlers without run_in_executor.
    """
    healthy_nodes = get_healthy_nodes()

    if not healthy_nodes:
        logger.warning(
            "No healthy nodes available to schedule task.",
            extra={"event": "scheduler_no_nodes", "task_id": task.task_id},
        )
        raise NoHealthyNodeError(
            "No healthy worker nodes are currently available. "
            "Submit again once a worker has registered and sent a heartbeat."
        )

    # Score all nodes and pick the best
    scored = [(node, _score(node)) for node in healthy_nodes]
    best_node, best_score = max(scored, key=lambda x: x[1])

    reason = (
        f"cpu:{best_node.cpu_percent:.1f}%,"
        f"ram:{best_node.ram_percent:.1f}%,"
        f"tasks:{best_node.active_tasks}"
    )

    decision = SchedulerDecision(
        task_id          = task.task_id,
        chosen_worker_id = best_node.node_id,
        reason           = reason,
        score            = best_score,
    )

    logger.info(
        f"Task [{task.task_id}] → worker [{best_node.node_id[-8:]}] "
        f"score={best_score:.4f} ({reason})",
        extra={
            "event":       "scheduler_decision",
            "task_id":     task.task_id,
            "worker_id":   best_node.node_id,
            "worker_ip":   best_node.ip,
            "score":       best_score,
            "reason":      reason,
            "candidates":  len(healthy_nodes),
        },
    )
    return decision
