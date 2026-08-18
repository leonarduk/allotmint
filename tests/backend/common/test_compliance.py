import json

import pytest

from backend.common import account_scaffold


def test_load_transactions_missing_owner_raises(tmp_path):
    accounts_root = tmp_path / "accounts"
    owner = "alex"

    with pytest.raises(FileNotFoundError):
        account_scaffold.load_transactions(owner, accounts_root=accounts_root)

    account_scaffold.load_transactions(owner, accounts_root=accounts_root, scaffold_missing=True)

    assert not (accounts_root / owner).exists()


def test_ensure_owner_scaffold_creates_defaults(tmp_path):
    accounts_root = tmp_path / "accounts"
    owner = "alex"

    owner_dir = account_scaffold.ensure_owner_scaffold(owner, accounts_root=accounts_root)

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
