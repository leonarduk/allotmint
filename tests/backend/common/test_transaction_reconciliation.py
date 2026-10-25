import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from backend.common import holdings_rebuild
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
                {"type": "BUY", "ticker": "abc", "units": 5},
                {"type": "SELL", "ticker": "ABC", "units": 2},
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
                {"type": "BUY", "ticker": "ghi", "shares": 999_999},
            ],
            {"GHI": 0.00999999},
            id="pp-scaled-shares",
        ),
        pytest.param(
            [
                {"type": "BUY", "ticker": "mno", "units": 2_000_000},
            ],
            {"MNO": 2_000_000.0},
            id="large-raw-units",
        ),
        pytest.param(
            [
                {"type": "BUY", "ticker": "", "units": 3},
                {"type": "BUY", "ticker": "jkl", "units": "oops"},
                {"type": "BUY", "ticker": "jkl", "units": 4},
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
                    {"date": "2024-01-01", "type": "BUY", "ticker": "ABC", "shares": 500_000_000},
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
        "units": 6.0,
        "synthetic": True,
    }
    assert second_synth == {
        "date": synthetic_date,
        "ticker": "XYZ",
        "type": "SELL",
        "units": 2.0,
        "synthetic": True,
    }


def _write_account(owner_dir: Path, cash: float, transactions: list[dict], **tx_meta: object) -> Path:
    owner_dir.mkdir()
    (owner_dir / "isa.json").write_text(
        json.dumps(
            {
                "account_type": "ISA",
                "holdings": [{"ticker": "ABC", "units": 10}, {"ticker": "CASH.GBP", "units": cash}],
            }
        )
    )
    tx_file = owner_dir / "ISA_transactions.json"
    tx_file.write_text(json.dumps({**tx_meta, "transactions": transactions}))
    return tx_file


_CASH_FLOW_ROWS = [
    {"date": "2024-01-01", "type": "TRANSFER_IN", "ticker": "CASH.GBP", "units": 1000.0},
    {"date": "2024-01-02", "type": "DEPOSIT", "amount_minor": 50000},
    {"date": "2024-01-03", "type": "BUY", "ticker": "ABC", "units": 10, "amount_minor": 20000},
    {"date": "2024-01-04", "type": "FEES", "amount_minor": 500},
]


def test_reconcile_leaves_cash_alone_when_replay_matches(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(tr, "date", FixedDate)
    # 1000 + 500 deposit - 200 buy - 5 fee: amount_minor rows the per-ticker ledger cannot see.
    tx_file = _write_account(tmp_path / "alice", 1295.0, _CASH_FLOW_ROWS, trade_cash_effects=True)
    before = tx_file.read_text()

    tr.reconcile_transactions_with_holdings(accounts_root=tmp_path)

    assert tx_file.read_text() == before


def test_reconcile_ignores_trade_settlements_without_opt_in(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(tr, "date", FixedDate)
    # Without trade_cash_effects only the transfer and deposit move cash.
    tx_file = _write_account(tmp_path / "alice", 1500.0, _CASH_FLOW_ROWS)
    before = tx_file.read_text()

    tr.reconcile_transactions_with_holdings(accounts_root=tmp_path)

    assert tx_file.read_text() == before


def test_reconcile_corrects_cash_the_replay_cannot_explain(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(tr, "date", FixedDate)
    tx_file = _write_account(tmp_path / "alice", 1200.0, _CASH_FLOW_ROWS, trade_cash_effects=True)

    tr.reconcile_transactions_with_holdings(accounts_root=tmp_path)

    injected = json.loads(tx_file.read_text())["transactions"][len(_CASH_FLOW_ROWS) :]
    assert len(injected) == 1
    assert injected[0]["ticker"] == "CASH.GBP"
    assert injected[0]["type"] == "SELL"
    assert injected[0]["units"] == pytest.approx(95.0)


_OPENING_ROWS = [
    {"date": "2024-01-01", "type": "TRANSFER_IN", "ticker": "CASH.GBP", "units": 1000.0},
    {"date": "2024-01-02", "type": "BUY", "ticker": "ABC", "units": 10},
]


@pytest.mark.parametrize(
    "row_type, expected_cash",
    [("DIVIDEND", 1050.0), ("INTEREST", 1050.0), ("WITHDRAWAL", 950.0)],
)
@pytest.mark.parametrize("drift", [0.0, -30.0])
def test_reconcile_replays_ticker_less_cash_movers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, row_type: str, expected_cash: float, drift: float
):
    # The issue behind #8209 lists dividends, interest and withdrawals as cash
    # movers too (#8214). Major units: amount_minor 5000 moves CASH.GBP by 50.
    monkeypatch.setattr(tr, "date", FixedDate)
    rows = [*_OPENING_ROWS, {"date": "2024-01-03", "type": row_type, "amount_minor": 5000}]
    assert holdings_rebuild.replay_transactions(rows).cash == pytest.approx(expected_cash)
    tx_file = _write_account(tmp_path / "alice", expected_cash + drift, rows)

    tr.reconcile_transactions_with_holdings(accounts_root=tmp_path)

    injected = json.loads(tx_file.read_text())["transactions"][len(rows) :]
    if not drift:
        assert injected == []
    else:
        assert [(tx["ticker"], tx["type"]) for tx in injected] == [("CASH.GBP", "SELL")]
        assert injected[0]["units"] == pytest.approx(-drift)


def test_reconcile_trusts_replayed_cash_when_ticker_less_rows_net_to_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    # cash_seen means "a cash-moving row was replayed", not "cash is non-zero":
    # rows the per-ticker ledger cannot see still decide CASH.GBP (#8210).
    monkeypatch.setattr(tr, "date", FixedDate)
    rows = [
        {"date": "2024-01-01", "type": "DEPOSIT", "amount_minor": 50000},
        {"date": "2024-01-02", "type": "WITHDRAWAL", "amount_minor": 50000},
    ]
    replay = holdings_rebuild.replay_transactions(rows)
    assert replay.cash_seen is True
    assert replay.cash == pytest.approx(0.0)
    assert tr._ledger_for({}, rows) == {"CASH.GBP": pytest.approx(0.0)}

    tx_file = _write_account(
        tmp_path / "alice", 25.0, [*rows, {"date": "2024-01-03", "type": "BUY", "ticker": "ABC", "units": 10}]
    )
    tr.reconcile_transactions_with_holdings(accounts_root=tmp_path)

    injected = json.loads(tx_file.read_text())["transactions"][3:]
    assert [(tx["ticker"], tx["type"], tx["units"]) for tx in injected] == [("CASH.GBP", "BUY", pytest.approx(25.0))]


def test_reconcile_falls_back_to_the_per_ticker_ledger_without_cash_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    # No cash-moving rows: the replay has no cash figure, so CASH.GBP comes from
    # the per-ticker ledger, which has none either (#8215).
    monkeypatch.setattr(tr, "date", FixedDate)
    rows = [{"date": "2024-01-02", "type": "BUY", "ticker": "ABC", "units": 10, "amount_minor": 20000}]
    assert holdings_rebuild.replay_transactions(rows).cash_seen is False
    assert tr._ledger_for({}, rows) == {"ABC": pytest.approx(10.0)}

    tx_file = _write_account(tmp_path / "alice", 0.0, rows)
    before = tx_file.read_text()
    tr.reconcile_transactions_with_holdings(accounts_root=tmp_path)

    assert tx_file.read_text() == before


def test_reconcile_skips_owner_metadata_files(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Metadata JSON is never read as holdings, even with a matching ledger (#10788)."""
    owner_dir = tmp_path / "lucy"
    owner_dir.mkdir()
    metadata = ("person", "settings", "approvals", "approval_requests", "pension-forecast")
    for stem in metadata:
        (owner_dir / f"{stem}.json").write_text(json.dumps({"holdings": [{"ticker": "ABC", "units": 1}]}))
        (owner_dir / f"{stem}_transactions.json").write_text(json.dumps({"transactions": []}))

    loaded: list[str] = []
    real_load_json = tr._load_json

    def recording_load_json(path: Path):
        loaded.append(path.name)
        return real_load_json(path)

    monkeypatch.setattr(tr, "_load_json", recording_load_json)

    tr.reconcile_transactions_with_holdings(accounts_root=tmp_path)

    assert loaded == []
    for stem in metadata:
        assert json.loads((owner_dir / f"{stem}_transactions.json").read_text()) == {"transactions": []}
