"""Shared fixtures for the retirement readiness tests: a synthetic 30-year returns CSV (1990-2019).

Every figure in the fixture is made up. CPI is 2% every year and UK cash
returns 4.04% nominal, so cash is exactly +2% real; 10-year gilts return 2%
nominal (0% real). ``us_small_value_gbp`` is blank before 1995 and
``gold_gbp`` blank before 1992.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.retirement.long_history import LongHistory, load_long_history

FIXTURE = Path(__file__).resolve().parents[2] / "data" / "retirement" / "annual_returns_synthetic.csv"


@pytest.fixture()
def synthetic_history() -> LongHistory:
    return load_long_history(str(FIXTURE))
