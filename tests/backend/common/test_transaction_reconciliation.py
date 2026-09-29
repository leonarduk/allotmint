import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from backend.common import transaction_reconciliation as tr
from backend.common.holdings_rebuild import CASH_TICKER, TRADE_CASH_FLAG, rebuild_holdings_document


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


def _write_account(owner_dir: Path, holdings: list[dict], tx_doc: dict) -> Path:
    owner_dir.mkdir(parents=True, exist_ok=True)
    (owner_dir / "isa.json").write_text(json.dumps({"account_type": "ISA", "holdings": holdings}))
    tx_path = owner_dir / "ISA_transactions.json"
    tx_path.write_text(json.dumps(tx_doc))
    return tx_path


def _rebuilt_cash(tx_path: Path) -> float | None:
    doc = rebuild_holdings_document(json.loads(tx_path.read_text()), "alice", "isa")
    return next((h["units"] for h in doc["holdings"] if h["ticker"] == CASH_TICKER), None)


# Cash in: 1000.00 transfer + 5000.00 deposit + 12.34 dividend = 6012.34.
# Trade settlements: BUY -1500.00, SELL +400.00; fees -9.99 -> 4902.35.
_TRADE_CASH_DOC = {
    TRADE_CASH_FLAG: True,
    "transactions": [
        {"date": "2024-01-01", "type": "TRANSFER_IN", "ticker": "CASH.GBP", "units": 1000.0},
        {"date": "2024-01-02", "type": "DEPOSIT", "amount_minor": 500000},
        {"date": "2024-01-03", "type": "BUY", "ticker": "ABC", "shares": 10, "amount_minor": 150000},
        {"date": "2024-02-01", "type": "SELL", "ticker": "ABC", "shares": 2, "amount_minor": 40000},
        {"date": "2024-02-02", "type": "DIVIDEND", "amount_minor": 1234},
        {"date": "2024-02-03", "type": "FEES", "amount_minor": 999},
    ],
}


def test_reconcile_injects_nothing_when_trade_cash_rebuild_matches(tmp_path: Path):
    tx_path = _write_account(
        tmp_path / "alice",
        [{"ticker": "ABC", "units": 8}, {"ticker": "CASH.GBP", "units": 4902.35}],
        _TRADE_CASH_DOC,
    )
    assert _rebuilt_cash(tx_path) == 4902.35
    before = tx_path.read_text()

    tr.reconcile_transactions_with_holdings(accounts_root=tmp_path)

    assert tx_path.read_text() == before


def test_reconcile_counts_legacy_cash_flows_without_trade_cash_flag(tmp_path: Path):
    tx_path = _write_account(
        tmp_path / "alice",
        [{"ticker": "CASH.GBP", "units": 250.5}],
        {
            "transactions": [
                {"date": "2024-01-01", "type": "DEPOSIT", "amount_minor": 30000},
                {"date": "2024-01-02", "type": "WITHDRAWAL", "amount_minor": 5000},
                {"date": "2024-01-03", "type": "INTEREST", "amount_minor": 50},
                # Without the flag, fees and settlements leave cash alone.
                {"date": "2024-01-04", "type": "FEES", "amount_minor": 100},
            ]
        },
    )
    before = tx_path.read_text()

    tr.reconcile_transactions_with_holdings(accounts_root=tmp_path)

    assert tx_path.read_text() == before


def test_reconcile_cash_adjustment_brings_rebuild_into_line(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(tr, "date", FixedDate)
    tx_path = _write_account(
        tmp_path / "alice",
        [{"ticker": "ABC", "units": 8}, {"ticker": "CASH.GBP", "units": 5000.0}],
        _TRADE_CASH_DOC,
    )

    tr.reconcile_transactions_with_holdings(accounts_root=tmp_path)

    synthetic = [t for t in json.loads(tx_path.read_text())["transactions"] if t.get("synthetic")]
    assert len(synthetic) == 1
    assert synthetic[0]["ticker"] == CASH_TICKER
    assert synthetic[0]["type"] == "BUY"
    assert synthetic[0]["units"] == pytest.approx(97.65)
    assert _rebuilt_cash(tx_path) == 5000.0

    # A second startup finds nothing left to reconcile.
    after_first = tx_path.read_text()
    tr.reconcile_transactions_with_holdings(accounts_root=tmp_path)
    assert tx_path.read_text() == after_first
