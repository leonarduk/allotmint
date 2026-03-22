from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from backend.common.account_models import PersonMetadata
from backend.routes import pension


@pytest.fixture
def request_with_root(tmp_path: Path) -> Request:
    app = MagicMock()
    app.state.accounts_root = str(tmp_path)
    scope = {"type": "http", "app": app}
    return Request(scope=scope)


def test_pension_forecast_success(monkeypatch: pytest.MonkeyPatch, request_with_root: Request) -> None:
    def fake_resolve_accounts_root(request: Request) -> Path:
        return Path(request.app.state.accounts_root)

    def fake_load_person_metadata(owner: str, accounts_root: Path) -> PersonMetadata:
        assert owner == "alex"
        assert accounts_root == Path(request_with_root.app.state.accounts_root)
        return PersonMetadata(dob="1985-07-01")

    def fake_age_from_dob(dob):
        assert dob == "1985-07-01"
        return 40

    def fake_state_pension_age_uk(dob):
        assert dob == "1985-07-01"
        return 68

    captured_args = {}

    def fake_build_owner_portfolio(owner, accounts_root=None, root=None):
        captured_args["owner"] = owner
        captured_args["accounts_root"] = accounts_root
        return {
            "accounts": [
                {"account_type": "sipp", "value_estimate_gbp": 50000.0},
                {"account_type": "isa", "value_estimate_gbp": 10000.0},
            ]
        }

    def fake_forecast_pension(**kwargs):
        return {"projection": [kwargs]}

    monkeypatch.setattr(pension, "resolve_accounts_root", fake_resolve_accounts_root)
    monkeypatch.setattr(pension, "load_person_metadata", fake_load_person_metadata)
    monkeypatch.setattr(pension, "_age_from_dob", fake_age_from_dob)
    monkeypatch.setattr(pension, "state_pension_age_uk", fake_state_pension_age_uk)
    monkeypatch.setattr(pension, "build_owner_portfolio", fake_build_owner_portfolio)
    monkeypatch.setattr(pension, "forecast_pension", fake_forecast_pension)

    result = pension.pension_forecast(
        request=request_with_root,
        owner="alex",
        death_age=90,
        state_pension_annual=9000.0,
        db_income_annual=None,
        db_normal_retirement_age=None,
        contribution_annual=None,
        contribution_monthly=None,
        investment_growth_pct=5.0,
        desired_income_annual=None,
    )

    assert result["pension_pot_gbp"] == 50000.0
    assert result["current_age"] == 40
    assert result["retirement_age"] == 68
    assert result["dob"] == "1985-07-01"


def test_pension_forecast_invalid_death_age(monkeypatch: pytest.MonkeyPatch, request_with_root: Request) -> None:
    monkeypatch.setattr(pension, "resolve_accounts_root", lambda request: Path("."))
    monkeypatch.setattr(
        pension,
        "load_person_metadata",
        lambda owner, accounts_root: PersonMetadata(dob="1990-01-01"),
    )
    monkeypatch.setattr(pension, "_age_from_dob", lambda dob: 30)
    monkeypatch.setattr(pension, "state_pension_age_uk", lambda dob: 67)
    monkeypatch.setattr(
        pension,
        "build_owner_portfolio",
        lambda owner, accounts_root=None, root=None: {"accounts": []},
    )

    with pytest.raises(HTTPException) as exc:
        pension.pension_forecast(
            request=request_with_root,
            owner="alex",
            death_age=60,
            state_pension_annual=None,
            db_income_annual=None,
            db_normal_retirement_age=None,
            contribution_annual=None,
            contribution_monthly=None,
            investment_growth_pct=5.0,
            desired_income_annual=None,
        )

    assert exc.value.status_code == 400
    assert "death_age" in exc.value.detail


def test_pension_forecast_missing_dob(monkeypatch: pytest.MonkeyPatch, request_with_root: Request) -> None:
    monkeypatch.setattr(pension, "resolve_accounts_root", lambda request: Path("."))
    monkeypatch.setattr(
        pension,
        "load_person_metadata",
        lambda owner, accounts_root: PersonMetadata(dob=None),
    )
    monkeypatch.setattr(pension, "_age_from_dob", lambda dob: None)

    with pytest.raises(HTTPException) as exc:
        pension.pension_forecast(
            request=request_with_root,
            owner="alex",
            death_age=90,
            state_pension_annual=None,
            db_income_annual=None,
            db_normal_retirement_age=None,
            contribution_annual=None,
            contribution_monthly=None,
            investment_growth_pct=5.0,
            desired_income_annual=None,
        )

    assert exc.value.status_code == 400
    assert "dob" in exc.value.detail
