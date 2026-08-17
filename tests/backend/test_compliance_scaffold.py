import json

from backend.common import compliance
from backend.common.account_scaffold import ensure_owner_scaffold

import allotmint_core.compliance as compliance_impl


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
        compliance_impl,
        "get_instrument_meta",
        lambda ticker: {},
    )

    owner_dir = ensure_owner_scaffold(owner, accounts_root)
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
