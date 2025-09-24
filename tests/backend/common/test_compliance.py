import pytest
from datetime import date as real_date, datetime as real_datetime

from backend.common import compliance
from backend.common.user_config import UserConfig


class FixedDate(real_date):
    min = real_date.min

    @classmethod
    def today(cls):
        return cls(2024, 1, 31)


class FixedDateTime(real_datetime):
    @classmethod
    def now(cls, tz=None):
        if tz is None:
            return cls(2024, 1, 31, 12, 0, 0)
        return cls(2024, 1, 31, 12, 0, 0, tzinfo=tz)


@pytest.fixture
def stubbed_env(monkeypatch):
    strict_cfg = UserConfig(
        hold_days_min=30,
        max_trades_per_month=2,
        approval_exempt_types=[],
        approval_exempt_tickers=[],
    )

    monkeypatch.setattr(
        compliance, "load_transactions", lambda owner, accounts_root=None: []
    )
    monkeypatch.setattr(compliance, "load_approvals", lambda owner, accounts_root=None: {})
    monkeypatch.setattr(
        compliance,
        "load_user_config",
        lambda owner, accounts_root=None: strict_cfg,
    )
    monkeypatch.setattr(
        compliance,
        "get_instrument_meta",
        lambda ticker: {
            "instrumentType": "STOCK",
            "assetClass": "EQUITY",
            "sector": "TECH",
        },
    )
    monkeypatch.setattr(compliance, "is_approval_valid", lambda approval, asof: False)
    monkeypatch.setattr(compliance, "date", FixedDate)
    monkeypatch.setattr(compliance, "datetime", FixedDateTime)


def test_check_trade_requires_owner(monkeypatch):
    called = False

    def fake_load_transactions(owner, accounts_root=None):
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(compliance, "load_transactions", fake_load_transactions)

    with pytest.raises(ValueError, match="owner is required"):
        compliance.check_trade({"ticker": "ABC"})

    assert called is False


def test_evaluate_trades_attach_warnings_once(monkeypatch, stubbed_env):
    trades = [
        {"date": "2024-01-01", "ticker": "ABC", "type": "buy", "shares": 10},
        {"date": "2024-01-02", "ticker": "XYZ", "type": "buy", "shares": 5},
        {"date": "2024-01-15", "ticker": "ABC", "type": "sell", "shares": 5},
    ]

    evaluated = compliance.evaluate_trades("alice", trades)

    assert evaluated[0]["warnings"] == []
    assert evaluated[1]["warnings"] == []

    expected_warnings = [
        "3 trades in 2024-01 (max 2)",
        "Sold ABC after 14 days (min 30)",
        "Sold ABC without approval",
    ]
    assert evaluated[2]["warnings"] == expected_warnings

    for result, trade in zip(evaluated, trades):
        if trade is trades[2]:
            continue
        assert result.get("warnings") == []
