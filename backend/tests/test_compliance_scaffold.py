import json

import pytest

from backend.common import compliance


def test_check_trade_missing_owner_raises_without_scaffold(tmp_path, monkeypatch):
    accounts_root = tmp_path / "accounts"
    trade = {
        "owner": "newbie",
        "ticker": "PFE",
        "type": "buy",
        "date": "1970-01-01",
        "shares": 1,
    }

    monkeypatch.setattr(
        "backend.common.compliance.get_instrument_meta",
        lambda ticker: {},
    )

    with pytest.raises(FileNotFoundError):
        compliance.check_trade(trade, accounts_root)

    assert not (accounts_root / "newbie").exists()


def test_ensure_owner_scaffold_populates_person_metadata(tmp_path, monkeypatch):
    accounts_root = tmp_path / "accounts"
    owner = "newbie"
    trade = {
        "owner": owner,
        "ticker": "PFE",
        "type": "buy",
        "date": "1970-01-01",
        "shares": 1,
    }

    monkeypatch.setattr(
        "backend.common.compliance.get_instrument_meta",
        lambda ticker: {},
    )

    owner_dir = compliance.ensure_owner_scaffold(owner, accounts_root)
    result = compliance.check_trade(trade, accounts_root)

    assert result["owner"] == owner

    person_path = owner_dir / "person.json"
    assert person_path.exists()

    metadata = json.loads(person_path.read_text())
    assert metadata["owner"] == owner
    assert metadata["full_name"] == ""
    assert metadata["dob"] == ""
    assert metadata["email"] == ""
    assert isinstance(metadata.get("holdings"), list)
    assert isinstance(metadata.get("viewers"), list)
