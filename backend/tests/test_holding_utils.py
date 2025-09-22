import datetime as dt

import pytest

from backend.common.constants import ACQUIRED_DATE, COST_BASIS_GBP, TICKER, UNITS
from backend.common import holding_utils as hu
from backend.common.holding_utils import EFFECTIVE_COST_BASIS_GBP


def test_enrich_holding_scales_booked_cost_basis(monkeypatch):
    """Booked GBX cost bases should respect scaling overrides."""

    # Always scale by 0.01 (e.g., GBX -> GBP)
    monkeypatch.setattr(hu, "get_scaling_override", lambda *args, **kwargs: 0.01)
    monkeypatch.setattr(hu, "get_instrument_meta", lambda *_: {})

    import backend.common.instrument_api as instrument_api
    import backend.common.portfolio_utils as pu

    monkeypatch.setattr(instrument_api, "_resolve_full_ticker", lambda *_: ("FOO", "L"))
    monkeypatch.setattr(pu, "get_security_meta", lambda *_: {})
    monkeypatch.setattr(
        pu,
        "_PRICE_SNAPSHOT",
        {"FOO.L": {"last_price": 2.0, "is_stale": False}},
    )
    monkeypatch.setattr(hu, "_get_price_for_date_scaled", lambda *args, **kwargs: (1.9, "mock"))

    holding = {
        TICKER: "FOO.L",
        UNITS: 1,
        COST_BASIS_GBP: 123.45,
        ACQUIRED_DATE: "2024-01-01",
    }

    enriched = hu.enrich_holding(holding, dt.date(2024, 1, 31), price_cache={}, approvals=None, user_config=None)

    assert enriched[COST_BASIS_GBP] == pytest.approx(1.23)
    assert enriched[EFFECTIVE_COST_BASIS_GBP] == pytest.approx(1.23)
    assert enriched["gain_gbp"] == pytest.approx(0.77)
