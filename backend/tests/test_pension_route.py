from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from pathlib import Path

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

    captured: dict[str, object] = {}

    def _fake_portfolio(owner: str, accounts_root: object) -> dict[str, object]:
        captured["owner"] = owner
        captured["accounts_root"] = accounts_root
        return {"accounts": []}

    monkeypatch.setattr("backend.routes.pension.build_owner_portfolio", _fake_portfolio)

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
    assert captured["owner"] == "demo-owner"

    accounts_root = captured.get("accounts_root")
    if isinstance(accounts_root, Path):
        accounts_root_path = accounts_root
    elif isinstance(accounts_root, str):
        accounts_root_path = Path(accounts_root)
    else:
        accounts_root_path = Path("data/accounts").resolve()

    # The fallback path should be a readable local directory containing demo data.
    assert accounts_root_path.exists()
    assert any(p.name == "demo-owner" for p in accounts_root_path.iterdir())


def test_pension_forecast_counts_prefixed_sipp_accounts(monkeypatch: MonkeyPatch) -> None:
    """Vendor-prefixed SIPP identifiers should contribute to the pension pot."""

    reload_config()
    config.offline_mode = True

    monkeypatch.setattr(
        "backend.routes.pension.load_person_meta",
        lambda owner, root: {"dob": "1980-01-01"},
    )
    monkeypatch.setattr(
        "backend.routes.pension.build_owner_portfolio",
        lambda owner, root: {
            "accounts": [
                {"account_type": "kz:sipp", "value_estimate_gbp": 1234.56},
                {"account_type": "isa", "value_estimate_gbp": 999.0},
            ]
        },
    )

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
    payload = response.json()
    assert payload["pension_pot_gbp"] == 1234.56
