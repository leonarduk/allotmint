from pathlib import Path
from unittest.mock import patch

import pytest
from pytest import MonkeyPatch

from backend.common.account_models import PersonMetadata
from backend.config import config
from backend.routes import pension


def test_pension_forecast_counts_prefixed_sipp_accounts(monkeypatch: MonkeyPatch):
    config.offline_mode = True

    monkeypatch.setattr(
        "backend.routes.pension.load_person_metadata",
        lambda owner, root: PersonMetadata(dob="1980-01-01"),
    )
    monkeypatch.setattr(
        "backend.routes.pension.build_owner_portfolio",
        lambda owner, accounts_root=None, root=None: {
            "accounts": [
                {"account_type": "kz:sipp", "value_estimate_gbp": 10000.0},
                {"account_type": "isa", "value_estimate_gbp": 5000.0},
            ]
        },
    )
    monkeypatch.setattr("backend.routes.pension._age_from_dob", lambda dob: 40)
    monkeypatch.setattr("backend.routes.pension.state_pension_age_uk", lambda dob: 67)
    monkeypatch.setattr(
        "backend.routes.pension.forecast_pension",
        lambda **kwargs: {"projection": []},
    )
    monkeypatch.setattr("backend.routes.pension.resolve_accounts_root", lambda req: Path("."))

    from unittest.mock import MagicMock
    from starlette.requests import Request

    app = MagicMock()
    app.state.accounts_root = "."
    scope = {"type": "http", "app": app}
    request = Request(scope=scope)

    result = pension.pension_forecast(
        request=request,
        owner="alice",
        death_age=90,
        state_pension_annual=None,
        db_income_annual=None,
        db_normal_retirement_age=None,
        contribution_annual=None,
        contribution_monthly=None,
        investment_growth_pct=5.0,
        desired_income_annual=None,
    )

    assert result["pension_pot_gbp"] == 10000.0
