from fastapi.testclient import TestClient

from backend.app import create_app
from backend.config import reload_config


def test_pension_forecast_demo_owner_returns_ok() -> None:
    """The pension forecast endpoint should succeed with default settings."""

    reload_config()
    app = create_app()

    with TestClient(app) as client:
        response = client.get(
            "/pension/forecast",
            params={
                "owner": "demo",
                "death_age": 90,
            },
        )

    assert response.status_code == 200
