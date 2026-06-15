# Week 1 Setup & Deployment Guide (4 Laptops)

This guide provides step-by-step instructions for deploying and running the **Mini Distributed Cloud Platform (Week 1)** across 4 physical laptops connected to a local area network (LAN).

---

## 1. Network & Architecture Topology

```
                  [ Local Area Network (LAN) ]
                               ↓
  ┌───────────────────────┬────┴──────────────────┬──────────────────────┐
  │                       │                       │                      │
  ▼                       ▼                       ▼                      ▼
[ Master Node ]        [ Worker 1 ]            [ Worker 2 ]           [ Worker 3 ]
IP: 192.168.1.10       IP: 192.168.1.11        IP: 192.168.1.12       IP: 192.168.1.13
Port: 8000             Port: 8001              Port: 8001             Port: 8001
- FastAPI Master       - FastAPI Worker        - FastAPI Worker       - FastAPI Worker
- Redis DB             - Heartbeat Sender      - Heartbeat Sender     - Heartbeat Sender
- Health Monitor       - Resource Collector    - Resource Collector   - Resource Collector
```

### IP Allocations
* **Master Node:** `192.168.1.10`
* **Worker Node 1:** `192.168.1.11`
* **Worker Node 2:** `192.168.1.12`
* **Worker Node 3:** `192.168.1.13`

> [!NOTE]
> If your router uses a different subnet (e.g., `192.168.0.x` or `10.0.0.x`), update the IP addresses accordingly. The crucial part is that the Master and Worker config files reflect these real LAN IPs.

---

## 2. Prerequisites & Installation

Run the following setup steps on **all 4 laptops**:

### A. Python & System Libraries
Ensure Python 3.10+ and `pip` are installed:
```bash
sudo apt update
sudo apt install -y python3 python3-pip python3-venv git
```

### B. Redis (Required on Master Node only)
Install and start Redis on the Master laptop:
```bash
sudo apt install -y redis-server
```
Modify Redis config (`/etc/redis/redis.conf`) to bind to all interfaces so workers can backup state (or keep it local if Master FastAPI is the only one communicating with Redis):
```text
# Check/set this line in /etc/redis/redis.conf
bind 127.0.0.1 ::1
```
Restart Redis:
```bash
sudo systemctl restart redis-server
```

---

## 3. Code Synchronization & Configuration

### A. Clone the Repository
On each laptop, clone the repository to the home directory:
```bash
git clone https://github.com/theabhishekc/distributed_cloud_platform.git ~/distributed_cloud_platform
cd ~/distributed_cloud_platform
```

### B. Python Virtual Environment & Dependencies
Set up the virtual environment and install requirements:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### C. Configure Worker Node Configs
On each worker laptop, configure `worker/config.py` (or environment variables) to point to the Master node's LAN IP:
```python
# worker/config.py
MASTER_BASE_URL = "http://192.168.1.10:8000"
WORKER_PORT = 8001
REGISTRATION_RETRY_INTERVAL_SECONDS = 10
```

---

## 4. Execution Step-by-Step

Follow this exact order of startup to ensure successful registration.

### Step 1: Start the Master Node (Laptop 1)
On the Master laptop (`192.168.1.10`):
1. Activate environment:
   ```bash
   cd ~/distributed_cloud_platform
   source .venv/bin/activate
   ```
2. Launch the Master service:
   ```bash
   uvicorn master.main:app --host 0.0.0.0 --port 8000
   ```
   *Expected Console Output:*
   ```text
   INFO:     Started server process [12345]
   INFO:     Waiting for application startup.
   INFO:     Application startup complete.
   INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
   ```

### Step 2: Start the Worker Nodes (Laptops 2, 3, 4)
On each Worker laptop (`192.168.1.11`, `.12`, `.13`):
1. Activate environment:
   ```bash
   cd ~/distributed_cloud_platform
   source .venv/bin/activate
   ```
2. Launch the Worker service:
   ```bash
   uvicorn worker.main:app --host 0.0.0.0 --port 8001
   ```
   *Expected Console Output:*
   ```text
   INFO:     Starting up — node_id=f47ac10b-58cc-4372-a567-0e02b2c3d479 ip=192.168.1.11
   INFO:     Starting registration for node f47ac10b-58cc-4372-a567-0e02b2c3d479 at 192.168.1.11
   INFO:     Starting heartbeat sender to master at http://192.168.1.10:8000/heartbeat (interval: 5s)...
   INFO:     Registered with master as node-f47ac10b-58cc-4372-a567-0e02b2c3d479
   INFO:     Heartbeat sent successfully. Metrics -> CPU: 12.4%, RAM: 45.2%
   ```

---

## 5. Verification & Diagnostics

Once all processes are running, verify the status of the cluster:

### A. Query Active Node Registry
From the Master node or any device on the network, query the active node list:
```bash
curl http://192.168.1.10:8000/nodes
```
*Expected JSON Response:*
```json
[
  {
    "node_id": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
    "ip": "192.168.1.11",
    "port": 8001,
    "cpu_percent": 12.4,
    "ram_percent": 45.2,
    "active_tasks": 0,
    "status": "healthy",
    "last_heartbeat": "2026-06-15T14:58:30Z"
  },
  ...
]
```

### B. Verify Redis Persistence
Check that the registered nodes are saved in the Redis database:
```bash
redis-cli HGETALL nodes
```

### C. Test Dead Node Detection
1. **Stop Worker 1:** Terminate the uvicorn process on Laptop 2 (`Ctrl+C`).
2. **Monitor Status:** Wait **15 seconds** (equivalent to 3 missed heartbeats).
3. **Verify Dead State:** Run `curl http://192.168.1.10:8000/nodes` and check that Worker 1's status has transitioned to `"dead"`.
4. **Restart Worker 1:** Start the worker service again on Laptop 2.
5. **Verify Recovery:** Verify that status returns to `"healthy"`.

---

## 6. Troubleshooting

### Firewall Blocking
If the workers cannot connect to the master, ensure your firewall permits traffic on ports `8000` and `8001`:
```bash
sudo ufw allow 8000/tcp
sudo ufw allow 8001/tcp
```

### IP Address Binding Error
If you see an address bind error during uvicorn startup, verify that no other service is currently using port `8000`/`8001` or run:
```bash
lsof -i :8000
kill -9 <PID>
```
