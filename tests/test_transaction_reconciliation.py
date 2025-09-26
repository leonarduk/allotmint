import json
from datetime import date, timedelta

from backend.app import create_app
from backend.config import config


def _make_owner(tmp_path, owner: str, account: str, *, holdings_units: float, tx_units: float) -> None:
    owner_dir = tmp_path / owner
    owner_dir.mkdir(parents=True, exist_ok=True)
    (owner_dir / "person.json").write_text(json.dumps({"owner": owner}))

    account_payload = {
        "owner": owner,
        "account_type": account.upper(),
        "currency": "GBP",
        "last_updated": "2024-01-01",
        "holdings": [
            {
                "ticker": "AAA",
                "units": holdings_units,
                "cost_basis_gbp": 0.0,
            }
        ],
    }
    (owner_dir / f"{account.lower()}.json").write_text(json.dumps(account_payload))

    tx_payload = {
        "owner": owner,
        "account_type": account.upper(),
        "transactions": [
            {
                "date": "2024-01-01",
                "type": "BUY",
                "ticker": "AAA",
                "shares": tx_units,
                "units": tx_units,
            }
        ],
    }
    (owner_dir / f"{account.upper()}_transactions.json").write_text(json.dumps(tx_payload))


def test_reconcile_injects_synthetic_transaction(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "accounts_root", tmp_path)
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    monkeypatch.setattr(config, "offline_mode", True)

    _make_owner(tmp_path, "sam", "isa", holdings_units=10, tx_units=5)

    # Trigger application startup which performs reconciliation.
    app = create_app()
    assert app is not None

    tx_file = tmp_path / "sam" / "ISA_transactions.json"
    data = json.loads(tx_file.read_text())
    synthetic = [t for t in data["transactions"] if t.get("synthetic")]
    assert len(synthetic) == 1
    adj = synthetic[0]
    assert adj["type"] == "BUY"
    assert adj["shares"] == 5

    expected_date = (date.today() - timedelta(days=365)).isoformat()
    assert adj["date"] == expected_date


def test_reconcile_ignores_balanced_accounts(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "accounts_root", tmp_path)
    monkeypatch.setattr(config, "skip_snapshot_warm", True)
    monkeypatch.setattr(config, "offline_mode", True)

    _make_owner(tmp_path, "jane", "gia", holdings_units=4, tx_units=4)

    create_app()

    tx_file = tmp_path / "jane" / "GIA_transactions.json"
    data = json.loads(tx_file.read_text())
    assert all(not t.get("synthetic") for t in data["transactions"])
