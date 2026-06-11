# worker/main.py
import socket
from fastapi import FastAPI

app = FastAPI(title="MiniCloud Worker Node")


def get_local_ip() -> str:
    """Get the machine's LAN IP (not 127.0.0.1)."""
    try:
        # Connect to an external address to discover which interface is used
        # This does NOT actually send any data
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "node": "worker",
        "ip": get_local_ip()
    }
