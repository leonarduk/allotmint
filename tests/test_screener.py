import pytest
from backend.screener import fetch_fundamentals, screen, Fundamentals


def test_fetch_fundamentals_parses_values(monkeypatch):
    sample = {
        "Name": "Foo Corp",
        "PEG": "1.5",
        "PERatio": "10.2",
        "DebtToEquityTTM": "0.5",
        "FreeCashFlowTTM": "1234",
    }

    class MockResp:
        def raise_for_status(self):
            pass

        def json(self):
            return sample

    def mock_get(url, params, timeout):
        assert params["function"] == "OVERVIEW"
        assert params["symbol"] == "aapl"
        return MockResp()

    monkeypatch.setenv("ALPHAVANTAGE_API_KEY", "demo")
    monkeypatch.setattr("backend.screener.ALPHA_VANTAGE_KEY", "demo")
    monkeypatch.setattr("backend.screener.requests.get", mock_get)

    f = fetch_fundamentals("aapl")
    assert f.ticker == "AAPL"
    assert f.name == "Foo Corp"
    assert f.peg_ratio == 1.5
    assert f.pe_ratio == 10.2
    assert f.de_ratio == 0.5
    assert f.fcf == 1234.0


def test_screen_filters_based_on_thresholds(monkeypatch):
    def mock_fetch(ticker):
        if ticker == "AAA":
            return Fundamentals(ticker="AAA", peg_ratio=0.5, pe_ratio=10, de_ratio=0.5, fcf=1000)
        return Fundamentals(ticker="BBB", peg_ratio=2.0, pe_ratio=15, de_ratio=1.5, fcf=500)

    monkeypatch.setattr("backend.screener.fetch_fundamentals", mock_fetch)

    results = screen(["AAA", "BBB"], peg_max=1.0, pe_max=20, de_max=1.0, fcf_min=800)
    assert [r.ticker for r in results] == ["AAA"]
