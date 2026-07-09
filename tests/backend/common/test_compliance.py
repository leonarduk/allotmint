import json
from datetime import date as real_date, datetime as real_datetime

import pytest

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
        compliance,
        "load_transactions",
        lambda owner, accounts_root=None, scaffold_missing=False: [],
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


def test_load_transactions_missing_owner_raises(tmp_path):
    accounts_root = tmp_path / "accounts"
    owner = "alex"

    with pytest.raises(FileNotFoundError):
        compliance.load_transactions(owner, accounts_root=accounts_root)

    records = compliance.load_transactions(
        owner, accounts_root=accounts_root, scaffold_missing=True
    )

    assert not (accounts_root / owner).exists()


def test_ensure_owner_scaffold_creates_defaults(tmp_path):
    accounts_root = tmp_path / "accounts"
    owner = "alex"

    owner_dir = compliance.ensure_owner_scaffold(owner, accounts_root=accounts_root)

    assert owner_dir == accounts_root / owner
    assert owner_dir.is_dir()

    settings_path = owner_dir / "settings.json"
    approvals_path = owner_dir / "approvals.json"
    tx_path = owner_dir / f"{owner}_transactions.json"

    assert settings_path.exists()
    assert approvals_path.exists()
    assert tx_path.exists()

    settings = json.loads(settings_path.read_text())
    approvals = json.loads(approvals_path.read_text())
    transactions = json.loads(tx_path.read_text())

    assert approvals == {"approvals": []}
    assert transactions.get("transactions") == []
    assert transactions.get("account_type") == "brokerage"
    assert "hold_days_min" in settings
    assert "max_trades_per_month" in settings


def test_check_trade_requires_owner(monkeypatch):
    called = False

    def fake_load_transactions(owner, accounts_root=None, scaffold_missing=False):
        nonlocal called
        called = True
        return []

    monkeypatch.setattr(compliance, "load_transactions", fake_load_transactions)

    with pytest.raises(ValueError, match="owner is required"):
        compliance.check_trade({"ticker": "ABC"})

    assert called is False


def test_check_transactions_logs_sanitised_invalid_share_count(monkeypatch, stubbed_env, caplog):
    """Malformed ``shares`` values are logged with control chars stripped.

    Regression test for #4015: the warning must not leak raw ``\\r``/``\\n``
    from attacker-controlled transaction fields into the log stream
    (CWE-117 log injection) - sanitise_log_value() must run on every logged
    field, and the sanitised shares/ticker/date values must appear in the
    warning message.
    """
    txs = [
        {
            "date": "2024-01-05",
            "ticker": "ABC\r\ninjected",
            "type": "buy",
            "shares": "not-a-number\r\nmalicious",
        }
    ]

    with caplog.at_level("WARNING"):
        result = compliance._check_transactions("alice", txs)

    assert result["warnings"] == []

    warning_records = [r for r in caplog.records if "invalid share count" in r.getMessage()]
    assert len(warning_records) == 1
    message = warning_records[0].getMessage()

    assert "\r" not in message
    assert "\n" not in message
    assert "not-a-numbermalicious" in message
    assert "ABCinjected" in message


def test_check_transactions_sanitises_ticker_when_shares_valid(
    monkeypatch, stubbed_env, caplog
):
    """CRLF in ``ticker`` is sanitised even when ``shares`` is valid.

    Complements test_check_transactions_logs_sanitised_invalid_share_count,
    which only exercises the invalid-shares warning branch. This covers the
    non-warning path: shares parse fine, but the sell still triggers the
    HOLD_DAYS_MIN/APPROVAL_REQUIRED info logs, which must sanitise the
    attacker-controlled ticker (CWE-117 log injection).
    """
    malicious_ticker = "FAKE\r\nLOG LINE"
    txs = [
        {
            "date": "2024-01-05",
            "ticker": malicious_ticker,
            "type": "buy",
            "shares": 10,
        },
        {
            "date": "2024-01-06",
            "ticker": malicious_ticker,
            "type": "sell",
            "shares": 5,
        },
    ]

    with caplog.at_level("INFO"):
        result = compliance._check_transactions("alice", txs)

    assert not any(
        "invalid share count" in r.getMessage() for r in caplog.records
    )

    ticker_records = [
        r
        for r in caplog.records
        if "HOLD_DAYS_MIN" in r.getMessage() or "APPROVAL_REQUIRED" in r.getMessage()
    ]
    assert ticker_records
    for record in ticker_records:
        message = record.getMessage()
        assert "\r" not in message
        assert "\n" not in message
        assert "FAKELOG LINE" in message

    assert result["warnings"]


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
