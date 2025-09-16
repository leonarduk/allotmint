import json
from datetime import date

import pytest

from backend.common.approvals import (
    add_trading_days,
    approvals_path,
    delete_approval,
    is_approval_valid,
    load_approvals,
    upsert_approval,
)
from backend.config import config


def test_approvals_path_missing_owner(tmp_path):
    with pytest.raises(FileNotFoundError) as exc:
        approvals_path("missing", accounts_root=tmp_path)
    assert exc.value.args[0] == tmp_path / "missing"


def test_load_approvals_valid_and_invalid_json(tmp_path):
    owner = tmp_path / "alice"
    owner.mkdir()
    (owner / "approvals.json").write_text(
        json.dumps([{"ticker": "adm.l", "approved_on": "2024-06-01"}])
    )

    loaded = load_approvals("alice", accounts_root=tmp_path)
    assert loaded == {"ADM.L": date(2024, 6, 1)}

    broken_owner = tmp_path / "bob"
    broken_owner.mkdir()
    (broken_owner / "approvals.json").write_text("not json")

    assert load_approvals("bob", accounts_root=tmp_path) == {}


def test_add_trading_days_skips_weekends():
    start = date(2024, 5, 31)  # Friday
    assert add_trading_days(start, 1) == date(2024, 6, 3)
    assert add_trading_days(start, 2) == date(2024, 6, 4)


def test_is_approval_valid_respects_config(monkeypatch):
    approved_on = date(2024, 6, 3)

    assert is_approval_valid(None, approved_on) is False

    monkeypatch.setattr(config, "approval_valid_days", None)
    assert is_approval_valid(approved_on, approved_on) is True
    assert is_approval_valid(approved_on, date(2024, 6, 4)) is False

    monkeypatch.setattr(config, "approval_valid_days", 2)
    assert is_approval_valid(approved_on, date(2024, 6, 4)) is True
    assert is_approval_valid(approved_on, date(2024, 6, 5)) is False

    monkeypatch.setattr(config, "approval_valid_days", 5)
    assert is_approval_valid(approved_on, date(2024, 6, 7)) is True
    assert is_approval_valid(approved_on, date(2024, 6, 10)) is False


def test_upsert_and_delete_approval_persist(tmp_path):
    owner = tmp_path / "carol"
    owner.mkdir()

    first_date = date(2024, 6, 5)
    updated = upsert_approval("carol", "adm.l", first_date, accounts_root=tmp_path)
    assert updated == {"ADM.L": first_date}
    data = json.loads((owner / "approvals.json").read_text())
    assert data["approvals"] == [
        {"ticker": "ADM.L", "approved_on": first_date.isoformat()}
    ]

    second_date = date(2024, 6, 6)
    updated = upsert_approval("carol", "ADM.l", second_date, accounts_root=tmp_path)
    assert updated == {"ADM.L": second_date}
    data = json.loads((owner / "approvals.json").read_text())
    assert data["approvals"] == [
        {"ticker": "ADM.L", "approved_on": second_date.isoformat()}
    ]

    cleared = delete_approval("carol", "adm.l", accounts_root=tmp_path)
    assert cleared == {}
    data = json.loads((owner / "approvals.json").read_text())
    assert data["approvals"] == []
