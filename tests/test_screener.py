import pytest
from backend.screener import fetch_fundamentals, screen, Fundamentals


def test_fetch_fundamentals_parses_values(monkeypatch):
    sample = {
        "Name": "Foo Corp",
        "PEG": "1.5",
        "PERatio": "10.2",
        "DebtToEquityTTM": "0.5",
        "FreeCashFlowTTM": "1234",
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
    assert f.fcf == 1234.0
    assert f.dividend_yield == 0.02
    assert f.dividend_payout_ratio == 0.4
    assert f.beta == 1.1
    assert f.shares_outstanding == 1000
    assert f.float_shares == 800
    assert f.market_cap == 5000000
    assert f.high_52w == 150.0
    assert f.low_52w == 100.0
    assert f.avg_volume == 9000


def test_screen_filters_based_on_thresholds(monkeypatch):
    def mock_fetch(ticker):
        if ticker == "AAA":
            return Fundamentals(
                ticker="AAA",
                peg_ratio=0.5,
                pe_ratio=10,
                de_ratio=0.5,
                fcf=1000,
                dividend_yield=0.03,
                dividend_payout_ratio=0.4,
                beta=1.0,
                shares_outstanding=1000,
                float_shares=800,
                market_cap=5000,
                high_52w=200,
                low_52w=100,
                avg_volume=10000,
            )
        return Fundamentals(
            ticker="BBB",
            peg_ratio=2.0,
            pe_ratio=15,
            de_ratio=1.5,
            fcf=500,
            dividend_yield=0.01,
            dividend_payout_ratio=0.8,
            beta=2.0,
            shares_outstanding=500,
            float_shares=300,
            market_cap=1000,
            high_52w=300,
            low_52w=50,
            avg_volume=5000,
        )

    monkeypatch.setattr("backend.screener.fetch_fundamentals", mock_fetch)

    results = screen(
        ["AAA", "BBB"],
        peg_max=1.0,
        pe_max=20,
        de_max=1.0,
        fcf_min=800,
        dividend_yield_min=0.02,
        dividend_payout_ratio_max=0.5,
        beta_max=1.5,
        shares_outstanding_min=800,
        float_shares_min=700,
        market_cap_min=2000,
        high_52w_max=250,
        low_52w_min=80,
        avg_volume_min=8000,
    )
    assert [r.ticker for r in results] == ["AAA"]
