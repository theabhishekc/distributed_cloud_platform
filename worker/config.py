# worker/config.py

import os

MASTER_IP = os.getenv("MASTER_IP", "192.168.1.10")
MASTER_PORT = int(os.getenv("MASTER_PORT", "8000"))
MASTER_BASE_URL = os.getenv("MASTER_BASE_URL", f"http://{MASTER_IP}:{MASTER_PORT}")

WORKER_PORT = int(os.getenv("WORKER_PORT", "8001"))

REGISTRATION_RETRY_INTERVAL_SECONDS = int(os.getenv("REGISTRATION_RETRY_INTERVAL_SECONDS", "10"))

# ── Week 2 additions ──────────────────────────────────────────────────────────

# Unique node identifier — set by the OS to this machine's hostname by default,
# overridable via env. The full UUID is generated at runtime by build_node_info()
# and stored in NODE_INFO; this is only used for logging before NODE_INFO exists.
WORKER_NODE_ID: str = os.getenv("WORKER_NODE_ID", "worker-unknown")

# Maximum Docker containers running simultaneously on this worker.
# Adjust per-laptop based on available RAM/CPU.
MAX_CONCURRENT_TASKS: int = int(os.getenv("MAX_CONCURRENT_TASKS", "3"))

# Seconds to wait for the master to accept a task result callback.
MASTER_CALLBACK_TIMEOUT: int = int(os.getenv("MASTER_CALLBACK_TIMEOUT", "30"))

