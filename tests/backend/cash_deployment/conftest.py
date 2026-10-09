"""Fixtures for the cash deployment tests (#10480)."""

from __future__ import annotations

from datetime import date

import pytest

from backend.common.investment_plan import InvestmentPlan
from tests.backend.cash_deployment.fixtures import synthetic_plan, synthetic_portfolio


@pytest.fixture
def portfolio() -> dict:
    return synthetic_portfolio()


@pytest.fixture
def plan() -> InvestmentPlan:
    return synthetic_plan()


@pytest.fixture
def start() -> date:
    return date(2026, 1, 15)
