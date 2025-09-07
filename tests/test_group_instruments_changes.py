import pytest

from backend.common import group_portfolio, instrument_api, portfolio_utils


def test_group_instruments_populates_change_fields(monkeypatch, client):
    portfolio = {
        "accounts": [
            {
                "account_type": "TEST",
                "holdings": [
                    {"ticker": "AAA.L", "units": 1.0, "cost_gbp": 90.0}
                ],
            }
        ]
    }
    monkeypatch.setattr(group_portfolio, "build_group_portfolio", lambda slug: portfolio)
    monkeypatch.setattr(portfolio_utils, "_PRICE_SNAPSHOT", {"AAA.L": {"last_price": 100.0}})
    monkeypatch.setattr(
        instrument_api,
        "price_change_pct",
        lambda t, d: {7: 5.0, 30: 10.0}.get(d),
    )
    resp = client.get("/portfolio-group/testslug/instruments")
    assert resp.status_code == 200
    instruments = resp.json()
    assert instruments[0]["change_7d_pct"] == 5.0
    assert instruments[0]["change_30d_pct"] == 10.0
