import json

from scripts.python import reconcile_holding_tickers


def test_reconcile_file_rewrites_foreign_ticker_and_flags_sedol(tmp_path, monkeypatch):
    account = tmp_path / "sipp.json"
    account.write_text(
        json.dumps(
            {
                "holdings": [
                    {"ticker": "MSFT.L", "units": 2},
                    {"ticker": "GSK.L", "units": 1},
                    {"ticker": "BMNR1F3.L", "units": 0.001},
                ]
            }
        )
    )
    monkeypatch.setattr(
        reconcile_holding_tickers,
        "resolve_instrument_ticker",
        lambda symbol: "MSFT.N" if symbol == "MSFT" else f"{symbol}.L",
    )

    result = reconcile_holding_tickers.reconcile_file(account)

    assert result == {
        "changed": ["MSFT.L -> MSFT.N", "BMNR1F3.L -> BMNR1F3"],
        "manual_mapping_required": ["BMNR1F3"],
    }
    holdings = json.loads(account.read_text())["holdings"]
    assert [holding["ticker"] for holding in holdings] == ["MSFT.N", "GSK.L", "BMNR1F3"]
