import json

import pytest

from backend.common.portfolio_loader import compute_holdings_from_transactions
from backend.routes import transactions as tx_routes
from scripts import convert_untracked_holdings as convert


def _write(path, doc):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc))


def _seed(tmp_path):
    """alice/isa: AAA entered by hand (no transactions), BBB bought through a transaction."""
    _write(
        tmp_path / "alice" / "isa.json",
        {
            "owner": "alice",
            "account_type": "ISA",
            "holdings": [
                {"ticker": "AAA", "units": 10, "cost_basis_gbp": 100.0, "name": "Aaa plc", "value_gbp": 150.0},
                {"ticker": "BBB", "units": 5, "cost_basis_gbp": 50.0},
            ],
        },
    )
    _write(
        tmp_path / "alice" / "isa_transactions.json",
        {
            "owner": "alice",
            "account_type": "isa",
            "transactions": [{"type": "BUY", "ticker": "BBB", "date": "2023-02-01", "units": 5, "price_gbp": 10.0}],
        },
    )


def test_opening_transfers_covers_only_untracked_holdings():
    transactions = [{"type": "BUY", "ticker": "BBB", "date": "2023-02-01", "units": 5, "price_gbp": 10.0}]
    holdings = [
        {"ticker": "AAA", "units": 10, "cost_basis_gbp": 100.0},
        {"ticker": "BBB", "units": 5},
        {"ticker": "CCC", "units": 4, "acquired_date": "2021-06-30T00:00:00"},
        {"ticker": "CASH.GBP", "units": 12.5},
        {"ticker": "DDD", "value_gbp": 900},
    ]

    transfers, skipped = convert.opening_transfers(transactions, holdings)

    assert transfers == [
        {
            "type": "TRANSFER_IN",
            "ticker": "AAA",
            "date": "2023-02-01",
            "units": 10.0,
            "reason": tx_routes.OPENING_BALANCE_REASON,
            "price_gbp": 10.0,
        },
        {
            "type": "TRANSFER_IN",
            "ticker": "CCC",
            "date": "2021-06-30",
            "units": 4.0,
            "reason": tx_routes.OPENING_BALANCE_REASON,
        },
    ]
    assert [ticker for ticker, _ in skipped] == ["CASH.GBP", "DDD"]


def test_write_records_the_transfer_rebuilds_and_is_idempotent(tmp_path, capsys):
    _seed(tmp_path)

    assert convert.main(["--accounts-root", str(tmp_path), "--owner", "alice", "--write"]) == 0

    stored = json.loads((tmp_path / "alice" / "isa_transactions.json").read_text())["transactions"]
    assert [(t["type"], t["ticker"]) for t in stored] == [("BUY", "BBB"), ("TRANSFER_IN", "AAA")]
    holdings = {h["ticker"]: h for h in json.loads((tmp_path / "alice" / "isa.json").read_text())["holdings"]}
    assert (holdings["AAA"]["units"], holdings["AAA"]["cost_basis_gbp"], holdings["AAA"]["name"]) == (
        10.0,
        100.0,
        "Aaa plc",
    )
    assert holdings["BBB"]["units"] == 5.0
    assert "Recorded 1 opening-balance transfer(s)." in capsys.readouterr().out

    assert convert.main(["--accounts-root", str(tmp_path), "--owner", "alice", "--write"]) == 0
    assert len(json.loads((tmp_path / "alice" / "isa_transactions.json").read_text())["transactions"]) == 2
    assert "Recorded 0 opening-balance transfer(s)." in capsys.readouterr().out


def test_dry_run_reports_and_writes_nothing(tmp_path, capsys):
    _seed(tmp_path)
    before = sorted((p.name, p.read_text()) for p in (tmp_path / "alice").iterdir())

    assert convert.main(["--accounts-root", str(tmp_path)]) == 0

    assert sorted((p.name, p.read_text()) for p in (tmp_path / "alice").iterdir()) == before
    out = capsys.readouterr().out
    assert "alice/isa:" in out
    assert "would record AAA: TRANSFER_IN 10 units at GBP 10, dated 2023-02-01" in out


def test_holdings_without_a_transactions_file_get_a_lower_case_one(tmp_path):
    _write(tmp_path / "bob" / "sipp.json", {"owner": "bob", "holdings": [{"ticker": "AAA", "units": 2}]})

    assert convert.main(["--accounts-root", str(tmp_path), "--all", "--write"]) == 0

    assert [p.name for p in (tmp_path / "bob").glob("*_transactions.json")] == ["sipp_transactions.json"]


def test_write_for_every_owner_requires_all(tmp_path):
    with pytest.raises(SystemExit):
        convert.main(["--accounts-root", str(tmp_path), "--write"])


