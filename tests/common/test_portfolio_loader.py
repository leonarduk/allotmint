import json
import logging
from pathlib import Path

import pytest

from backend.common.portfolio_loader import rebuild_account_holdings


def test_rebuild_account_holdings(tmp_path: Path) -> None:
    owner_dir = tmp_path / "alice"
    owner_dir.mkdir()
    tx_file = owner_dir / "ISA_transactions.json"
    tx_data = {
        "currency": "GBP",
        "transactions": [
            {"type": "BUY", "ticker": "ABC", "shares": 200_000_000, "date": "2024-01-10"},
            {"type": "SELL", "ticker": "ABC", "shares": 50_000_000, "date": "2024-02-15"},
            {"type": "TRANSFER_IN", "ticker": "XYZ", "shares": 150_000_000, "date": "2024-03-20"},
            {"type": "TRANSFER_OUT", "ticker": "XYZ", "shares": 50_000_000, "date": "2024-04-25"},
            {"type": "REMOVAL", "ticker": "XYZ", "shares": 25_000_000, "date": "2024-05-30"},
            {"type": "DEPOSIT", "amount_minor": 10000},
            {"type": "WITHDRAWAL", "amount_minor": 5000},
            {"type": "DIVIDENDS", "amount_minor": 2500},
        ],
    }
    tx_file.write_text(json.dumps(tx_data))

    result = rebuild_account_holdings("alice", "isa", accounts_root=tmp_path)

    holdings = {h["ticker"]: h for h in result["holdings"]}

    assert holdings["ABC"]["units"] == pytest.approx(1.5)
    assert holdings["ABC"]["acquired_date"] == "2024-01-10"

    assert holdings["XYZ"]["units"] == pytest.approx(0.75)
    assert holdings["XYZ"]["acquired_date"] == "2024-03-20"

    assert holdings["CASH.GBP"]["units"] == pytest.approx(75.0)


def test_rebuild_account_holdings_missing_file(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.ERROR, logger="portfolio_loader")

    result = rebuild_account_holdings("bob", "isa", accounts_root=tmp_path)

    assert result == {}
    assert "Transaction file missing" in caplog.text
