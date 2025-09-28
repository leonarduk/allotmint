import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from backend.common import transaction_reconciliation as tr


class FixedDate(date):
    @classmethod
    def today(cls) -> "FixedDate":  # type: ignore[override]
        return cls(2024, 1, 15)


@pytest.mark.parametrize(
    "raw, fallback, expected",
    [
        pytest.param(" Brokerage ", "ignored", "brokerage", id="trim-and-lower"),
        pytest.param(None, "Savings", "savings", id="fallback"),
    ],
)
def test_normalise_account_key(raw, fallback, expected):
    assert tr._normalise_account_key(raw, fallback) == expected


def test_load_json_handles_missing_file(tmp_path: Path, caplog: pytest.LogCaptureFixture):
    missing = tmp_path / "absent.json"
    assert tr._load_json(missing) is None
    assert any("Failed to read" in message for message in caplog.messages)


def test_load_json_handles_invalid_json(tmp_path: Path, caplog: pytest.LogCaptureFixture):
    invalid = tmp_path / "broken.json"
    invalid.write_text("not-json")
    assert tr._load_json(invalid) is None
    assert any("Invalid JSON" in message for message in caplog.messages)


def test_load_json_parses_valid_json(tmp_path: Path):
    payload = {"hello": "world"}
    path = tmp_path / "data.json"
    path.write_text(json.dumps(payload))
    assert tr._load_json(path) == payload


@pytest.mark.parametrize(
    "transactions, expected",
    [
        pytest.param(
            [
                {"type": "BUY", "ticker": "abc", "shares": 5},
                {"type": "SELL", "ticker": "ABC", "shares": 2},
            ],
            {"ABC": 3.0},
            id="basic-buys-sells",
        ),
        pytest.param(
            [
                {"kind": "purchase", "ticker": "def", "units": "4"},
                {"type": "SELL", "ticker": "def", "quantity": "1"},
            ],
            {"DEF": 3.0},
            id="alternate-fields",
        ),
        pytest.param(
            [
                {"type": "BUY", "ticker": "ghi", "shares": 2_000_000},
            ],
            {"GHI": 2_000_000 / tr._SHARE_SCALE},
            id="scaled-quantity",
        ),
        pytest.param(
            [
                {"type": "BUY", "ticker": "", "shares": 3},
                {"type": "BUY", "ticker": "jkl", "shares": "oops"},
                {"type": "BUY", "ticker": "jkl", "shares": 4},
            ],
            {"JKL": 4.0},
            id="skip-malformed-rows",
        ),
    ],
)
def test_transactions_to_positions(transactions, expected):
    assert tr._transactions_to_positions(transactions) == expected


def test_reconcile_transactions_with_holdings_adds_synthetic_entries(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(tr, "date", FixedDate)

    owner_dir = tmp_path / "alice"
    owner_dir.mkdir()

    account_file = owner_dir / "brokerage.json"
    account_file.write_text(
        json.dumps(
            {
                "account_type": "Brokerage",
                "holdings": [
                    {"ticker": "ABC", "units": 10},
                ],
            },
            indent=2,
        )
        + "\n"
    )

    transactions_file = owner_dir / "brokerage_transactions.json"
    transactions_file.write_text(
        json.dumps(
            {
                "transactions": [
                    {"date": "2024-01-01", "type": "BUY", "ticker": "ABC", "shares": 5},
                    {"date": "2024-01-02", "type": "SELL", "ticker": "ABC", "units": 1},
                    {"date": "2024-01-03", "type": "BUY", "ticker": "XYZ", "quantity": 2},
                ]
            },
            indent=2,
        )
        + "\n"
    )

    tr.reconcile_transactions_with_holdings(accounts_root=tmp_path)

    updated = json.loads(transactions_file.read_text())
    transactions = updated["transactions"]
    assert len(transactions) == 5

    synthetic_date = (FixedDate.today() - timedelta(days=365)).isoformat()

    first_synth, second_synth = transactions[-2:]

    assert first_synth == {
        "date": synthetic_date,
        "ticker": "ABC",
        "type": "BUY",
        "shares": 6.0,
        "units": 6.0,
        "synthetic": True,
    }
    assert second_synth == {
        "date": synthetic_date,
        "ticker": "XYZ",
        "type": "SELL",
        "shares": 2.0,
        "units": 2.0,
        "synthetic": True,
    }


