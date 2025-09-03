from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.routes.agent import router


def test_agent_stats_route(monkeypatch):
    sample_payload = {"win_rate": 0.5, "average_profit": 1.23}
    monkeypatch.setattr(
        "backend.routes.agent.load_and_compute_metrics",
        lambda: sample_payload,
    )
    app = FastAPI()
    app.include_router(router)

    with TestClient(app) as client:
        response = client.get("/agent/stats")

    assert response.status_code == 200
    assert response.json() == sample_payload
