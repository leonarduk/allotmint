import json
from pathlib import Path

from backend.common import clean_accounts
from backend.common.clean_accounts import simplify_account_file, KEEP_FIELDS


def test_simplify_account_file(tmp_path: Path):
    # Create temporary account JSON with varied holdings
    account = {
        "holdings": [
            {
                "ticker": "AAA",
                "units": 10,
                "cost_basis_gbp": 100,
                "acquired_date": "2023-01-01",
                "extra": "remove-me",
            },
            {  # invalid: missing ticker
                "units": 5,
                "cost_basis_gbp": 50,
            },
            {  # missing units and cost_basis_gbp, should default to 0
                "ticker": "BBB",
            },
        ]
    }

    path = tmp_path / "acct.json"
    path.write_text(json.dumps(account))

    # Run simplification which overwrites the file
    simplify_account_file(path)

    data = json.loads(path.read_text())

    # Invalid holdings are skipped
    assert len(data["holdings"]) == 2
    assert all("ticker" in h for h in data["holdings"])

    # Missing fields default to zero
    defaults = next(h for h in data["holdings"] if h["ticker"] == "BBB")
    assert defaults["units"] == 0.0
    assert defaults["cost_basis_gbp"] == 0.0

    # Output holdings only contain KEEP_FIELDS
    for holding in data["holdings"]:
        assert set(holding) <= KEEP_FIELDS

    # Clean up temporary file
    path.unlink()


def test_main_writes_to_simplified_directory(tmp_path: Path, monkeypatch):
    repo_root = tmp_path
    accounts_dir = repo_root / "data" / "accounts"
    owner_dir = accounts_dir / "owner"
    owner_dir.mkdir(parents=True)

    original_path = owner_dir / "account.json"
    original_content = {
        "holdings": [
            {
                "ticker": "AAA",
                "units": 10,
                "cost_basis_gbp": 100,
                "acquired_date": "2023-01-01",
                "extra_field": "remove-me",
            }
        ],
        "notes": "retain top level extras",
    }
    original_path.write_text(json.dumps(original_content), encoding="utf-8")

    monkeypatch.setattr(clean_accounts, "REPO_ROOT", repo_root)
    monkeypatch.setattr(clean_accounts, "ACCOUNTS_DIR", accounts_dir)
    monkeypatch.setattr(clean_accounts, "OVERWRITE", False)

    clean_accounts.main()

    simplified_path = repo_root / "data" / "accounts_simplified" / "owner" / "account.json"
    assert simplified_path.exists()

    simplified_data = json.loads(simplified_path.read_text(encoding="utf-8"))
    assert simplified_data["notes"] == original_content["notes"]
    assert len(simplified_data["holdings"]) == 1
    simplified_holding = simplified_data["holdings"][0]
    assert set(simplified_holding) == KEEP_FIELDS

    original_data = json.loads(original_path.read_text(encoding="utf-8"))
    assert original_data == original_content
