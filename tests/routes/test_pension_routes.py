from datetime import date
from pathlib import Path

import pytest
from fastapi import HTTPException
from starlette.applications import Starlette
from starlette.requests import Request

from backend.routes import pension


@pytest.fixture
def request_with_root(tmp_path: Path) -> Request:
    app = Starlette()
    app.state.accounts_root = tmp_path

    async def receive() -> dict:
        return {"type": "http.request"}

    scope = {
        "type": "http",
        "app": app,
        "method": "GET",
        "path": "/pension/forecast",
        "headers": [],
    }
    return Request(scope, receive)


def test_pension_forecast_success(monkeypatch: pytest.MonkeyPatch, request_with_root: Request) -> None:
    def fake_resolve_accounts_root(request: Request) -> Path:
        return Path(request.app.state.accounts_root)

    def fake_load_person_meta(owner: str, accounts_root: Path) -> dict:
        assert owner == "alex"
        assert accounts_root == Path(request_with_root.app.state.accounts_root)
        return {"dob": date(1985, 7, 1)}

    def fake_age_from_dob(dob):
        assert dob == date(1985, 7, 1)
        return 40

    def fake_state_pension_age_uk(dob):
        assert dob == date(1985, 7, 1)
        return 68

    captured_args = {}

    def fake_build_owner_portfolio(owner: str, accounts_root=None, *args, **kwargs):
        captured_args["args"] = args
        captured_args["kwargs"] = kwargs
        captured_args["accounts_root"] = accounts_root
        return {
            "accounts": [
                {"account_type": "SIPP", "value_estimate_gbp": 10_000},
                {"account_type": "isa", "value_estimate_gbp": 5_000},
                {"account_type": "kz:sipp", "value_estimate_gbp": 20_000},
            ]
        }

    def fake_forecast_pension(**kwargs):
        assert kwargs["initial_pot"] == 30_000
        return {"projection": [kwargs]}

    monkeypatch.setattr(pension, "resolve_accounts_root", fake_resolve_accounts_root)
    monkeypatch.setattr(pension, "load_person_meta", fake_load_person_meta)
    monkeypatch.setattr(pension, "_age_from_dob", fake_age_from_dob)
    monkeypatch.setattr(pension, "state_pension_age_uk", fake_state_pension_age_uk)
    monkeypatch.setattr(pension, "build_owner_portfolio", fake_build_owner_portfolio)
    monkeypatch.setattr(pension, "forecast_pension", fake_forecast_pension)

    result = pension.pension_forecast(
        request_with_root,
        owner="alex",
        death_age=90,
        state_pension_annual=8_000,
        db_income_annual=4_000,
        db_normal_retirement_age=60,
        contribution_monthly=500,
        investment_growth_pct=4.5,
        desired_income_annual=35_000,
    )

    assert result["current_age"] == 40
    assert result["retirement_age"] == 68
    assert result["pension_pot_gbp"] == 30_000
    assert "projection" in result
    assert captured_args["accounts_root"] == Path(request_with_root.app.state.accounts_root)


def test_pension_forecast_invalid_death_age(monkeypatch: pytest.MonkeyPatch, request_with_root: Request) -> None:
    monkeypatch.setattr(pension, "resolve_accounts_root", lambda request: Path("."))
    monkeypatch.setattr(
        pension,
        "load_person_meta",
        lambda owner, accounts_root: {"dob": date(1990, 1, 1)},
    )
    monkeypatch.setattr(pension, "_age_from_dob", lambda dob: 30)
    monkeypatch.setattr(pension, "state_pension_age_uk", lambda dob: 67)

    with pytest.raises(HTTPException) as exc:
        pension.pension_forecast(
            request_with_root,
            owner="alex",
            death_age=60,
            state_pension_annual=None,
            db_income_annual=None,
            db_normal_retirement_age=None,
            contribution_annual=None,
            investment_growth_pct=5.0,
            desired_income_annual=None,
        )

    assert exc.value.status_code == 400
    assert "death_age" in exc.value.detail


def test_pension_forecast_missing_dob(monkeypatch: pytest.MonkeyPatch, request_with_root: Request) -> None:
    monkeypatch.setattr(pension, "resolve_accounts_root", lambda request: Path("."))
    monkeypatch.setattr(pension, "load_person_meta", lambda owner, accounts_root: {})

    with pytest.raises(HTTPException) as exc:
        pension.pension_forecast(
            request_with_root,
            owner="alex",
            death_age=90,
            state_pension_annual=None,
            db_income_annual=None,
            db_normal_retirement_age=None,
            contribution_annual=None,
            investment_growth_pct=5.0,
            desired_income_annual=None,
        )

    assert exc.value.status_code == 400
    assert "dob" in exc.value.detail
