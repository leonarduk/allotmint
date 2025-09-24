import json

import backend.utils.build_instruments_from_accounts as bia


def test_build_instruments_reuses_existing_metadata(monkeypatch, tmp_path):
    instruments_dir = tmp_path / "instruments"
    valid_dir = instruments_dir / "TO"
    valid_dir.mkdir(parents=True)
    (valid_dir / "ABC.json").write_text(
        json.dumps(
            {
                "ticker": "ABC.TO",
                "name": "Stored Name",
                "Sector": "Stored Sector",
                "Region": "Stored Region",
                "currency": "CAD",
            }
        ),
        encoding="utf-8",
    )
    (instruments_dir / "invalid.json").write_text("{not-json", encoding="utf-8")

    accounts_dir = tmp_path / "accounts"
    owner_dir = accounts_dir / "alice"
    owner_dir.mkdir(parents=True)
    (owner_dir / "acct.json").write_text(
        json.dumps({"holdings": [{"ticker": "ABC.TO"}]}),
        encoding="utf-8",
    )

    monkeypatch.setattr(bia, "INSTRUMENTS_DIR", instruments_dir)
    monkeypatch.setattr(bia, "ACCOUNTS_DIR", accounts_dir)
    monkeypatch.setattr(bia, "SCALING_FILE", tmp_path / "scaling.json")

    instruments = bia.build_instruments()

    assert instruments == {
        "ABC.TO": {
            "ticker": "ABC.TO",
            "name": "Stored Name",
            "exchange": "TO",
            "currency": "CAD",
            "sector": "Stored Sector",
            "region": "Stored Region",
        }
    }
