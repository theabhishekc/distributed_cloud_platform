# master/main.py
from fastapi import FastAPI
from master.api.registry_routes import router


app = FastAPI(
    title="Mini Distributed Cloud Platform - Master Node"
)

app.include_router(router)

@app.get("/health")
def health():
    return {
        "status": "ok",
        "node": "master"
    }
