from datetime import UTC, datetime, timedelta, date

import pytest

import backend.screener as screener_module
from backend.screener import fetch_fundamentals, screen, Fundamentals


@pytest.fixture(autouse=True)
def reset_screener_cache():
    """Ensure screener cache state is clean between tests."""

    original_ttl = screener_module._CACHE_TTL_SECONDS
    screener_module._CACHE.clear()
    yield
    screener_module._CACHE.clear()
    screener_module._CACHE_TTL_SECONDS = original_ttl


@pytest.fixture
def empty_yahoo_ticker(monkeypatch):
    class _EmptyTicker:
        info = {}

    monkeypatch.setattr("backend.screener.yf.Ticker", lambda *_args, **_kwargs: _EmptyTicker())


def _make_base_fundamentals(ticker: str = "AAA") -> Fundamentals:
    return Fundamentals(
        ticker=ticker,
        name="Base Corp",
        peg_ratio=0.5,
        pe_ratio=10.0,
        de_ratio=0.5,
        lt_de_ratio=0.4,
        interest_coverage=12.0,
        current_ratio=2.0,
        quick_ratio=1.8,
        fcf=2000.0,
        eps=6.0,
        gross_margin=0.5,
        operating_margin=0.3,
        net_margin=0.2,
        ebitda_margin=0.35,
        roa=0.18,
        roe=0.25,
        roi=0.22,
        dividend_yield=0.04,
        dividend_payout_ratio=0.4,
        beta=1.1,
        shares_outstanding=1500,
        float_shares=1300,
        market_cap=8000,
        high_52w=120.0,
        low_52w=70.0,
        avg_volume=20000,
    )


def test_fetch_fundamentals_uses_cache(monkeypatch, empty_yahoo_ticker):
    sample = {
        "Name": "Cached Corp",
        "PEG": "0.5",
    }

    calls = {"count": 0}

    class MockResp:
        def raise_for_status(self):
            pass

        def json(self):
            return sample

    def mock_get(url, params, timeout):
        calls["count"] += 1
        return MockResp()

    monkeypatch.setattr("backend.screener.requests.get", mock_get)

    first = fetch_fundamentals("aapl")
    second = fetch_fundamentals("aapl")

    assert calls["count"] == 1
    assert first is second


def test_fetch_fundamentals_refreshes_expired_cache(monkeypatch, empty_yahoo_ticker):
    sample = {
        "Name": "Expired Corp",
        "PEG": "0.7",
    }

    calls = {"count": 0}

    class MockResp:
        def raise_for_status(self):
            pass

        def json(self):
            return sample

    def mock_get(url, params, timeout):
        calls["count"] += 1
        return MockResp()

    monkeypatch.setattr("backend.screener.requests.get", mock_get)

    first = fetch_fundamentals("aapl")
    cache_key = ("AAPL", date.today().isoformat())
    _, cached_value = screener_module._CACHE[cache_key]
    screener_module._CACHE[cache_key] = (
        datetime.now(UTC) - timedelta(seconds=screener_module._CACHE_TTL_SECONDS + 1),
        cached_value,
    )

    second = fetch_fundamentals("aapl")

    assert calls["count"] == 2
    assert second is not first


@pytest.mark.parametrize(
    "threshold_kwargs, failing_updates",
    [
        ({"peg_max": 1.0}, {"peg_ratio": 2.0}),
        ({"pe_max": 12.0}, {"pe_ratio": None}),
        ({"de_max": 0.6}, {"de_ratio": 0.8}),
        ({"lt_de_max": 0.5}, {"lt_de_ratio": 0.8}),
        ({"interest_coverage_min": 15.0}, {"interest_coverage": None}),
        ({"current_ratio_min": 2.5}, {"current_ratio": 2.0}),
        ({"quick_ratio_min": 2.0}, {"quick_ratio": None}),
        ({"fcf_min": 2500.0}, {"fcf": 2000.0}),
        ({"eps_min": 7.0}, {"eps": 6.0}),
        ({"gross_margin_min": 0.55}, {"gross_margin": None}),
        ({"operating_margin_min": 0.35}, {"operating_margin": 0.3}),
        ({"net_margin_min": 0.25}, {"net_margin": 0.2}),
        ({"ebitda_margin_min": 0.4}, {"ebitda_margin": 0.35}),
        ({"roa_min": 0.2}, {"roa": 0.18}),
        ({"roe_min": 0.3}, {"roe": None}),
        ({"roi_min": 0.24}, {"roi": 0.22}),
        ({"dividend_yield_min": 0.05}, {"dividend_yield": 0.04}),
        ({"dividend_payout_ratio_max": 0.35}, {"dividend_payout_ratio": None}),
        ({"beta_max": 1.0}, {"beta": 1.1}),
        ({"shares_outstanding_min": 1600}, {"shares_outstanding": 1500}),
        ({"float_shares_min": 1350}, {"float_shares": None}),
        ({"market_cap_min": 9000}, {"market_cap": 8000}),
        ({"high_52w_max": 110.0}, {"high_52w": 120.0}),
        ({"low_52w_min": 80.0}, {"low_52w": 70.0}),
        ({"avg_volume_min": 25000}, {"avg_volume": 20000}),
    ],
)
def test_screen_filters_each_threshold(monkeypatch, threshold_kwargs, failing_updates):
    base = _make_base_fundamentals()
    failing = base.model_copy(update=failing_updates)

    def mock_fetch(_):
        return failing

    monkeypatch.setattr("backend.screener.fetch_fundamentals", mock_fetch)

    assert screen(["AAA"], **threshold_kwargs) == []


def test_screen_skips_tickers_with_fetch_errors(monkeypatch):
    good = _make_base_fundamentals("BBB")

    def mock_fetch(ticker):
        if ticker == "AAA":
            raise RuntimeError("boom")
        return good.model_copy(update={"ticker": ticker})

    monkeypatch.setattr("backend.screener.fetch_fundamentals", mock_fetch)

    results = screen(["AAA", "BBB"])

    assert [r.ticker for r in results] == ["BBB"]


def test_fetch_fundamentals_parses_values(monkeypatch, empty_yahoo_ticker):
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

    monkeypatch.setattr(config, "alpha_vantage_key", "demo")
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
    assert f.eps == 5.0
    assert f.gross_margin == 0.4
    assert f.operating_margin == 0.2
    assert f.net_margin == 0.1
    assert f.ebitda_margin == 0.3
    assert f.roa == 0.15
    assert f.roe == 0.25
    assert f.roi == 0.2
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
                eps=5,
                gross_margin=0.4,
                operating_margin=0.2,
                net_margin=0.1,
                ebitda_margin=0.3,
                roa=0.15,
                roe=0.2,
                roi=0.18,
                lt_de_ratio=0.3,
                interest_coverage=10,
                current_ratio=2.0,
                quick_ratio=1.5,
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
            eps=1,
            gross_margin=0.2,
            operating_margin=0.05,
            net_margin=0.02,
            ebitda_margin=0.1,
            roa=0.05,
            roe=0.04,
            roi=0.03,
            lt_de_ratio=2.0,
            interest_coverage=1.0,
            current_ratio=0.5,
            quick_ratio=0.4,
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
        eps_min=3,
        gross_margin_min=0.3,
        operating_margin_min=0.1,
        net_margin_min=0.05,
        ebitda_margin_min=0.2,
        roa_min=0.1,
        roe_min=0.15,
        roi_min=0.1,
        lt_de_max=1.0,
        interest_coverage_min=5.0,
        current_ratio_min=1.0,
        quick_ratio_min=1.0,
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
