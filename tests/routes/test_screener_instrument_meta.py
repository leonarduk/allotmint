"""Coverage for the route-only sector/name population on /screener rows."""

from backend.routes import screener


def test_apply_instrument_meta_sets_sector_and_fills_missing_name(monkeypatch):
    metas = {
        "AAA.L": {"name": "AAA PLC", "sector": "Basic Materials"},
        "BBB.L": {"name": "BBB PLC", "sector": ""},
    }
    monkeypatch.setattr(screener, "get_instrument_meta", lambda ticker: metas.get(ticker, {}))
    rows = [
        {"ticker": "AAA.L", "name": None},
        {"ticker": "BBB.L", "name": "Engine Name"},
        {"ticker": "CCC.L"},
    ]

    screener._apply_instrument_meta(rows)

    assert rows[0] == {"ticker": "AAA.L", "name": "AAA PLC", "sector": "Basic Materials"}
    # An engine-supplied name wins; a blank stored sector is None, not "".
    assert rows[1] == {"ticker": "BBB.L", "name": "Engine Name", "sector": None}
    assert rows[2] == {"ticker": "CCC.L", "sector": None}


def test_ranked_fundamentals_accepts_sector():
    assert screener.RankedFundamentals(ticker="AAA", rank=1, sector="Energy").sector == "Energy"
    assert screener.RankedFundamentals(ticker="AAA", rank=1).sector is None
