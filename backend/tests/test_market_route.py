import backend.routes.market as market

def test_fetch_indexes_includes_ftse(monkeypatch):
    prices = {sym: i * 100.0 for i, sym in enumerate(market.INDEX_SYMBOLS.values(), start=1)}

    def fake_Tickers(symbols):
        assert "^FTSE" in symbols and "^FTMC" in symbols
        tickers = {
            sym: type("T", (), {"info": {"regularMarketPrice": price}})()
            for sym, price in prices.items()
        }
        return type("TT", (), {"tickers": tickers})()

    monkeypatch.setattr(market.yf, "Tickers", fake_Tickers)

    out = market._fetch_indexes()
    for name, sym in market.INDEX_SYMBOLS.items():
        assert out[name]["value"] == prices[sym]
        assert out[name]["change"] is None
