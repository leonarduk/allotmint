import json

from scripts import reconcile_holding_tickers


def test_reconcile_account_file_updates_equity_and_flags_fund(tmp_path, monkeypatch):
    path = tmp_path / "sipp.json"
    path.write_text(
        json.dumps(
            {
                "holdings": [
                    {"ticker": "MSFT.L", "units": 2},
                    {"ticker": "BMNR1F3.L", "units": 0.001},
                ]
            }
        )
    )
    monkeypatch.setattr(
        reconcile_holding_tickers,
        "resolve_instrument_ticker",
        lambda ticker, create_missing: "MSFT.US" if ticker == "MSFT" else None,
    )

    result = reconcile_holding_tickers.reconcile_account_file(path, write=True)

    assert result == {"changed": ["MSFT.L -> MSFT.US"], "unresolved": ["BMNR1F3.L"]}
    holdings = json.loads(path.read_text())["holdings"]
    assert [holding["ticker"] for holding in holdings] == ["MSFT.US", "BMNR1F3.L"]
