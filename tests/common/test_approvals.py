import json
from datetime import date
from pathlib import Path

import pytest

from backend.common.approvals import (
    approvals_path,
    delete_approval,
    is_approval_valid,
    load_approvals,
    upsert_approval,
)


def test_approvals_path(tmp_path: Path) -> None:
    """Check path resolution and missing owner handling."""
    with pytest.raises(FileNotFoundError):
        approvals_path("alice", accounts_root=tmp_path)

    owner_dir = tmp_path / "bob"
    owner_dir.mkdir()
    expect = owner_dir / "approvals.json"
    assert approvals_path("bob", accounts_root=tmp_path) == expect


def test_load_upsert_delete(tmp_path: Path) -> None:
    owner_dir = tmp_path / "bob"
    owner_dir.mkdir()

    # Load existing entries
    data = {"approvals": [{"ticker": "adm.l", "approved_on": "2024-06-04"}]}
    (owner_dir / "approvals.json").write_text(json.dumps(data))
    loaded = load_approvals("bob", accounts_root=tmp_path)
    assert loaded == {"ADM.L": date(2024, 6, 4)}

    # Upsert and persist a new approval
    appr_on = date(2024, 6, 5)
    out = upsert_approval("bob", "xyz", appr_on, accounts_root=tmp_path)
    assert out["XYZ"] == appr_on
    stored = json.loads((owner_dir / "approvals.json").read_text())
    assert {row["ticker"] for row in stored["approvals"]} == {"ADM.L", "XYZ"}

    # Delete and persist
    out = delete_approval("bob", "adm.l", accounts_root=tmp_path)
    assert "ADM.L" not in out
    stored = json.loads((owner_dir / "approvals.json").read_text())
    assert stored["approvals"] == [{"ticker": "XYZ", "approved_on": "2024-06-05"}]


def test_is_approval_valid_expiry() -> None:
    approved_on = date(2024, 6, 7)  # Friday
    assert is_approval_valid(approved_on, date(2024, 6, 10), days=3)
    assert is_approval_valid(approved_on, date(2024, 6, 11), days=3)
    assert not is_approval_valid(approved_on, date(2024, 6, 12), days=3)
    assert not is_approval_valid(None, date(2024, 6, 10), days=1)
