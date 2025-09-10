import json
from pathlib import Path

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
