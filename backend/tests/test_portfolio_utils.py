from backend.common.portfolio_utils import _fx_to_gbp


def test_fx_to_gbp_logs_warning_on_failure(monkeypatch, caplog):
    def fake_fetch(currency, start, end):
        raise RuntimeError("boom")

    monkeypatch.setattr("backend.common.portfolio_utils.fetch_fx_rate_range", fake_fetch)
    cache = {}
    with caplog.at_level("WARNING"):
        rate = _fx_to_gbp("USD", cache)
    assert rate == 1.0
    assert cache["USD"] == 1.0
    assert "USD" in caplog.text
    assert "boom" in caplog.text
