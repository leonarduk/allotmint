import pytest
from backend.screener import fetch_fundamentals, screen, Fundamentals


def test_fetch_fundamentals_parses_values(monkeypatch):
    sample = {
        "Name": "Foo Corp",
        "PEG": "1.5",
        "PERatio": "10.2",
        "DebtToEquityTTM": "0.5",
        "FreeCashFlowTTM": "1234",
        "PriceToBookRatio": "1.1",
        "PriceToSalesRatioTTM": "2.2",
        "PriceToCashFlowRatio": "3.3",
        "PriceToFreeCashFlowTTM": "4.4",
        "PriceToEBITDA": "5.5",
        "EVToEBITDA": "6.6",
        "EVToRevenue": "7.7",
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
    assert f.pb_ratio == 1.1
    assert f.ps_ratio == 2.2
    assert f.pc_ratio == 3.3
    assert f.pfcf_ratio == 4.4
    assert f.p_ebitda == 5.5
    assert f.ev_to_ebitda == 6.6
    assert f.ev_to_revenue == 7.7


def test_screen_filters_based_on_thresholds(monkeypatch):
    def mock_fetch(ticker):
        if ticker == "AAA":
            return Fundamentals(
                ticker="AAA",
                peg_ratio=0.5,
                pe_ratio=10,
                de_ratio=0.5,
                fcf=1000,
                pb_ratio=1.0,
                ps_ratio=2.0,
                pc_ratio=3.0,
                pfcf_ratio=4.0,
                p_ebitda=5.0,
                ev_to_ebitda=6.0,
                ev_to_revenue=7.0,
            )
        return Fundamentals(
            ticker="BBB",
            peg_ratio=2.0,
            pe_ratio=15,
            de_ratio=1.5,
            fcf=500,
            pb_ratio=10.0,
            ps_ratio=20.0,
            pc_ratio=30.0,
            pfcf_ratio=40.0,
            p_ebitda=50.0,
            ev_to_ebitda=60.0,
            ev_to_revenue=70.0,
        )

    monkeypatch.setattr("backend.screener.fetch_fundamentals", mock_fetch)

    results = screen(
        ["AAA", "BBB"],
        peg_max=1.0,
        pe_max=20,
        de_max=1.0,
        fcf_min=800,
        pb_max=2.0,
        ps_max=3.0,
        pc_max=4.0,
        pfcf_max=5.0,
        pebitda_max=6.0,
        ev_ebitda_max=7.0,
        ev_revenue_max=8.0,
    )
    assert [r.ticker for r in results] == ["AAA"]