def test_rebuild_keeps_an_uneven_cost_and_an_unknown_one(tmp_path):
    _write(
        tmp_path / "alice" / "isa.json",
        {
            "owner": "alice",
            "holdings": [
                {"ticker": "AAA", "units": 3, "cost_basis_gbp": 100.0},
                {"ticker": "BBB", "units": 7, "cost_basis_gbp": 0, "value_gbp": 70.0},
                {"ticker": "CCC", "units": 2, "value_gbp": 20.0},
            ],
        },
    )

    assert convert.main(["--accounts-root", str(tmp_path), "--owner", "alice", "--write"]) == 0

    holdings = {h["ticker"]: h for h in json.loads((tmp_path / "alice" / "isa.json").read_text())["holdings"]}
    assert (holdings["AAA"]["units"], holdings["AAA"]["cost_basis_gbp"]) == (3.0, 100.0)
    assert (holdings["BBB"]["units"], holdings["BBB"]["cost_basis_gbp"], holdings["BBB"]["value_gbp"]) == (7.0, 0, 70.0)
    assert (holdings["CCC"]["units"], holdings["CCC"]["cost_basis_gbp"]) == (2.0, 0.0)


def _seed_cash(tmp_path, balance, **tx_doc_extra):
    _write(
        tmp_path / "alice" / "isa.json",
        {
            "owner": "alice",
            "holdings": [
                {"ticker": "CASH.GBP", "units": balance, "cost_basis_gbp": balance},
                {"ticker": "BBB", "units": 5, "cost_basis_gbp": 50.0},
            ],
        },
    )
    _write(
        tmp_path / "alice" / "isa_transactions.json",
        {
            "owner": "alice",
            "account_type": "isa",
            **tx_doc_extra,
            "transactions": [{"type": "BUY", "ticker": "BBB", "date": "2023-02-01", "units": 5, "price_gbp": 10.0}],
        },
    )


def _cash(tmp_path):
    holdings = json.loads((tmp_path / "alice" / "isa.json").read_text())["holdings"]
    return next(h["units"] for h in holdings if h["ticker"] == "CASH.GBP")


def test_cash_is_only_reported_without_include_cash(tmp_path, capsys):
    _seed_cash(tmp_path, 2000)

    assert convert.main(["--accounts-root", str(tmp_path), "--owner", "alice", "--write"]) == 0

    assert len(json.loads((tmp_path / "alice" / "isa_transactions.json").read_text())["transactions"]) == 1
    assert "skipped CASH.GBP: cash balance: re-run with --include-cash" in capsys.readouterr().out


def test_include_cash_records_an_opening_deposit_that_a_later_dividend_adds_to(tmp_path, capsys):
    _seed_cash(tmp_path, 2000)

    assert convert.main(["--accounts-root", str(tmp_path), "--owner", "alice", "--include-cash", "--write"]) == 0

    tx_doc = json.loads((tmp_path / "alice" / "isa_transactions.json").read_text())
    deposit = tx_doc["transactions"][-1]
    assert (deposit["type"], deposit["amount_minor"], deposit["date"]) == ("DEPOSIT", 200000, "2023-02-01")
    assert _cash(tmp_path) == pytest.approx(2000)
    assert "recorded CASH.GBP: DEPOSIT GBP 2,000.00, dated 2023-02-01" in capsys.readouterr().out

    # Why it matters: without the deposit the rebuild would value the cash at this dividend alone.
    tx_doc["transactions"].append({"type": "DIVIDEND", "ticker": "BBB", "date": "2024-01-01", "amount_minor": 1234})
    existing = json.loads((tmp_path / "alice" / "isa.json").read_text())
    rebuilt = compute_holdings_from_transactions(tx_doc, "alice", "isa", existing)["holdings"]
    assert next(h["units"] for h in rebuilt if h["ticker"] == "CASH.GBP") == pytest.approx(2012.34)

    assert convert.main(["--accounts-root", str(tmp_path), "--owner", "alice", "--include-cash", "--write"]) == 0
    assert len(json.loads((tmp_path / "alice" / "isa_transactions.json").read_text())["transactions"]) == 2


def test_include_cash_records_a_withdrawal_for_an_overdrawn_balance(tmp_path):
    _seed_cash(tmp_path, -12.5)

    assert convert.main(["--accounts-root", str(tmp_path), "--owner", "alice", "--include-cash", "--write"]) == 0

    withdrawal = json.loads((tmp_path / "alice" / "isa_transactions.json").read_text())["transactions"][-1]
    assert (withdrawal["type"], withdrawal["amount_minor"]) == ("WITHDRAWAL", 1250)
    assert _cash(tmp_path) == pytest.approx(-12.5)


def test_include_cash_leaves_cash_that_trades_already_settle(tmp_path):
    _seed_cash(tmp_path, -50, trade_cash_effects=True)

    assert convert.main(["--accounts-root", str(tmp_path), "--owner", "alice", "--include-cash", "--write"]) == 0

    assert len(json.loads((tmp_path / "alice" / "isa_transactions.json").read_text())["transactions"]) == 1
