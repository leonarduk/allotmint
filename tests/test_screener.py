from backend.screener import Fundamentals, fetch_fundamentals, screen


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
