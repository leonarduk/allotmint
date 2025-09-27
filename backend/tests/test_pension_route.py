from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from backend.app import create_app
from backend.config import config, reload_config


def test_pension_forecast_demo_owner_returns_ok() -> None:
    """The pension forecast endpoint should succeed for the bundled owner."""

    reload_config()
    config.offline_mode = True
    app = create_app()

    with TestClient(app) as client:
        response = client.get(
            "/pension/forecast",
            params={
                "owner": "demo-owner",
                "death_age": 90,
            },
        )

    assert response.status_code == 200


def test_pension_forecast_demo_owner_returns_ok_in_aws(monkeypatch: MonkeyPatch) -> None:
    """AWS environments without DATA_BUCKET should fall back to local data."""

    monkeypatch.setenv("APP_ENV", "aws")
    monkeypatch.delenv("DATA_BUCKET", raising=False)

    reload_config()
    config.offline_mode = True
    app = create_app()

    with TestClient(app) as client:
        response = client.get(
            "/pension/forecast",
            params={
                "owner": "demo-owner",
                "death_age": 90,
            },
        )

    assert response.status_code == 200
