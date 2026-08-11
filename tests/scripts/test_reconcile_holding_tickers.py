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
        lambda ticker, create_missing: "MSFT.US" if ticker == "MSFT" and create_missing else None,
    )

    original_text = path.read_text()
    result = reconcile_holding_tickers.reconcile_account_file(path, write=True)

    assert result == {"changed": ["MSFT.L -> MSFT.US"], "unresolved": ["BMNR1F3.L"]}
    holdings = json.loads(path.read_text())["holdings"]
    assert [holding["ticker"] for holding in holdings] == ["MSFT.US", "BMNR1F3.L"]

    backup_path = path.with_suffix(path.suffix + ".bak")
    assert backup_path.read_text() == original_text


def test_reconcile_account_file_dry_run_does_not_create_missing_metadata(tmp_path, monkeypatch):
    """A dry run (no --write) must not trigger live Yahoo lookups/persistence (#6310)."""
    path = tmp_path / "sipp.json"
    path.write_text(json.dumps({"holdings": [{"ticker": "MSFT.L", "units": 2}]}))
    seen_create_missing: list[bool] = []

    def fake_resolve(ticker, create_missing):
        seen_create_missing.append(create_missing)
        return None

    monkeypatch.setattr(reconcile_holding_tickers, "resolve_instrument_ticker", fake_resolve)

    result = reconcile_holding_tickers.reconcile_account_file(path, write=False)

    assert seen_create_missing == [False]
    assert result == {"changed": [], "unresolved": ["MSFT.L"]}
