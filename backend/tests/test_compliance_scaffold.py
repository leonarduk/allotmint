import json

from backend.common import compliance


def test_check_trade_creates_default_person_metadata(tmp_path, monkeypatch):
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

    result = compliance.check_trade(trade, accounts_root)

    assert result["owner"] == "newbie"

    person_path = accounts_root / "newbie" / "person.json"
    assert person_path.exists()

    metadata = json.loads(person_path.read_text())
    assert metadata["owner"] == "newbie"
    assert isinstance(metadata.get("holdings"), list)
    assert isinstance(metadata.get("viewers"), list)
