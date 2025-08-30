import backend.common.portfolio_utils as pu


def test_check_price_alerts_retains_exchange_suffix(monkeypatch):
    snapshot = {"AAA.L": {"last_price": 110.0}}
    portfolio = {"accounts": [{"holdings": [{"ticker": "AAA", "units": 1, "cost_gbp": 100}]}]}
    monkeypatch.setattr(pu, "_PRICE_SNAPSHOT", snapshot)
    monkeypatch.setattr(pu, "list_portfolios", lambda: [portfolio])
    monkeypatch.setattr("backend.common.alerts.publish_alert", lambda alert: None)

    alerts = pu.check_price_alerts(threshold_pct=0.05)
    assert alerts and alerts[0]["ticker"] == "AAA.L"
