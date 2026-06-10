# master/main.py

from fastapi import FastAPI

app = FastAPI(
    title="Mini Distributed Cloud Platform - Master Node"
)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "node": "master"
    }
