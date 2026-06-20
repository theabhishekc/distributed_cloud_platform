# worker/config.py

import os

MASTER_IP = os.getenv("MASTER_IP", "192.168.1.10")
MASTER_PORT = int(os.getenv("MASTER_PORT", "8000"))
MASTER_BASE_URL = os.getenv("MASTER_BASE_URL", f"http://{MASTER_IP}:{MASTER_PORT}")

WORKER_PORT = int(os.getenv("WORKER_PORT", "8001"))

REGISTRATION_RETRY_INTERVAL_SECONDS = int(os.getenv("REGISTRATION_RETRY_INTERVAL_SECONDS", "10"))
