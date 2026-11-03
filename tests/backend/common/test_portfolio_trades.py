"""Monthly trade counts come from the transaction ledger (#10811)."""

import datetime as dt
import json
import sys
from types import SimpleNamespace

import pytest

from backend.common import group_portfolio, portfolio
from backend.common.user_config import UserConfig

OCT = dt.date(2026, 10, 13)


def _write_ledger(root, owner, account, transactions):
    owner_dir = root / owner
    owner_dir.mkdir(parents=True, exist_ok=True)
    doc = {"owner": owner, "account_type": account, "transactions": transactions}
    (owner_dir / f"{account}_transactions.json").write_text(json.dumps(doc), encoding="utf-8")


def _rows(n, tx_type, date="2026-10-07"):
    return [{"date": date, "type": tx_type, "ticker": "VWRL.L", "units": 1} for _ in range(n)]


def test_counts_buy_and_sell_rows_in_current_month_across_accounts(tmp_path):
    _write_ledger(tmp_path, "steve", "SIPP", _rows(4, "BUY") + _rows(3, "SELL"))
    _write_ledger(tmp_path, "steve", "ISA", _rows(3, "buy") + _rows(2, "SELL", "2026-10-31"))

    assert portfolio.count_trades_in_month("steve", OCT, tmp_path) == 12


def test_ignores_income_cash_and_transfer_rows(tmp_path):
    non_trades = ["DIVIDEND", "INTEREST", "FEES", "DEPOSIT", "WITHDRAWAL", "TRANSFER_IN", "TRANSFER_OUT", ""]
    rows = _rows(1, "BUY") + [r for t in non_trades for r in _rows(1, t)]
    _write_ledger(tmp_path, "steve", "ISA", rows)

    assert portfolio.count_trades_in_month("steve", OCT, tmp_path) == 1


def test_ignores_other_months_and_undated_rows(tmp_path):
    rows = (
        _rows(1, "BUY", "2026-09-30")
        + _rows(1, "SELL", "2025-10-07")
        + _rows(1, "BUY", "2026-11-01")
        + _rows(1, "BUY", "")
        + _rows(1, "BUY", "not-a-date")
        + _rows(1, "SELL", "2026-10-01")
    )
    _write_ledger(tmp_path, "steve", "ISA", rows)

    assert portfolio.count_trades_in_month("steve", OCT, tmp_path) == 1


def test_missing_owner_or_unreadable_ledger_counts_zero(tmp_path):
    assert portfolio.count_trades_in_month("nobody", OCT, tmp_path) == 0
    (tmp_path / "steve").mkdir()
    (tmp_path / "steve" / "ISA_transactions.json").write_text("{broken", encoding="utf-8")
    assert portfolio.count_trades_in_month("steve", OCT, tmp_path) == 0
    assert portfolio.count_trades_in_month("../etc", OCT, tmp_path) == 0


def test_legacy_trades_csv_is_not_counted(tmp_path):
    _write_ledger(tmp_path, "steve", "ISA", _rows(1, "BUY"))
    (tmp_path / "steve" / "trades.csv").write_text("date,ticker\n2026-10-07,PFE\n", encoding="utf-8")

    assert portfolio.count_trades_in_month("steve", OCT, tmp_path) == 1


def test_skips_rows_with_non_string_dates(tmp_path):
    rows = _rows(1, "BUY") + [{"date": d, "type": "BUY"} for d in (20261007, None, ["2026-10-07"])]
    _write_ledger(tmp_path, "steve", "ISA", rows)

    assert portfolio.count_trades_in_month("steve", OCT, tmp_path) == 1


def test_aws_overlays_writable_s3_ledger_per_account(tmp_path, monkeypatch):
    _write_ledger(tmp_path, "steve", "ISA", _rows(5, "BUY"))
    _write_ledger(tmp_path, "steve", "SIPP", _rows(2, "SELL"))
    s3_docs = {
        "ISA_transactions.json": {"transactions": _rows(1, "BUY")},
        "person.json": {"owner": "steve"},
    }

    class FakeStore:
        def __init__(self, bucket):
            assert bucket == "bucket"

        def list_owner_files(self, owner):
            assert owner == "steve"
            return sorted(s3_docs)

        def read_document(self, owner, name):
            return s3_docs[name]

    monkeypatch.setenv("DATA_BUCKET", "bucket")
    monkeypatch.setattr(portfolio.config, "app_env", "aws", raising=False)
    monkeypatch.setitem(sys.modules, "backend.common.accounts_store", SimpleNamespace(S3AccountsStore=FakeStore))

    # S3 ISA (1 BUY) replaces the on-disk ISA (5 BUY); on-disk SIPP (2 SELL) stays.
    assert portfolio.count_trades_in_month("steve", OCT, tmp_path) == 3


def test_group_trade_counts_use_ledger(monkeypatch):
    monkeypatch.setattr(portfolio, "count_trades_in_month", lambda owner, month: 12)
    monkeypatch.setattr(group_portfolio, "load_user_config", lambda owner: UserConfig(max_trades_per_month=20))

    assert group_portfolio._trade_counts_for_owner("steve", OCT) == (12, 8)


# The same cases as allotmint-pro's tests/test_compliance.py::test_is_trade, so
# the two trade definitions cannot drift apart again (#11408).
@pytest.mark.parametrize(
    ("tx", "expected"),
    [
        ({"type": "BUY"}, True),
        ({"type": "buy"}, True),
        ({"type": "SELL"}, True),
        ({"type": "PURCHASE"}, True),
        ({"kind": "purchase"}, True),
        ({"type": "DIVIDEND"}, False),
        ({"type": "INTEREST"}, False),
        ({"type": "TRANSFER_IN"}, False),
        ({"type": "DIVIDEND", "kind": "BUY"}, False),
        ({"type": "", "kind": "SELL"}, True),
        ({"type": "  ", "kind": "SELL"}, True),
        ({"type": None, "kind": "buy"}, True),
        ({"type": " buy "}, True),
        ({}, False),
    ],
)
def test_is_trade(tx, expected):
    assert portfolio.is_trade(tx) is expected


def test_counts_purchase_and_kind_only_rows_but_not_a_dividend_tagged_buy(tmp_path):
    rows = (
        _rows(1, "PURCHASE")
        + [{"date": "2026-10-07", "type": " ", "kind": "BUY", "ticker": "VWRL.L"}]
        + [{"date": "2026-10-07", "type": "DIVIDEND", "kind": "BUY", "ticker": "VWRL.L"}]
    )
    _write_ledger(tmp_path, "steve", "ISA", rows)

    assert portfolio.count_trades_in_month("steve", OCT, tmp_path) == 2
