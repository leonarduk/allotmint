import pytest
from backend.screener import fetch_fundamentals, screen, Fundamentals


def test_fetch_fundamentals_parses_values(monkeypatch):
    sample = {
        "Name": "Foo Corp",
        "PEG": "1.5",
        "PERatio": "10.2",
        "DebtToEquityTTM": "0.5",
        "LongTermDebtToEquity": "0.3",
        "InterestCoverage": "8.5",
        "CurrentRatio": "2.1",
        "QuickRatio": "1.8",
        "FreeCashFlowTTM": "1234",
        "EPS": "5.0",
        "GrossProfitTTM": "0.4",
        "OperatingMarginTTM": "0.2",
        "NetProfitMarginTTM": "0.1",
        "EbitdaMarginTTM": "0.3",
        "ReturnOnAssetsTTM": "0.15",
        "ReturnOnEquityTTM": "0.25",
        "ReturnOnInvestmentTTM": "0.2",
        "DividendYield": "0.02",
        "PayoutRatio": "0.4",
        "Beta": "1.1",
        "SharesOutstanding": "1000",
        "SharesFloat": "800",
        "MarketCapitalization": "5000000",
        "52WeekHigh": "150",
        "52WeekLow": "100",
        "AverageDailyVolume10Day": "9000",
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

    from backend import config

    monkeypatch.setattr(config.settings, "alpha_vantage_key", "demo")
    monkeypatch.setattr("backend.screener.requests.get", mock_get)

    f = fetch_fundamentals("aapl")
    assert f.ticker == "AAPL"
    assert f.name == "Foo Corp"
    assert f.peg_ratio == 1.5
    assert f.pe_ratio == 10.2
    assert f.de_ratio == 0.5
    assert f.lt_de_ratio == 0.3
    assert f.interest_coverage == 8.5
    assert f.current_ratio == 2.1
    assert f.quick_ratio == 1.8
    assert f.fcf == 1234.0


def test_screen_filters_based_on_thresholds(monkeypatch):
    def mock_fetch(ticker):
        if ticker == "AAA":
            return Fundamentals(ticker="AAA", peg_ratio=0.5, pe_ratio=10, de_ratio=0.5, fcf=1000)
        return Fundamentals(ticker="BBB", peg_ratio=2.0, pe_ratio=15, de_ratio=1.5, fcf=500)

    monkeypatch.setattr("backend.screener.fetch_fundamentals", mock_fetch)

    results = screen(["AAA", "BBB"], peg_max=1.0, pe_max=20, de_max=1.0, fcf_min=800)
    assert [r.ticker for r in results] == ["AAA"]
